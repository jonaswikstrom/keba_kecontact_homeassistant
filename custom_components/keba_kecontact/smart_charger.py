"""Smart charging controller with AI-powered optimization."""
from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime, timedelta, time
from typing import Any, TYPE_CHECKING
from pathlib import Path

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .anthropic_client import (
    AnthropicChargingPlanner,
    ChargingPlan,
    ChargerRequirement,
    PriceSlot,
    TokenUsage,
)
from .charging_history import ChargingHistoryTracker
from .const import (
    DOMAIN,
    CONF_VEHICLE_SOC_ENTITY,
    CONF_VEHICLE_CHARGING_STATUS_ENTITY,
    CONF_BATTERY_CAPACITY,
    CONF_DEPARTURE_TIME,
    CONF_TARGET_SOC,
    MIN_CHARGING_CURRENT_A,
    DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_TARGET_SOC,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)
_FILE_LOG: logging.Logger | None = None


def _setup_file_logger() -> logging.Logger | None:
    """Create a file logger that writes to config directory."""
    file_logger = logging.getLogger("keba_smart_charging_file")
    if file_logger.handlers:
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
            "%(asctime)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        file_logger.addHandler(handler)
        file_logger.info("=== Smart charging file logger started ===")
        return file_logger
    except Exception as e:
        _LOGGER.warning("Could not create file logger: %s", e)
        return None


def _log(level: int, msg: str, *args, exc_info: bool = False) -> None:
    """Log to both standard logger and file logger."""
    _LOGGER.log(level, msg, *args, exc_info=exc_info)
    if _FILE_LOG:
        _FILE_LOG.log(level, msg, *args)
        if exc_info:
            import traceback
            _FILE_LOG.error(traceback.format_exc())


def _log_debug(msg: str, *args) -> None:
    _log(logging.DEBUG, msg, *args)


def _log_info(msg: str, *args) -> None:
    _log(logging.INFO, msg, *args)


def _log_warning(msg: str, *args) -> None:
    _log(logging.WARNING, msg, *args)


def _log_error(msg: str, *args, exc_info: bool = False) -> None:
    _log(logging.ERROR, msg, *args, exc_info=exc_info)


_FILE_LOG = _setup_file_logger()


class SmartCharger:
    """Manages AI-powered charging schedules for multiple chargers."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        nordpool_entity_id: str,
        charger_entry_ids: list[str],
        max_current: int,
    ) -> None:
        """Initialize the smart charger."""
        self.hass = hass
        self._api_key = api_key
        self._nordpool_entity_id = nordpool_entity_id
        self._charger_entry_ids = charger_entry_ids
        self._max_current = max_current

        self._planner = AnthropicChargingPlanner(api_key)
        self._history_tracker = ChargingHistoryTracker(hass)
        self._active_plans: dict[str, ChargingPlan] = {}

        self._unsub_nordpool: callable | None = None
        self._unsub_interval: callable | None = None
        self._unsub_progress_check: callable | None = None
        self._unsub_charger_states: list[callable] = []
        self._unsub_vehicle_status: list[callable] = []
        self._unsub_start_event: callable | None = None

        self._last_tomorrow_valid: bool | None = None
        self._planning_in_progress = False
        self._last_progress_check: dict[str, float] = {}
        self._last_error: str | None = None
        self._last_applied_slot: dict[str, tuple[int, str]] = {}

    @property
    def last_error(self) -> str | None:
        """Return the last error message, if any."""
        return self._last_error

    def clear_error(self) -> None:
        """Clear the last error."""
        self._last_error = None

    @property
    def token_usage(self) -> TokenUsage:
        """Return API token usage statistics."""
        return self._planner.token_usage

    @property
    def active_plans(self) -> dict[str, ChargingPlan]:
        """Return all active plans."""
        return self._active_plans.copy()

    def get_plan(self, charger_entry_id: str) -> ChargingPlan | None:
        """Get active plan for a specific charger."""
        return self._active_plans.get(charger_entry_id)

    async def async_start(self) -> None:
        """Start the smart charger."""
        await self._history_tracker.async_load()

        self._unsub_nordpool = async_track_state_change_event(
            self.hass,
            [self._nordpool_entity_id],
            self._handle_nordpool_change,
        )

        self._unsub_interval = async_track_time_interval(
            self.hass,
            self._execute_plans,
            timedelta(minutes=1),
        )

        self._unsub_progress_check = async_track_time_interval(
            self.hass,
            self._check_charging_progress,
            timedelta(minutes=30),
        )

        for entry_id in self._charger_entry_ids:
            state_entity_id = self._get_state_entity_id(entry_id)
            if state_entity_id:
                unsub = async_track_state_change_event(
                    self.hass,
                    [state_entity_id],
                    self._handle_charger_state_change,
                )
                self._unsub_charger_states.append(unsub)

            vehicle_status_entity = self._get_vehicle_charging_status_entity(entry_id)
            if vehicle_status_entity:
                unsub = async_track_state_change_event(
                    self.hass,
                    [vehicle_status_entity],
                    self._handle_vehicle_status_change,
                )
                self._unsub_vehicle_status.append(unsub)
                _log_info("Listening to vehicle charging status: %s for charger %s",
                    vehicle_status_entity, entry_id)

        _log_info("Smart charger started with %d chargers, max current %dA",
            len(self._charger_entry_ids), self._max_current)

        if self.hass.is_running:
            self.hass.async_create_task(self._check_already_connected_cars())
        else:
            self._unsub_start_event = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                self._on_homeassistant_started,
            )

    async def _on_homeassistant_started(self, event: Event) -> None:
        """Handle Home Assistant started event."""
        import asyncio
        _log_info("Home Assistant started, waiting 2s before checking connected cars...")
        await asyncio.sleep(2)
        await self._check_already_connected_cars()

    async def _check_already_connected_cars(self) -> None:
        """Check for cars that are already connected at startup."""
        _log_info("Checking for already connected cars at startup...")
        _log_info("Charger entry IDs: %s", self._charger_entry_ids)
        _log_info("hass.data[DOMAIN] keys: %s", list(self.hass.data.get(DOMAIN, {}).keys()))

        for entry_id in self._charger_entry_ids:
            entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
            config_entry = entry_data.get("config_entry")
            _log_info("Entry %s: has_data=%s, has_config=%s", entry_id, bool(entry_data), bool(config_entry))
            if config_entry:
                opts = config_entry.options
                _log_info("  options: soc=%s, battery=%s, departure=%s",
                    opts.get('vehicle_soc_entity'), opts.get('battery_capacity_kwh'), opts.get('departure_time'))

            ai_ready = self._is_charger_ai_ready(entry_id)
            state_entity = self._get_state_entity_id(entry_id)
            state = self.hass.states.get(state_entity) if state_entity else None
            _log_info("  ai_ready=%s, state_entity=%s, state=%s", ai_ready, state_entity, state.state if state else None)

        await self._detect_missed_disconnects()

        connected = self._get_connected_chargers()
        _log_info("Connected chargers found: %s", connected)

        if connected:
            _log_info("Found %d already connected charger(s), creating single batch plan", len(connected))
            for entry_id in connected:
                if not self._history_tracker.is_session_active(entry_id):
                    soc_entity = self._get_charger_soc_entity(entry_id)
                    if soc_entity:
                        current_soc = self._get_soc_normalized(soc_entity)
                        session_energy = self._get_charger_session_energy(entry_id)
                        if current_soc is not None:
                            await self._history_tracker.start_session(
                                entry_id,
                                soc_entity,
                                current_soc,
                                session_energy or 0,
                            )
            await self._create_plans_for_chargers(connected)
        else:
            _log_info("No AI-ready connected chargers found at startup")

    async def _detect_missed_disconnects(self) -> None:
        """Detect and end sessions for cars that disconnected while we were down."""
        active_sessions = self._history_tracker.get_all_active_sessions()
        if not active_sessions:
            return

        _log_info("Checking %d persisted active sessions for missed disconnects...", len(active_sessions))

        for entry_id, session in active_sessions.items():
            state_entity = self._get_state_entity_id(entry_id)
            if not state_entity:
                _log_warning("Session for %s has no state entity, ending session", entry_id)
                await self._history_tracker.end_session(entry_id, session.start_soc, 0)
                continue

            state = self.hass.states.get(state_entity)
            if not state:
                _log_warning("State entity %s not found, keeping session active", state_entity)
                continue

            is_connected = state.state in ("Charging", "Ready for charging")

            if not is_connected:
                _log_info(
                    "Detected missed disconnect for %s (state: %s, session started: %s)",
                    entry_id, state.state, session.start_time.isoformat()
                )
                current_soc = self._get_soc_normalized(session.vehicle_soc_entity)
                session_energy = self._get_charger_session_energy(entry_id)
                await self._history_tracker.end_session(
                    entry_id,
                    current_soc if current_soc else session.start_soc,
                    session_energy or 0,
                )
            else:
                _log_info(
                    "Session for %s still active (connected since %s)",
                    entry_id, session.start_time.isoformat()
                )

    async def async_stop(self) -> None:
        """Stop the smart charger."""
        if self._unsub_nordpool:
            self._unsub_nordpool()
        if self._unsub_interval:
            self._unsub_interval()
        if self._unsub_progress_check:
            self._unsub_progress_check()
        for unsub in self._unsub_charger_states:
            unsub()
        for unsub in self._unsub_vehicle_status:
            unsub()

        _log_info("Smart charger stopped")

    @callback
    def _handle_nordpool_change(self, event: Event) -> None:
        """Handle Nordpool entity state changes."""
        new_state = event.data.get("new_state")
        if not new_state:
            return

        tomorrow_available = new_state.attributes.get("tomorrow_available", False)

        if self._last_tomorrow_valid is False and tomorrow_available is True:
            _log_info("Tomorrow's prices now available, checking if replan needed")
            self.hass.async_create_task(self._replan_overnight_if_needed())

        self._last_tomorrow_valid = tomorrow_available

    @callback
    def _handle_charger_state_change(self, event: Event) -> None:
        """Handle charger state changes (car plugged in/out)."""
        entity_id = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        entry_id = self._get_entry_id_from_state_entity(entity_id)
        if not entry_id:
            return

        old_value = old_state.state
        new_value = new_state.state

        if old_value == "Not ready for charging" and new_value in ("Ready for charging", "Charging"):
            _log_info("Car connected to charger %s (state: %s), initiating AI planning", entry_id, new_value)
            self.hass.async_create_task(self._on_car_connected(entry_id))
        elif old_value in ("Ready for charging", "Charging") and new_value == "Not ready for charging":
            _log_info("Car disconnected from charger %s", entry_id)
            self.hass.async_create_task(self._on_car_disconnected(entry_id))

    CHARGING_DONE_STATES = {"done", "idle", "completed", "full", "finished", "not_charging"}

    @callback
    def _handle_vehicle_status_change(self, event: Event) -> None:
        """Handle vehicle charging status changes (for detecting charging completion)."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        new_lower = new_state.state.lower()
        old_lower = old_state.state.lower()

        if new_lower in self.CHARGING_DONE_STATES and old_lower not in self.CHARGING_DONE_STATES:
            entity_id = event.data.get("entity_id")
            entry_id = self._find_entry_for_vehicle_status_entity(entity_id)
            if entry_id:
                _log_info("Charger %s: Vehicle reports charging done (state: %s)", entry_id, new_state.state)
                self.hass.async_create_task(self._on_vehicle_charging_done(entry_id))

    async def _on_vehicle_charging_done(self, entry_id: str) -> None:
        """Handle vehicle reporting charging is complete - stop charging and end session."""
        if entry_id in self._active_plans:
            del self._active_plans[entry_id]
            _log_info("Charger %s: Removed plan (vehicle reports done)", entry_id)

        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        client = entry_data.get("client")

        if client:
            try:
                await client.disable()
                _log_info("Charger %s: Disabled charging (vehicle reports done)", entry_id)
            except Exception as err:
                _log_error("Failed to disable charger %s: %s", entry_id, err)

        soc_entity = self._get_charger_soc_entity(entry_id)
        if soc_entity:
            current_soc = self._get_soc_normalized(soc_entity)
            session_energy = self._get_charger_session_energy(entry_id)
            if current_soc is not None:
                await self._history_tracker.end_session(
                    entry_id,
                    current_soc,
                    session_energy or 0,
                )

    async def _on_car_connected(self, triggered_entry_id: str) -> None:
        """Handle car connection - create plans for ALL connected cars."""
        if self._planning_in_progress:
            _LOGGER.debug("Planning already in progress, skipping")
            return

        self._planning_in_progress = True

        try:
            soc_entity = self._get_charger_soc_entity(triggered_entry_id)
            if soc_entity:
                current_soc = self._get_soc_normalized(soc_entity)
                session_energy = self._get_charger_session_energy(triggered_entry_id)
                if current_soc is not None:
                    await self._history_tracker.start_session(
                        triggered_entry_id,
                        soc_entity,
                        current_soc,
                        session_energy or 0,
                    )

            await self._create_plans_for_all_connected()
        except Exception as err:
            _log_error("Failed to create charging plans: %s", err, exc_info=True)
        finally:
            self._planning_in_progress = False

    async def _on_car_disconnected(self, entry_id: str) -> None:
        """Handle car disconnection."""
        if entry_id in self._active_plans:
            del self._active_plans[entry_id]
            _log_info("Removed plan for disconnected charger %s", entry_id)

        soc_entity = self._get_charger_soc_entity(entry_id)
        if soc_entity:
            current_soc = self._get_soc_normalized(soc_entity)
            session_energy = self._get_charger_session_energy(entry_id)
            if current_soc is not None:
                await self._history_tracker.end_session(
                    entry_id,
                    current_soc,
                    session_energy or 0,
                )

        remaining_connected = self._get_connected_chargers()
        if remaining_connected:
            _log_info(
                "Replanning for remaining %d connected chargers",
                len(remaining_connected)
            )
            await self._create_plans_for_chargers(remaining_connected)

    async def _create_plans_for_all_connected(self) -> None:
        """Create plans for all currently connected chargers."""
        connected = self._get_connected_chargers()
        if not connected:
            _LOGGER.debug("No AI-configured chargers connected")
            return

        await self._create_plans_for_chargers(connected)

    async def _create_plans_for_chargers(self, entry_ids: list[str]) -> None:
        """Create AI charging plans for specified chargers."""
        requirements = []

        for entry_id in entry_ids:
            req = self._build_charger_requirement(entry_id)
            if req:
                requirements.append(req)

        if not requirements:
            _log_warning("No valid charger requirements, skipping planning")
            self._last_error = "No valid charger requirements (check SoC entity, battery capacity, departure time)"
            return

        today_prices, tomorrow_prices = self._get_nordpool_prices()
        _log_info("Got %d today prices, %s tomorrow prices",
            len(today_prices), len(tomorrow_prices) if tomorrow_prices else "no")

        if not today_prices:
            _log_warning("No Nordpool prices available, cannot create plan")
            self._last_error = "No Nordpool prices available"
            return

        _log_info("Calling AI planner with %d chargers, %d today slots",
            len(requirements), len(today_prices))

        try:
            plans = await self._planner.create_plan(
                chargers=requirements,
                total_max_current_a=self._max_current,
                today_prices=today_prices,
                tomorrow_prices=tomorrow_prices,
            )

            self._last_error = None
            for plan in plans:
                self._active_plans[plan.charger_id] = plan
                _log_info("Created plan for %s: %d slots, total cost %.2f, reason: %s",
                    plan.charger_id, len(plan.slots), plan.total_cost, plan.reasoning[:100])

        except Exception as err:
            msg = f"AI planning failed: {err}"
            _log_error(msg, exc_info=True)
            self._last_error = msg

    async def _check_charging_progress(self, now: datetime) -> None:
        """Check if actual charging progress matches the plan, replan if needed."""
        if not self._active_plans:
            return

        deviations = []

        for entry_id, plan in self._active_plans.items():
            soc_entity = self._get_charger_soc_entity(entry_id)
            if not soc_entity:
                continue

            actual_soc = self._get_soc_normalized(soc_entity)
            if actual_soc is None:
                continue

            current_hour = now.hour
            current_minute = now.minute
            current_date = now.date().isoformat()
            slot = plan.get_slot_for_time(current_hour, current_minute, current_date)

            if slot and slot.expected_soc_after > 0:
                expected_soc = slot.expected_soc_after
                deviation = abs(actual_soc - expected_soc)

                _LOGGER.debug(
                    "Charger %s: actual SoC %.1f%%, expected %.1f%%, deviation %.1f%%",
                    entry_id, actual_soc, expected_soc, deviation
                )

                if deviation > 10:
                    deviations.append({
                        "charger_id": entry_id,
                        "actual_soc": actual_soc,
                        "expected_soc": expected_soc,
                        "deviation": deviation,
                    })

        if deviations:
            _log_info(
                "Significant charging deviation detected: %s, validating with Haiku",
                deviations
            )

            today_prices, tomorrow_prices = self._get_nordpool_prices()
            if not today_prices:
                return

            try:
                result = await self._planner.validate_plan(
                    current_plans=list(self._active_plans.values()),
                    new_prices_today=today_prices,
                    new_prices_tomorrow=tomorrow_prices,
                )

                if result.replan_needed:
                    _log_info(
                        "Haiku recommends replan due to progress deviation: %s",
                        result.reason
                    )
                    connected = list(self._active_plans.keys())
                    await self._create_plans_for_chargers(connected)
                else:
                    _LOGGER.debug("Haiku says current plan is still OK: %s", result.reason)

            except Exception as err:
                _log_error("Progress validation failed: %s", err)

    async def _replan_overnight_if_needed(self) -> None:
        """Check if plans should be updated with new tomorrow prices."""
        if not self._active_plans:
            return

        now = datetime.now()
        overnight_plans = []

        for plan in self._active_plans.values():
            if plan.departure_time.date() > now.date():
                overnight_plans.append(plan)

        if not overnight_plans:
            _LOGGER.debug("No overnight plans to validate")
            return

        today_prices, tomorrow_prices = self._get_nordpool_prices()

        if not tomorrow_prices:
            _LOGGER.debug("Tomorrow prices still not available")
            return

        try:
            result = await self._planner.validate_plan(
                current_plans=overnight_plans,
                new_prices_today=today_prices,
                new_prices_tomorrow=tomorrow_prices,
            )

            if result.replan_needed:
                _log_info("Replan needed: %s", result.reason)
                connected = list(self._active_plans.keys())
                await self._create_plans_for_chargers(connected)
            else:
                _LOGGER.debug("Current plans are still optimal: %s", result.reason)

        except Exception as err:
            _log_error("Plan validation failed: %s", err)

    async def _execute_plans(self, now: datetime) -> None:
        """Execute charging plans - apply current time slot's settings."""
        current_hour = now.hour
        current_minute = now.minute
        current_date = now.date().isoformat()

        for entry_id, plan in list(self._active_plans.items()):
            if now >= plan.departure_time:
                _log_info("Plan for %s expired (departure time passed)", entry_id)
                del self._active_plans[entry_id]
                await self._restore_charger_to_normal(entry_id)
                continue

            slot = plan.get_slot_for_time(current_hour, current_minute, current_date)

            if slot:
                await self._apply_slot(entry_id, slot)

    async def _apply_slot(self, entry_id: str, slot: Any) -> None:
        """Apply a charging slot's current setting to a charger."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        client = entry_data.get("client")

        if not client:
            _log_warning("No client found for charger %s", entry_id)
            return

        slot_key = f"{slot.date}_{slot.hour:02d}:{slot.minute:02d}"
        last = self._last_applied_slot.get(entry_id)
        is_change = last is None or last != (slot.current_amps, slot_key)

        try:
            current_ma = slot.current_amps * 1000

            if current_ma == 0:
                await client.disable()
                if is_change:
                    _log_info("Charger %s: Paused (slot %s, price %.4f SEK)",
                        entry_id, slot_key, slot.price)
            else:
                await client.enable()
                await client.set_current(current_ma)
                if is_change:
                    _log_info("Charger %s: %dA @ %.4f SEK (SoC→%.0f%%)",
                        entry_id, slot.current_amps, slot.price, slot.expected_soc_after)

            if is_change:
                self._last_applied_slot[entry_id] = (slot.current_amps, slot_key)

        except Exception as err:
            _log_error("Failed to apply slot to %s: %s", entry_id, err)

    async def _restore_charger_to_normal(self, entry_id: str) -> None:
        """Restore charger to user-configured current limit."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        client = entry_data.get("client")
        config_entry = entry_data.get("config_entry")

        if not client or not config_entry:
            return

        try:
            user_limit = config_entry.options.get("current_limit", 16)
            await client.enable()
            await client.set_current(int(user_limit * 1000))
            _log_info("Restored charger %s to user limit %dA", entry_id, user_limit)
        except Exception as err:
            _log_error("Failed to restore charger %s: %s", entry_id, err)

    def _get_connected_chargers(self) -> list[str]:
        """Get list of chargers with cars connected and AI config complete."""
        connected = []

        for entry_id in self._charger_entry_ids:
            if not self._is_charger_ai_ready(entry_id):
                continue

            state_entity = self._get_state_entity_id(entry_id)
            if state_entity:
                state = self.hass.states.get(state_entity)
                if state and state.state in ("Charging", "Ready for charging"):
                    connected.append(entry_id)

        return connected

    def _is_charger_ai_ready(self, entry_id: str) -> bool:
        """Check if charger has all required AI configuration."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        config_entry: ConfigEntry | None = entry_data.get("config_entry")

        if not config_entry:
            _LOGGER.debug("Charger %s: no config_entry in hass.data", entry_id)
            return False

        soc_entity = config_entry.options.get(CONF_VEHICLE_SOC_ENTITY)
        battery = config_entry.options.get(CONF_BATTERY_CAPACITY)
        departure = config_entry.options.get(CONF_DEPARTURE_TIME)

        is_ready = bool(soc_entity and battery and departure)
        _LOGGER.debug(
            "Charger %s AI ready check: soc=%s, battery=%s, departure=%s -> %s",
            entry_id, soc_entity, battery, departure, is_ready
        )

        return is_ready

    def _build_charger_requirement(self, entry_id: str) -> ChargerRequirement | None:
        """Build a ChargerRequirement from charger config and state."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        config_entry: ConfigEntry | None = entry_data.get("config_entry")
        coordinator = entry_data.get("coordinator")

        if not config_entry:
            return None

        soc_entity = config_entry.options.get(CONF_VEHICLE_SOC_ENTITY)
        battery_capacity = config_entry.options.get(
            CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY_KWH
        )
        departure_time_str = config_entry.options.get(CONF_DEPARTURE_TIME, "07:00:00")
        target_soc = config_entry.options.get(CONF_TARGET_SOC, DEFAULT_TARGET_SOC)

        if not soc_entity:
            return None

        current_soc = self._get_soc_normalized(soc_entity)
        if current_soc is None:
            _log_warning("Could not get SoC for %s from %s", entry_id, soc_entity)
            return None

        now = datetime.now()
        departure_time = self._parse_departure_time(departure_time_str, now)

        max_current = 32
        if coordinator and coordinator.data:
            hw_limit = coordinator.data.get("curr_hw", 32000)
            max_current = min(int(hw_limit / 1000), self._max_current)

        historical_rate = self._history_tracker.get_expected_charging_rate(
            entry_id, soc_entity
        )

        return ChargerRequirement(
            charger_id=entry_id,
            charger_name=config_entry.title,
            current_soc=current_soc,
            battery_capacity_kwh=battery_capacity,
            departure_time=departure_time,
            max_current_a=max_current,
            target_soc=float(target_soc),
            historical_charging_rate_kw=historical_rate,
        )

    def _parse_departure_time(self, time_str: str, now: datetime) -> datetime:
        """Parse departure time string and return next occurrence."""
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            departure = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if departure <= now:
                departure += timedelta(days=1)

            return departure
        except Exception:
            return now.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1)

    def _get_nordpool_prices(self) -> tuple[list[PriceSlot], list[PriceSlot] | None]:
        """Get today's and tomorrow's prices from electricity price entity."""
        _log_debug("Getting Nordpool prices from %s", self._nordpool_entity_id)
        state = self.hass.states.get(self._nordpool_entity_id)

        if not state:
            msg = f"Nordpool entity '{self._nordpool_entity_id}' not found"
            _log_error(msg)
            self._last_error = msg
            return [], None

        unit = state.attributes.get("unit_of_measurement", "")
        multiplier = self._get_price_multiplier(unit)
        _log_debug("Price unit: %s, multiplier: %s", unit, multiplier)

        today_raw = state.attributes.get("prices_today", [])
        _log_info("prices_today has %d entries, type: %s",
            len(today_raw) if today_raw else 0,
            type(today_raw[0]).__name__ if today_raw else "empty")

        today_date = datetime.now().date().isoformat()
        today = self._extract_prices_to_slots(today_raw, today_date, multiplier)

        if not today:
            msg = f"No prices_today in '{self._nordpool_entity_id}'"
            _log_error(msg)
            self._last_error = msg
            return [], None

        _log_info("Extracted %d price slots for today", len(today))
        if today:
            _log_debug("First slot: %s:%s = %s, Last slot: %s:%s = %s",
                today[0].hour, today[0].minute, today[0].price,
                today[-1].hour, today[-1].minute, today[-1].price)

        tomorrow = None
        if state.attributes.get("tomorrow_available"):
            tomorrow_raw = state.attributes.get("prices_tomorrow", [])
            tomorrow_date = (datetime.now().date() + timedelta(days=1)).isoformat()
            tomorrow = self._extract_prices_to_slots(tomorrow_raw, tomorrow_date, multiplier)
            _log_info("Extracted %d price slots for tomorrow", len(tomorrow) if tomorrow else 0)

        return today, tomorrow

    def _get_price_multiplier(self, unit: str) -> float:
        """Get multiplier to normalize price to currency/kWh."""
        unit_lower = unit.lower()
        if "mwh" in unit_lower:
            return 0.001
        if "öre" in unit_lower or "ore" in unit_lower or "cent" in unit_lower:
            return 0.01
        return 1.0

    def _extract_prices_to_slots(
        self, price_list: list, date: str, multiplier: float = 1.0
    ) -> list[PriceSlot]:
        """Extract price values from list and convert to PriceSlot objects."""
        if not price_list:
            return []

        slots_count = len(price_list)
        minutes_per_slot = (24 * 60) // slots_count

        if isinstance(price_list[0], dict):
            first = price_list[0]
            if "start" in first:
                prices = sorted(price_list, key=lambda x: x.get("start", ""))
                slots = []
                for i, item in enumerate(prices):
                    total_minutes = i * minutes_per_slot
                    slots.append(PriceSlot(
                        hour=total_minutes // 60,
                        minute=total_minutes % 60,
                        price=item.get("price", item.get("value", 0.0)) * multiplier,
                        date=date,
                    ))
                return slots
            elif slots_count == 24 and "hour" in first:
                prices = sorted(price_list, key=lambda x: x.get("hour", 0))
                slots = []
                for item in prices:
                    slots.append(PriceSlot(
                        hour=item.get("hour", 0),
                        minute=0,
                        price=item.get("price", 0.0) * multiplier,
                        date=date,
                    ))
                return slots
            else:
                slots = []
                for i, item in enumerate(price_list):
                    total_minutes = i * minutes_per_slot
                    slots.append(PriceSlot(
                        hour=total_minutes // 60,
                        minute=total_minutes % 60,
                        price=item.get("price", item.get("value", 0.0)) * multiplier,
                        date=date,
                    ))
                return slots

        slots = []
        for i, price in enumerate(price_list):
            total_minutes = i * minutes_per_slot
            slots.append(PriceSlot(
                hour=total_minutes // 60,
                minute=total_minutes % 60,
                price=price * multiplier,
                date=date,
            ))
        return slots

    def _get_state_entity_id(self, entry_id: str) -> str | None:
        """Get the state entity ID for a charger entry."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        config_entry: ConfigEntry | None = entry_data.get("config_entry")

        if not config_entry:
            return None

        serial = config_entry.title.split("(")[-1].rstrip(")")
        return f"sensor.keba_kecontact_{serial.lower()}_status"

    def _get_entry_id_from_state_entity(self, entity_id: str) -> str | None:
        """Get entry ID from a state entity ID."""
        for entry_id in self._charger_entry_ids:
            if self._get_state_entity_id(entry_id) == entity_id:
                return entry_id
        return None

    def _get_entity_state_float(self, entity_id: str) -> float | None:
        """Get numeric state value from an entity."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_soc_normalized(self, entity_id: str) -> float | None:
        """Get SoC value normalized to 0-100 range."""
        state = self.hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None

        unit = state.attributes.get("unit_of_measurement", "")
        if unit == "%" or value > 1.0:
            return value
        return value * 100

    def _get_charger_soc_entity(self, entry_id: str) -> str | None:
        """Get the configured SoC entity for a charger."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        config_entry = entry_data.get("config_entry")
        if config_entry:
            return config_entry.options.get(CONF_VEHICLE_SOC_ENTITY)
        return None

    def _get_charger_session_energy(self, entry_id: str) -> float | None:
        """Get current session energy for a charger."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        coordinator = entry_data.get("coordinator")
        if coordinator and coordinator.data:
            return coordinator.data.get("e_pres", 0) / 10000
        return None

    def _get_vehicle_charging_status_entity(self, entry_id: str) -> str | None:
        """Get the configured vehicle charging status entity for a charger."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id, {})
        config_entry = entry_data.get("config_entry")
        if config_entry:
            return config_entry.options.get(CONF_VEHICLE_CHARGING_STATUS_ENTITY)
        return None

    def _find_entry_for_vehicle_status_entity(self, entity_id: str) -> str | None:
        """Find charger entry ID from a vehicle status entity ID."""
        for entry_id in self._charger_entry_ids:
            if self._get_vehicle_charging_status_entity(entry_id) == entity_id:
                return entry_id
        return None
