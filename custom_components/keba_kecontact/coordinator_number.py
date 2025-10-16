"""Support for Keba Charging Coordinator number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import KebaChargingCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba Charging Coordinator number based on a config entry."""
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
        CoordinatorMaxCurrentNumber(coordinator, entry, device_info),
    ]

    async_add_entities(entities)


class CoordinatorMaxCurrentNumber(NumberEntity):
    """Number entity for setting maximum available current."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 6.0
    _attr_native_max_value = 63.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_max_current"
        self._attr_has_entity_name = True
        self._attr_name = "Max Current"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return float(self._coordinator.max_current)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        _LOGGER.debug("Setting coordinator max current to %.1f A", value)
        try:
            await self._coordinator.set_max_current(int(value))

            from .const import CONF_COORDINATOR_MAX_CURRENT
            new_options = {**self._entry.options, CONF_COORDINATOR_MAX_CURRENT: int(value)}
            self.hass.config_entries.async_update_entry(
                self._entry, options=new_options
            )

            _LOGGER.info("Set coordinator max current to %.1f A and persisted to config", value)
        except Exception as err:
            _LOGGER.error("Failed to set coordinator max current to %.1f A: %s", value, err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success
