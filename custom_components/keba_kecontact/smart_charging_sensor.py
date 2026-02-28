"""Sensors for displaying AI smart charging plans."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import KebaChargingCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_smart_charging_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: KebaChargingCoordinator,
    device_info: DeviceInfo,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up smart charging sensors for a coordinator."""
    entities: list[SensorEntity | BinarySensorEntity] = [
        SmartChargingStatusSensor(coordinator, entry, device_info),
        SmartChargingCostSensor(coordinator, entry, device_info),
        SmartChargingReasoningSensor(coordinator, entry, device_info),
        SmartChargingNextWindowSensor(coordinator, entry, device_info),
        SmartChargingActiveBinarySensor(coordinator, entry, device_info),
    ]

    for charger_entry_id in coordinator.charger_entry_ids:
        charger_data = hass.data.get(DOMAIN, {}).get(charger_entry_id, {})
        charger_entry = charger_data.get("config_entry")
        if charger_entry:
            entities.append(
                ChargerChargingPlanSensor(
                    coordinator, entry, device_info, charger_entry_id, charger_entry.title
                )
            )
            entities.append(
                ChargerChargingRateSensor(
                    coordinator, entry, device_info, charger_entry_id, charger_entry.title
                )
            )

    async_add_entities(entities)


class SmartChargingStatusSensor(RestoreEntity, SensorEntity):
    """Sensor showing smart charging status."""

    _attr_icon = "mdi:robot"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_smart_charging_status"
        self._attr_has_entity_name = True
        self._attr_name = "Smart Charging Status"

    @property
    def native_value(self) -> str:
        """Return the status."""
        if not self._coordinator.smart_charger:
            return "disabled"

        if self._coordinator.smart_charger.active_plans:
            return "active"

        return "waiting"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self._coordinator.smart_charger:
            return {}

        plans = self._coordinator.smart_charger.active_plans
        return {
            "active_plans": len(plans),
            "chargers_with_plans": list(plans.keys()),
        }


class SmartChargingCostSensor(SensorEntity):
    """Sensor showing estimated total charging cost."""

    _attr_icon = "mdi:currency-eur"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_smart_charging_cost"
        self._attr_has_entity_name = True
        self._attr_name = "Estimated Charging Cost"

    @property
    def native_value(self) -> float | None:
        """Return the total estimated cost."""
        if not self._coordinator.smart_charger:
            return None

        plans = self._coordinator.smart_charger.active_plans
        if not plans:
            return None

        total = sum(plan.total_cost for plan in plans.values())
        return round(total, 2)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit."""
        return "EUR"


class SmartChargingReasoningSensor(SensorEntity):
    """Sensor showing AI reasoning for the current plan."""

    _attr_icon = "mdi:head-lightbulb"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_smart_charging_reasoning"
        self._attr_has_entity_name = True
        self._attr_name = "AI Reasoning"

    @property
    def native_value(self) -> str | None:
        """Return the AI reasoning."""
        if not self._coordinator.smart_charger:
            return None

        plans = self._coordinator.smart_charger.active_plans
        if not plans:
            return None

        first_plan = next(iter(plans.values()))
        return first_plan.reasoning[:255] if first_plan.reasoning else None


class SmartChargingNextWindowSensor(SensorEntity):
    """Sensor showing next charging window."""

    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_smart_charging_next_window"
        self._attr_has_entity_name = True
        self._attr_name = "Next Charging Window"

    @property
    def native_value(self) -> str | None:
        """Return the next charging window description."""
        if not self._coordinator.smart_charger:
            return None

        plans = self._coordinator.smart_charger.active_plans
        if not plans:
            return None

        now = datetime.now()
        current_hour = now.hour
        current_date = now.date().isoformat()

        next_windows = []

        for plan in plans.values():
            upcoming_slots = [
                slot for slot in plan.slots
                if slot.current_amps > 0 and (
                    slot.date > current_date or
                    (slot.date == current_date and slot.hour >= current_hour)
                )
            ]

            if upcoming_slots:
                upcoming_slots.sort(key=lambda s: (s.date, s.hour))

                window_start = upcoming_slots[0].hour
                window_end = window_start

                for i, slot in enumerate(upcoming_slots[1:], 1):
                    if slot.hour == window_end + 1 and slot.date == upcoming_slots[i-1].date:
                        window_end = slot.hour
                    else:
                        break

                next_windows.append(f"{window_start:02d}:00-{window_end+1:02d}:00")

        if next_windows:
            return ", ".join(next_windows[:2])

        return None


class SmartChargingActiveBinarySensor(BinarySensorEntity):
    """Binary sensor indicating if AI is currently controlling any charger."""

    _attr_icon = "mdi:robot-outline"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_smart_charging_active"
        self._attr_has_entity_name = True
        self._attr_name = "AI Charging Active"

    @property
    def is_on(self) -> bool:
        """Return if AI charging is active."""
        if not self._coordinator.smart_charger:
            return False

        return len(self._coordinator.smart_charger.active_plans) > 0


class ChargerChargingPlanSensor(RestoreEntity, SensorEntity):
    """Sensor showing the charging plan for a specific charger."""

    _attr_icon = "mdi:ev-plug-type2"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        charger_entry_id: str,
        charger_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._charger_entry_id = charger_entry_id
        self._charger_name = charger_name
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{charger_entry_id}_charging_plan"
        self._attr_has_entity_name = True
        self._attr_name = f"{charger_name} Charging Plan"

    @property
    def native_value(self) -> str:
        """Return plan status."""
        if not self._coordinator.smart_charger:
            return "disabled"

        plan = self._coordinator.smart_charger.get_plan(self._charger_entry_id)
        if plan:
            return plan.status
        return "no_plan"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full plan as attributes."""
        if not self._coordinator.smart_charger:
            return {}

        plan = self._coordinator.smart_charger.get_plan(self._charger_entry_id)
        if not plan:
            return {}

        return {
            "slots": [slot.to_dict() for slot in plan.slots],
            "total_cost": plan.total_cost,
            "reasoning": plan.reasoning,
            "departure_time": plan.departure_time.isoformat(),
            "created_at": plan.created_at.isoformat(),
            "charger_id": self._charger_entry_id,
        }


class ChargerChargingRateSensor(SensorEntity):
    """Sensor showing historical charging rate for a charger."""

    _attr_icon = "mdi:lightning-bolt"
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        charger_entry_id: str,
        charger_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._entry = entry
        self._charger_entry_id = charger_entry_id
        self._charger_name = charger_name
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{charger_entry_id}_charging_rate"
        self._attr_has_entity_name = True
        self._attr_name = f"{charger_name} Charging Rate"

    @property
    def native_value(self) -> float | None:
        """Return historical charging rate."""
        if not self._coordinator.smart_charger:
            return None

        rate = self._coordinator.smart_charger._history_tracker.get_expected_charging_rate(
            self._charger_entry_id
        )
        return round(rate, 1) if rate else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self._coordinator.smart_charger:
            return {}

        tracker = self._coordinator.smart_charger._history_tracker
        sessions = tracker.get_sessions_for_charger(self._charger_entry_id)
        efficiency = tracker.get_charging_efficiency(self._charger_entry_id)

        return {
            "sessions_recorded": len(sessions),
            "efficiency_kwh_per_percent": round(efficiency, 3) if efficiency else None,
        }
