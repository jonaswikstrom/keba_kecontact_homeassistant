"""Support for Keba Charging Coordinator sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import KebaChargingCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba Charging Coordinator sensor based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") != "charging_coordinator":
        return

    coordinator: KebaChargingCoordinator = data["coordinator"]
    device_info = data["device_info"]

    entities = [
        CoordinatorTotalPowerSensor(coordinator, entry, device_info),
        CoordinatorTotalSessionEnergySensor(coordinator, entry, device_info),
        CoordinatorTotalEnergySensor(coordinator, entry, device_info),
        CoordinatorActiveChargersSensor(coordinator, entry, device_info),
        CoordinatorDistributionSensor(coordinator, entry, device_info),
    ]

    async_add_entities(entities)


class CoordinatorBaseSensor(CoordinatorEntity[KebaChargingCoordinator], SensorEntity):
    """Base class for Keba Charging Coordinator sensors."""

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._entry = entry


class CoordinatorTotalPowerSensor(CoordinatorBaseSensor):
    """Sensor for total power consumption across all chargers."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_total_power"
        self._attr_has_entity_name = True
        self._attr_name = "Total Power"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_power")


class CoordinatorTotalSessionEnergySensor(CoordinatorBaseSensor):
    """Sensor for total session energy across all chargers."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_total_session_energy"
        self._attr_has_entity_name = True
        self._attr_name = "Total Session Energy"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_session_energy")


class CoordinatorTotalEnergySensor(CoordinatorBaseSensor):
    """Sensor for total energy across all chargers."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_total_energy"
        self._attr_has_entity_name = True
        self._attr_name = "Total Energy"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_energy")


class CoordinatorActiveChargersSensor(CoordinatorBaseSensor):
    """Sensor for number of active chargers."""

    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_active_chargers"
        self._attr_has_entity_name = True
        self._attr_name = "Active Chargers"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("active_chargers")


class CoordinatorDistributionSensor(CoordinatorBaseSensor):
    """Sensor for current distribution description."""

    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_distribution"
        self._attr_has_entity_name = True
        self._attr_name = "Current Distribution"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("distribution")
