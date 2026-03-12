"""Anthropic API client for AI-powered smart charging optimization."""
from __future__ import annotations

import logging
import logging.handlers
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)
_FILE_LOG: logging.Logger | None = None


def _get_file_logger() -> logging.Logger | None:
    global _FILE_LOG
    if _FILE_LOG is not None:
        return _FILE_LOG
    file_logger = logging.getLogger("keba_anthropic_file")
    if file_logger.handlers:
        _FILE_LOG = file_logger
        return file_logger
    file_logger.setLevel(logging.DEBUG)
    try:
        log_path = Path("/config/keba_smart_charging.log")
        if not log_path.parent.exists():
            log_path = Path.home() / "keba_smart_charging.log"
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [API] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        file_logger.addHandler(handler)
        _FILE_LOG = file_logger
        return file_logger
    except Exception:
        return None


def _log_info(msg: str, *args) -> None:
    _LOGGER.info(msg, *args)
    fl = _get_file_logger()
    if fl:
        fl.info(msg, *args)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5"


@dataclass
class ChargingSlot:
    """Represents a single time slot's charging configuration."""

    hour: int
    minute: int
    date: str
    current_amps: int
    expected_soc_after: float
    price: float
    cost: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "hour": self.hour,
            "minute": self.minute,
            "date": self.date,
            "current_amps": self.current_amps,
            "expected_soc_after": self.expected_soc_after,
            "price": self.price,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingSlot:
        """Deserialize from dictionary."""
        return cls(
            hour=data["hour"],
            minute=data.get("minute", 0),
            date=data["date"],
            current_amps=data["current_amps"],
            expected_soc_after=data.get("expected_soc_after", data.get("soc_after", 0)),
            price=data["price"],
            cost=data["cost"],
        )


@dataclass
class ChargingPlan:
    """Represents a complete charging plan for one charger."""

    charger_id: str
    created_at: datetime
    departure_time: datetime
    slots: list[ChargingSlot] = field(default_factory=list)
    total_cost: float = 0.0
    reasoning: str = ""
    status: str = "active"
    initial_soc: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "charger_id": self.charger_id,
            "created_at": self.created_at.isoformat(),
            "departure_time": self.departure_time.isoformat(),
            "slots": [s.to_dict() for s in self.slots],
            "total_cost": self.total_cost,
            "reasoning": self.reasoning,
            "status": self.status,
            "initial_soc": self.initial_soc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingPlan:
        """Deserialize from storage."""
        return cls(
            charger_id=data["charger_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            departure_time=datetime.fromisoformat(data["departure_time"]),
            slots=[ChargingSlot.from_dict(s) for s in data.get("slots", [])],
            total_cost=data.get("total_cost", 0.0),
            reasoning=data.get("reasoning", ""),
            status=data.get("status", "active"),
            initial_soc=data.get("initial_soc"),
        )

    def get_slot_for_time(self, hour: int, minute: int, date: str) -> ChargingSlot | None:
        """Get the charging slot for a specific time and date."""
        if not self.slots:
            return None

        minutes_per_slot = self._get_minutes_per_slot()
        slot_minute = (minute // minutes_per_slot) * minutes_per_slot

        for slot in self.slots:
            if slot.hour == hour and slot.minute == slot_minute and slot.date == date:
                return slot
        return None

    def _get_minutes_per_slot(self) -> int:
        """Determine minutes per slot from the slots in this plan."""
        if len(self.slots) < 2:
            return 60

        slots_sorted = sorted(self.slots, key=lambda s: (s.date, s.hour, s.minute))
        for i in range(len(slots_sorted) - 1):
            s1, s2 = slots_sorted[i], slots_sorted[i + 1]
            if s1.date == s2.date:
                diff = (s2.hour * 60 + s2.minute) - (s1.hour * 60 + s1.minute)
                if diff > 0:
                    return diff
        return 60


@dataclass
class ChargerRequirement:
    """Input data for a single charger's charging needs."""

    charger_id: str
    charger_name: str
    current_soc: float
    battery_capacity_kwh: float
    departure_time: datetime
    max_current_a: int
    target_soc: float = 100.0


@dataclass
class ValidationResult:
    """Result from plan validation."""

    replan_needed: bool
    reason: str


@dataclass
class PriceSlot:
    """A single price slot with time information."""

    hour: int
    minute: int
    price: float
    date: str


SYSTEM_PROMPT = """You are an EV charging optimization AI. Your task is to create cost-optimal charging schedules while ensuring vehicles are ready by their departure times.

CONSTRAINTS (MUST be satisfied):
1. TOTAL MAX CURRENT: Sum of all chargers' current ≤ total_max_current_a at any time slot
2. MIN CURRENT PER CHARGER: Each charger gets either 0A (paused) OR ≥6A. Never 1-5A.
3. MAX CURRENT PER CHARGER: Respect each charger's individual max_current_a limit
4. DEPARTURE TIME: Each vehicle must reach its target SoC by its departure time. ONLY schedule charging slots BEFORE the departure time.

CHARGING CALCULATIONS:
- Three-phase charging: Power (kW) = Current (A) × 230V × 3 × 0.95 / 1000
- Energy per slot (kWh) = Power (kW) × (slot_duration_minutes / 60)
- SoC increase = Energy (kWh) / Battery capacity (kWh) × 100%

TIME SLOTS:
- Prices are provided with variable resolution (15-min, 30-min, or hourly)
- The slot duration is indicated in the prompt (e.g., "15-minute slots")
- Each slot needs hour AND minute fields (e.g., hour=14, minute=30 for 14:30)
- IMPORTANT: Only include slots where charging occurs (current_amps > 0)
- Do NOT include slots with current_amps=0. Missing slots are treated as paused.

OPTIMIZATION GOAL:
Minimize total electricity cost while meeting all constraints. Prefer cheaper slots when possible, but ensure vehicles are fully charged by departure.

OUTPUT FORMAT:
- You must respond with valid JSON matching the tool schema exactly
- Keep output minimal - only active charging slots
- All numeric values (cost, price, soc_after) must be computed numbers, NOT expressions
- Example: "cost": 0.52 (correct), NOT "cost": 0.3374 * 1.64 (wrong)"""

CREATE_PLAN_TOOL = {
    "name": "create_charging_plan",
    "description": "Create optimized charging schedules for one or more EVs",
    "input_schema": {
        "type": "object",
        "properties": {
            "plans": {
                "type": "array",
                "description": "One plan per charger",
                "items": {
                    "type": "object",
                    "properties": {
                        "charger_id": {"type": "string"},
                        "slots": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hour": {"type": "integer", "minimum": 0, "maximum": 23},
                                    "minute": {"type": "integer", "minimum": 0, "maximum": 59, "description": "Slot start minute (0, 15, 30, 45 for 15-min slots)"},
                                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                                    "current_amps": {"type": "integer", "minimum": 0},
                                    "soc_after": {"type": "number"},
                                    "price": {"type": "number"},
                                    "cost": {"type": "number"},
                                },
                                "required": ["hour", "minute", "date", "current_amps", "soc_after", "price", "cost"],
                            },
                        },
                        "total_cost": {"type": "number"},
                    },
                    "required": ["charger_id", "slots", "total_cost"],
                },
            },
            "reasoning": {"type": "string", "description": "Brief explanation of the optimization strategy"},
        },
        "required": ["plans", "reasoning"],
    },
}

VALIDATE_PLAN_TOOL = {
    "name": "validate_plan",
    "description": "Check if current plan is still optimal with new prices",
    "input_schema": {
        "type": "object",
        "properties": {
            "replan_needed": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["replan_needed", "reason"],
    },
}


@dataclass
class TokenUsage:
    """Tracks API token usage statistics."""

    total_input: int = 0
    total_output: int = 0
    sonnet_input: int = 0
    sonnet_output: int = 0
    haiku_input: int = 0
    haiku_output: int = 0
    api_calls: int = 0

    @property
    def total(self) -> int:
        return self.total_input + self.total_output

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total,
            "total_input": self.total_input,
            "total_output": self.total_output,
            "sonnet_input": self.sonnet_input,
            "sonnet_output": self.sonnet_output,
            "sonnet_total": self.sonnet_input + self.sonnet_output,
            "haiku_input": self.haiku_input,
            "haiku_output": self.haiku_output,
            "haiku_total": self.haiku_input + self.haiku_output,
            "api_calls": self.api_calls,
        }


class AnthropicChargingPlanner:
    """Anthropic API client for EV charging optimization."""

    PAYLOAD_HISTORY_FILE = "/config/keba_ai_payloads.json"
    MAX_PAYLOAD_HISTORY = 5

    def __init__(self, api_key: str) -> None:
        """Initialize the planner with API key."""
        self._api_key = api_key
        self._token_usage = TokenUsage()
        self._payload_history: list[dict] = []
        self._load_payload_history()

    @property
    def token_usage(self) -> TokenUsage:
        """Return token usage statistics."""
        return self._token_usage

    @property
    def payload_history(self) -> list[dict]:
        """Return payload history for debugging."""
        return self._payload_history.copy()

    def _load_payload_history(self) -> None:
        """Load payload history from file."""
        import json
        try:
            with open(self.PAYLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                self._payload_history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._payload_history = []

    def _save_payload_history(self) -> None:
        """Save payload history to file."""
        import json
        try:
            with open(self.PAYLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._payload_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _LOGGER.warning("Failed to save payload history: %s", e)

    def _add_payload(self, prompt: str, response: dict, model: str) -> None:
        """Add a payload to history, keeping only the latest entries."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "prompt": prompt,
            "response": response,
        }
        self._payload_history.append(entry)
        while len(self._payload_history) > self.MAX_PAYLOAD_HISTORY:
            self._payload_history.pop(0)
        self._save_payload_history()

    async def create_plan(
        self,
        chargers: list[ChargerRequirement],
        total_max_current_a: int,
        today_prices: list[PriceSlot],
        tomorrow_prices: list[PriceSlot] | None,
        current_time: datetime | None = None,
        max_retries: int = 3,
    ) -> list[ChargingPlan]:
        """Create optimal charging plans for all chargers using Sonnet."""
        import asyncio

        if current_time is None:
            current_time = datetime.now()

        prompt = self._build_create_prompt(
            chargers, total_max_current_a, today_prices, tomorrow_prices, current_time
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                response = await self._call_api(
                    model=MODEL_SONNET,
                    prompt=prompt,
                    tools=[CREATE_PLAN_TOOL],
                )

                self._add_payload(prompt, response, MODEL_SONNET)

                plans = self._parse_create_response(chargers, response, current_time)
                if plans:
                    return plans

            except ValueError as e:
                last_error = e
                if "No valid plans" in str(e) and attempt < max_retries - 1:
                    _log_info("Retry %d/%d: Empty API response, waiting 2s before retry...",
                        attempt + 1, max_retries)
                    await asyncio.sleep(2)
                    continue
                raise

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    _log_info("Retry %d/%d: API error '%s', waiting 2s before retry...",
                        attempt + 1, max_retries, str(e)[:100])
                    await asyncio.sleep(2)
                    continue
                raise

        raise last_error or ValueError("Failed to create plans after retries")

    async def validate_plan(
        self,
        current_plans: list[ChargingPlan],
        new_prices_today: list[PriceSlot],
        new_prices_tomorrow: list[PriceSlot] | None,
    ) -> ValidationResult:
        """Check if plans need updating using Haiku."""
        prompt = self._build_validate_prompt(current_plans, new_prices_today, new_prices_tomorrow)

        response = await self._call_api(
            model=MODEL_HAIKU,
            prompt=prompt,
            tools=[VALIDATE_PLAN_TOOL],
        )

        return self._parse_validate_response(response)

    def _build_create_prompt(
        self,
        chargers: list[ChargerRequirement],
        total_max_current_a: int,
        today_prices: list[PriceSlot],
        tomorrow_prices: list[PriceSlot] | None,
        current_time: datetime,
    ) -> str:
        """Build the prompt for plan creation."""
        slot_minutes = self._get_slot_duration_minutes(today_prices)

        lines = [
            f"Current time: {current_time.strftime('%Y-%m-%d %H:%M')}",
            f"Total max current available: {total_max_current_a}A",
            f"Slot duration: {slot_minutes} minutes",
            "",
            "CHARGERS TO PLAN:",
        ]

        for i, c in enumerate(chargers, 1):
            lines.append(
                f"{i}. {c.charger_name} (ID: {c.charger_id})"
            )
            lines.append(
                f"   - Current SoC: {c.current_soc:.0f}%, Target SoC: {c.target_soc:.0f}%, Battery: {c.battery_capacity_kwh} kWh"
            )
            lines.append(
                f"   - Departure: {c.departure_time.strftime('%Y-%m-%d %H:%M')}, Max current: {c.max_current_a}A"
            )

        lines.append("")
        lines.append("ELECTRICITY PRICES (per kWh):")

        current_slot_start = current_time.hour * 60 + (current_time.minute // slot_minutes) * slot_minutes

        if today_prices:
            lines.append(f"Today ({today_prices[0].date}):")
            for slot in today_prices:
                slot_start = slot.hour * 60 + slot.minute
                if slot_start >= current_slot_start:
                    lines.append(f"  {slot.hour:02d}:{slot.minute:02d} - {slot.price:.4f}")

        if tomorrow_prices:
            lines.append(f"Tomorrow ({tomorrow_prices[0].date}):")
            for slot in tomorrow_prices:
                lines.append(f"  {slot.hour:02d}:{slot.minute:02d} - {slot.price:.4f}")
        else:
            lines.append("Tomorrow's prices: Not available yet")

        lines.append("")
        lines.append("Create optimal charging schedules. Use the create_charging_plan tool.")

        return "\n".join(lines)

    def _get_slot_duration_minutes(self, prices: list[PriceSlot]) -> int:
        """Determine slot duration in minutes from price data."""
        if len(prices) < 2:
            return 60

        slots_per_day = len(prices)
        if slots_per_day == 96:
            return 15
        elif slots_per_day == 48:
            return 30
        elif slots_per_day == 24:
            return 60
        else:
            return 24 * 60 // slots_per_day

    def _build_validate_prompt(
        self,
        current_plans: list[ChargingPlan],
        new_prices_today: list[PriceSlot],
        new_prices_tomorrow: list[PriceSlot] | None,
    ) -> str:
        """Build the prompt for plan validation."""
        lines = [
            "Check if the following charging plans are still optimal with updated prices.",
            "",
            "CURRENT PLANS:",
        ]

        for plan in current_plans:
            lines.append(f"Charger {plan.charger_id}:")
            lines.append(f"  Total cost: {plan.total_cost:.2f}")
            lines.append("  Scheduled slots:")
            for slot in plan.slots:
                lines.append(f"    {slot.date} {slot.hour:02d}:{slot.minute:02d} - {slot.current_amps}A @ {slot.price:.4f}")

        lines.append("")
        lines.append("NEW PRICES:")

        if new_prices_today:
            lines.append(f"Today ({new_prices_today[0].date}):")
            for slot in new_prices_today:
                lines.append(f"  {slot.hour:02d}:{slot.minute:02d} - {slot.price:.4f}")

        if new_prices_tomorrow:
            lines.append(f"Tomorrow ({new_prices_tomorrow[0].date}):")
            for slot in new_prices_tomorrow:
                lines.append(f"  {slot.hour:02d}:{slot.minute:02d} - {slot.price:.4f}")

        lines.append("")
        lines.append(
            "Would the plans benefit significantly from replanning? "
            "Use the validate_plan tool to respond."
        )

        return "\n".join(lines)

    async def _call_api(
        self,
        model: str,
        prompt: str,
        tools: list[dict],
    ) -> dict[str, Any]:
        """Call the Anthropic API."""
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": 16384,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "tools": tools,
            "tool_choice": {"type": "tool", "name": tools[0]["name"]},
        }

        _LOGGER.debug("Calling Anthropic API with model %s", model)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                ANTHROPIC_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Anthropic API error %d: %s", response.status, error_text)
                    raise RuntimeError(f"Anthropic API error: {response.status}")

                result = await response.json()
                self._track_tokens(model, result)
                return result

    def _track_tokens(self, model: str, response: dict[str, Any]) -> None:
        """Track token usage from API response."""
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        self._token_usage.total_input += input_tokens
        self._token_usage.total_output += output_tokens
        self._token_usage.api_calls += 1

        if model == MODEL_SONNET:
            self._token_usage.sonnet_input += input_tokens
            self._token_usage.sonnet_output += output_tokens
        elif model == MODEL_HAIKU:
            self._token_usage.haiku_input += input_tokens
            self._token_usage.haiku_output += output_tokens

    def _parse_create_response(
        self,
        chargers: list[ChargerRequirement],
        response: dict[str, Any],
        current_time: datetime,
    ) -> list[ChargingPlan]:
        """Parse the API response into ChargingPlan objects."""
        import json
        stop_reason = response.get("stop_reason", "unknown")
        usage = response.get("usage", {})
        _log_info("API stop_reason=%s, input_tokens=%s, output_tokens=%s",
            stop_reason, usage.get("input_tokens"), usage.get("output_tokens"))

        content_list = response.get("content", [])
        _log_info("API response has %d content blocks", len(content_list))
        for i, c in enumerate(content_list):
            _log_info("Content[%d] type=%s, name=%s", i, c.get("type"), c.get("name", "N/A"))
            if c.get("type") == "text":
                _log_info("Content[%d] text: %s", i, c.get("text", "")[:500])
            if c.get("type") == "tool_use":
                raw_input = json.dumps(c.get("input", {}))
                _log_info("Content[%d] raw input (first 1000 chars): %s", i, raw_input[:1000])

        plans = []

        for content in content_list:
            if content.get("type") == "tool_use" and content.get("name") == "create_charging_plan":
                tool_input = content.get("input", {})
                _log_info("tool_input keys: %s", list(tool_input.keys()))
                plans_data = tool_input.get("plans", [])
                if isinstance(plans_data, str):
                    try:
                        plans_data = json.loads(plans_data)
                        _log_info("Parsed plans from JSON string")
                    except json.JSONDecodeError:
                        _log_error("Failed to parse plans JSON string")
                        plans_data = []
                _log_info("plans array length: %d", len(plans_data))
                if plans_data and isinstance(plans_data, list) and len(plans_data) > 0:
                    _log_info("First plan keys: %s", list(plans_data[0].keys()) if isinstance(plans_data[0], dict) else [])
                reasoning = tool_input.get("reasoning", "")

                for plan_data in plans_data:
                    try:
                        charger_id = plan_data["charger_id"]
                        _log_info("Parsing plan for charger_id: %s", charger_id)

                        charger = next((c for c in chargers if c.charger_id == charger_id), None)
                        departure = charger.departure_time if charger else current_time

                        slots = []
                        for slot_data in plan_data.get("slots", []):
                            slots.append(ChargingSlot(
                                hour=slot_data["hour"],
                                minute=slot_data.get("minute", 0),
                                date=slot_data["date"],
                                current_amps=slot_data["current_amps"],
                                expected_soc_after=slot_data.get("soc_after", 0),
                                price=slot_data["price"],
                                cost=slot_data["cost"],
                            ))

                        plans.append(ChargingPlan(
                            charger_id=charger_id,
                            created_at=current_time,
                            departure_time=departure,
                            slots=slots,
                            total_cost=plan_data.get("total_cost", 0.0),
                            reasoning=reasoning,
                            status="active",
                        ))
                    except Exception as e:
                        _log_info("Failed to parse plan: %s, plan_data=%s", e, str(plan_data)[:500])

        if not plans:
            _LOGGER.error("Failed to parse charging plans from API response")
            raise ValueError("No valid plans in API response")

        return plans

    def _parse_validate_response(self, response: dict[str, Any]) -> ValidationResult:
        """Parse the validation response."""
        for content in response.get("content", []):
            if content.get("type") == "tool_use" and content.get("name") == "validate_plan":
                tool_input = content.get("input", {})
                return ValidationResult(
                    replan_needed=tool_input.get("replan_needed", False),
                    reason=tool_input.get("reason", ""),
                )

        _LOGGER.warning("Could not parse validation response, assuming no replan needed")
        return ValidationResult(replan_needed=False, reason="Failed to parse response")
