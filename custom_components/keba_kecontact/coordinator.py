"""Charging Coordinator for managing multiple Keba chargers."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    COORDINATOR_STRATEGY_OFF,
    COORDINATOR_STRATEGY_EQUAL,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)
MAX_DISPLAY_LENGTH = 23


class KebaChargingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for managing load balancing between multiple Keba chargers."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        charger_entry_ids: list[str],
        max_current: int,
        strategy: str,
    ) -> None:
        """Initialize the charging coordinator."""
        self._name = name
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_coordinator_{name}",
            update_interval=SCAN_INTERVAL,
        )
        self._charger_entry_ids = charger_entry_ids
        self._max_current = max_current
        self._strategy = strategy
        self._state_listener = None

    async def async_start(self) -> None:
        """Start the coordinator."""
        self._state_listener = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_change
        )
        await self.async_refresh()

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        if self._state_listener:
            self._state_listener()
            self._state_listener = None

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Handle state changes from chargers."""
        entity_id = event.data.get("entity_id", "")

        if "keba_kecontact" in entity_id and "state" in entity_id:
            _LOGGER.debug("Charger state changed: %s, scheduling refresh", entity_id)
            self.hass.async_create_task(self._apply_load_balancing())

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from all chargers and aggregate."""
        try:
            total_power = 0.0
            total_session_energy = 0.0
            total_energy = 0.0
            active_chargers = 0
            charger_states = {}

            for entry_id in self._charger_entry_ids:
                if entry_id not in self.hass.data.get(DOMAIN, {}):
                    _LOGGER.debug("Charger entry %s not found in hass.data, skipping", entry_id)
                    continue

                entry_data = self.hass.data[DOMAIN][entry_id]
                if "coordinator" not in entry_data:
                    _LOGGER.debug("Charger entry %s has no coordinator, skipping", entry_id)
                    continue

                coordinator = entry_data["coordinator"]
                if not coordinator.data:
                    _LOGGER.debug("Charger entry %s has no data yet, skipping", entry_id)
                    continue

                charger_data = coordinator.data

                charger_states[entry_id] = {
                    "state": charger_data.get("state"),
                    "power_kw": charger_data.get("power_kw", 0),
                    "max_curr": charger_data.get("max_curr", 0),
                    "serial": charger_data.get("serial"),
                }

                power = charger_data.get("power_kw", 0) or 0
                session_energy = charger_data.get("energy_present_kwh", 0) or 0
                total_energy_charger = charger_data.get("energy_total_kwh", 0) or 0
                state = charger_data.get("state")

                total_power += power
                total_session_energy += session_energy
                total_energy += total_energy_charger

                if state == 3:
                    active_chargers += 1

            distribution = self._calculate_distribution(charger_states)
            is_balancing = self._is_load_balancing_active(active_chargers)

            return {
                "total_power": total_power,
                "total_session_energy": total_session_energy,
                "total_energy": total_energy,
                "active_chargers": active_chargers,
                "charger_states": charger_states,
                "distribution": distribution,
                "max_current": self._max_current,
                "strategy": self._strategy,
                "is_load_balancing_active": is_balancing,
            }

        except Exception as err:
            _LOGGER.error("Failed to update charging coordinator data: %s", err, exc_info=True)
            raise UpdateFailed(f"Error updating coordinator: {err}") from err

    def _calculate_distribution(self, charger_states: dict[str, Any]) -> str:
        """Calculate current distribution description."""
        if self._strategy == COORDINATOR_STRATEGY_OFF:
            return "Off - No load balancing"

        active_chargers = [
            entry_id for entry_id, state in charger_states.items()
            if state.get("state") == 3
        ]

        num_active = len(active_chargers)

        if num_active == 0:
            return f"{self._max_current}A available"

        if self._strategy == COORDINATOR_STRATEGY_EQUAL:
            per_charger = int(self._max_current / num_active)
            if num_active == 1:
                return f"{self._max_current}A available, {per_charger}A to charger"
            else:
                return f"{self._max_current}A available, {per_charger}A per charger"

        return "Unknown strategy"

    def _is_load_balancing_active(self, active_chargers_count: int) -> bool:
        """Check if load balancing is currently active."""
        if self._strategy == COORDINATOR_STRATEGY_OFF:
            return False

        return active_chargers_count >= 2

    async def _apply_load_balancing(self) -> None:
        """Apply load balancing based on current strategy."""
        if self._strategy == COORDINATOR_STRATEGY_OFF:
            return

        try:
            charger_states = {}
            for entry_id in self._charger_entry_ids:
                if entry_id not in self.hass.data.get(DOMAIN, {}):
                    _LOGGER.debug("Charger entry %s not found during load balancing, skipping", entry_id)
                    continue

                entry_data = self.hass.data[DOMAIN][entry_id]
                if "coordinator" not in entry_data or "client" not in entry_data:
                    _LOGGER.debug("Charger entry %s missing coordinator or client, skipping", entry_id)
                    continue

                coordinator = entry_data["coordinator"]
                if not coordinator.data:
                    _LOGGER.debug("Charger entry %s has no data during load balancing, skipping", entry_id)
                    continue

                charger_data = coordinator.data
                charger_states[entry_id] = {
                    "state": charger_data.get("state"),
                    "client": entry_data["client"],
                }

            active_chargers = {
                entry_id: data
                for entry_id, data in charger_states.items()
                if data.get("state") == 3
            }

            num_active = len(active_chargers)

            if num_active == 0:
                await self._restore_all_chargers_to_user_limits(charger_states)
            elif num_active == 1:
                await self._restore_all_chargers_to_user_limits(charger_states)
            elif self._strategy == COORDINATOR_STRATEGY_EQUAL:
                await self._apply_equal_strategy(active_chargers)

            await self.async_request_refresh()

        except Exception as err:
            _LOGGER.error("Failed to apply load balancing: %s", err, exc_info=True)

    async def _restore_all_chargers_to_user_limits(self, charger_states: dict[str, Any]) -> None:
        """Restore all chargers to their user-configured current limits."""
        for entry_id, data in charger_states.items():
            client = data["client"]
            entry_data = self.hass.data[DOMAIN].get(entry_id, {})
            config_entry = entry_data.get("config_entry")

            if not config_entry:
                _LOGGER.debug("No config entry found for %s, skipping restore", entry_id)
                continue

            user_limit = config_entry.options.get("current_limit")
            if user_limit is None:
                _LOGGER.debug("No user current_limit found for %s, skipping restore", entry_id)
                continue

            user_limit_ma = int(user_limit * 1000)

            coordinator = entry_data.get("coordinator")
            charger_hw_limit_ma = 63000
            if coordinator and coordinator.data:
                curr_hw = coordinator.data.get("curr_hw")
                if curr_hw is not None:
                    charger_hw_limit_ma = curr_hw

            actual_current_ma = min(user_limit_ma, charger_hw_limit_ma)

            try:
                await client.set_current(actual_current_ma)
                _LOGGER.debug(
                    "Restored charger %s to user limit %d mA",
                    client.ip_address,
                    actual_current_ma
                )

                message = f"User {int(actual_current_ma / 1000)}A"
                await self._send_display_message(client, message)

            except Exception as err:
                _LOGGER.error(
                    "Failed to restore charger %s to user limit: %s",
                    client.ip_address,
                    err
                )

    async def _apply_equal_strategy(self, active_chargers: dict[str, Any]) -> None:
        """Apply equal distribution strategy."""
        min_current_ma = 6000
        available_current_ma = self._max_current * 1000
        num_chargers = len(active_chargers)

        min_total_required = min_current_ma * num_chargers

        if available_current_ma < min_total_required:
            _LOGGER.warning(
                "Insufficient current: %d mA available, but %d chargers need minimum %d mA total (6A each). "
                "Load balancing cannot proceed safely.",
                available_current_ma,
                num_chargers,
                min_total_required
            )
            return

        per_charger_ma = int(available_current_ma / num_chargers)
        per_charger_ma = max(min_current_ma, per_charger_ma)

        per_charger_a = per_charger_ma / 1000

        for entry_id, data in active_chargers.items():
            client = data["client"]

            entry_data = self.hass.data[DOMAIN].get(entry_id, {})
            coordinator = entry_data.get("coordinator")

            charger_hw_limit_ma = 63000

            if coordinator and coordinator.data:
                curr_hw = coordinator.data.get("curr_hw")
                if curr_hw is not None:
                    charger_hw_limit_ma = curr_hw

            actual_current_ma = min(per_charger_ma, charger_hw_limit_ma)

            limit_reason = "LoadBal"
            if actual_current_ma == charger_hw_limit_ma and actual_current_ma < per_charger_ma:
                limit_reason = "HW Limit"

            _LOGGER.debug(
                "Charger %s: requested=%d mA, hw_limit=%d mA, actual=%d mA (%s)",
                client.ip_address,
                per_charger_ma,
                charger_hw_limit_ma,
                actual_current_ma,
                limit_reason
            )

            try:
                await client.set_current(actual_current_ma)
                _LOGGER.debug(
                    "Set charger %s to %d mA (equal distribution)",
                    client.ip_address,
                    actual_current_ma
                )

                message = f"{limit_reason} {int(actual_current_ma / 1000)}A"
                await self._send_display_message(client, message)

            except Exception as err:
                _LOGGER.error(
                    "Failed to set current for charger %s: %s",
                    client.ip_address,
                    err
                )


    async def set_max_current(self, current: int) -> None:
        """Update maximum available current."""
        self._max_current = current
        await self._apply_load_balancing()

    async def set_strategy(self, strategy: str) -> None:
        """Update load balancing strategy."""
        self._strategy = strategy
        await self._apply_load_balancing()

    async def _send_display_message(self, client, message: str) -> None:
        """Send a message to charger display, truncating if necessary."""
        if len(message) > MAX_DISPLAY_LENGTH:
            message = message[:MAX_DISPLAY_LENGTH]

        try:
            await client.display_text(message)
            _LOGGER.debug("Sent display message: %s", message)
        except Exception as err:
            _LOGGER.debug("Failed to send display message: %s", err)

    @property
    def charger_entry_ids(self) -> list[str]:
        """Return the list of managed charger entry IDs."""
        return self._charger_entry_ids

    @property
    def max_current(self) -> int:
        """Return the maximum current setting."""
        return self._max_current

    @property
    def strategy(self) -> str:
        """Return the current strategy."""
        return self._strategy
