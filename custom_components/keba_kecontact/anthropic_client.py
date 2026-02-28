"""Anthropic API client for AI-powered smart charging optimization."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL_SONNET = "claude-3-5-sonnet-latest"
MODEL_HAIKU = "claude-3-5-haiku-latest"


@dataclass
class ChargingSlot:
    """Represents a single hour's charging configuration."""

    hour: int
    date: str
    current_amps: int
    expected_soc_after: float
    price: float
    cost: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "hour": self.hour,
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
        )

    def get_slot_for_hour(self, hour: int, date: str) -> ChargingSlot | None:
        """Get the charging slot for a specific hour and date."""
        for slot in self.slots:
            if slot.hour == hour and slot.date == date:
                return slot
        return None


@dataclass
class ChargerRequirement:
    """Input data for a single charger's charging needs."""

    charger_id: str
    charger_name: str
    current_soc: float
    battery_capacity_kwh: float
    departure_time: datetime
    max_current_a: int
    historical_charging_rate_kw: float | None = None


@dataclass
class ValidationResult:
    """Result from plan validation."""

    replan_needed: bool
    reason: str


SYSTEM_PROMPT = """You are an EV charging optimization AI. Your task is to create cost-optimal charging schedules while ensuring vehicles are ready by their departure times.

CONSTRAINTS (MUST be satisfied):
1. TOTAL MAX CURRENT: Sum of all chargers' current ≤ total_max_current_a at any hour
2. MIN CURRENT PER CHARGER: Each charger gets either 0A (paused) OR ≥6A. Never 1-5A.
3. MAX CURRENT PER CHARGER: Respect each charger's individual max_current_a limit
4. DEPARTURE TIME: Each vehicle must reach near 100% SoC by its departure time

CHARGING CALCULATIONS:
- Three-phase charging: Power (kW) = Current (A) × 230V × 3 × 0.95 / 1000
- Energy per hour (kWh) = Power (kW) × 1 hour
- SoC increase = Energy (kWh) / Battery capacity (kWh) × 100%

OPTIMIZATION GOAL:
Minimize total electricity cost while meeting all constraints. Prefer cheaper hours when possible, but ensure vehicles are fully charged by departure.

OUTPUT FORMAT:
You must respond with valid JSON matching the tool schema exactly."""

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
                                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                                    "current_amps": {"type": "integer", "minimum": 0},
                                    "soc_after": {"type": "number"},
                                    "price": {"type": "number"},
                                    "cost": {"type": "number"},
                                },
                                "required": ["hour", "date", "current_amps", "soc_after", "price", "cost"],
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


class AnthropicChargingPlanner:
    """Anthropic API client for EV charging optimization."""

    def __init__(self, api_key: str) -> None:
        """Initialize the planner with API key."""
        self._api_key = api_key

    async def create_plan(
        self,
        chargers: list[ChargerRequirement],
        total_max_current_a: int,
        today_prices: list[float],
        tomorrow_prices: list[float] | None,
        current_time: datetime | None = None,
    ) -> list[ChargingPlan]:
        """Create optimal charging plans for all chargers using Sonnet."""
        if current_time is None:
            current_time = datetime.now()

        prompt = self._build_create_prompt(
            chargers, total_max_current_a, today_prices, tomorrow_prices, current_time
        )

        response = await self._call_api(
            model=MODEL_SONNET,
            prompt=prompt,
            tools=[CREATE_PLAN_TOOL],
        )

        return self._parse_create_response(chargers, response, current_time)

    async def validate_plan(
        self,
        current_plans: list[ChargingPlan],
        new_prices_today: list[float],
        new_prices_tomorrow: list[float] | None,
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
        today_prices: list[float],
        tomorrow_prices: list[float] | None,
        current_time: datetime,
    ) -> str:
        """Build the prompt for plan creation."""
        lines = [
            f"Current time: {current_time.strftime('%Y-%m-%d %H:%M')}",
            f"Total max current available: {total_max_current_a}A",
            "",
            "CHARGERS TO PLAN:",
        ]

        for i, c in enumerate(chargers, 1):
            rate_info = f", historical rate: {c.historical_charging_rate_kw:.1f} kW" if c.historical_charging_rate_kw else ""
            lines.append(
                f"{i}. {c.charger_name} (ID: {c.charger_id})"
            )
            lines.append(
                f"   - Current SoC: {c.current_soc:.0f}%, Battery: {c.battery_capacity_kwh} kWh"
            )
            lines.append(
                f"   - Departure: {c.departure_time.strftime('%Y-%m-%d %H:%M')}, Max current: {c.max_current_a}A{rate_info}"
            )

        lines.append("")
        lines.append("ELECTRICITY PRICES (per kWh):")
        lines.append(f"Today ({current_time.strftime('%Y-%m-%d')}):")

        for hour, price in enumerate(today_prices):
            if hour >= current_time.hour:
                lines.append(f"  {hour:02d}:00 - {price:.4f}")

        if tomorrow_prices:
            tomorrow = current_time.date()
            from datetime import timedelta
            tomorrow = tomorrow + timedelta(days=1)
            lines.append(f"Tomorrow ({tomorrow.isoformat()}):")
            for hour, price in enumerate(tomorrow_prices):
                lines.append(f"  {hour:02d}:00 - {price:.4f}")
        else:
            lines.append("Tomorrow's prices: Not available yet")

        lines.append("")
        lines.append("Create optimal charging schedules. Use the create_charging_plan tool.")

        return "\n".join(lines)

    def _build_validate_prompt(
        self,
        current_plans: list[ChargingPlan],
        new_prices_today: list[float],
        new_prices_tomorrow: list[float] | None,
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
                lines.append(f"    {slot.date} {slot.hour:02d}:00 - {slot.current_amps}A @ {slot.price:.4f}")

        lines.append("")
        lines.append("NEW PRICES:")
        lines.append("Today:")
        for hour, price in enumerate(new_prices_today):
            lines.append(f"  {hour:02d}:00 - {price:.4f}")

        if new_prices_tomorrow:
            lines.append("Tomorrow:")
            for hour, price in enumerate(new_prices_tomorrow):
                lines.append(f"  {hour:02d}:00 - {price:.4f}")

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
            "max_tokens": 4096,
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
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error("Anthropic API error %d: %s", response.status, error_text)
                    raise RuntimeError(f"Anthropic API error: {response.status}")

                return await response.json()

    def _parse_create_response(
        self,
        chargers: list[ChargerRequirement],
        response: dict[str, Any],
        current_time: datetime,
    ) -> list[ChargingPlan]:
        """Parse the API response into ChargingPlan objects."""
        plans = []

        for content in response.get("content", []):
            if content.get("type") == "tool_use" and content.get("name") == "create_charging_plan":
                tool_input = content.get("input", {})
                reasoning = tool_input.get("reasoning", "")

                for plan_data in tool_input.get("plans", []):
                    charger_id = plan_data["charger_id"]

                    charger = next((c for c in chargers if c.charger_id == charger_id), None)
                    departure = charger.departure_time if charger else current_time

                    slots = []
                    for slot_data in plan_data.get("slots", []):
                        slots.append(ChargingSlot(
                            hour=slot_data["hour"],
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
