"""Support for Keba Charging Coordinator binary sensors."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up Keba Charging Coordinator binary sensor based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") != "charging_coordinator":
        return

    coordinator: KebaChargingCoordinator = data["coordinator"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"coordinator_{coordinator.name}")},
        name=f"Keba Charging Coordinator - {coordinator.name}",
        manufacturer="Keba",
        model="Charging Coordinator",
    )

    entities = [
        CoordinatorLoadBalancingActiveSensor(coordinator, entry, device_info),
    ]

    async_add_entities(entities)


class CoordinatorLoadBalancingActiveSensor(
    CoordinatorEntity[KebaChargingCoordinator], BinarySensorEntity
):
    """Binary sensor showing if load balancing is currently active."""

    _attr_icon = "mdi:scale-balance"

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_load_balancing_active"
        self._attr_name = "Load Balancing Active"

    @property
    def is_on(self) -> bool | None:
        """Return true if load balancing is active."""
        return self.coordinator.data.get("is_load_balancing_active", False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
