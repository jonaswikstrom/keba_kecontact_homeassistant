"""Support for Keba Charging Coordinator select entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import KebaChargingCoordinator
from .const import (
    DOMAIN,
    CONF_CHARGER_PRIORITY,
    COORDINATOR_STRATEGY_OFF,
    COORDINATOR_STRATEGY_EQUAL,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba select entities based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") == "charging_coordinator":
        coordinator: KebaChargingCoordinator = data["coordinator"]

        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"coordinator_{coordinator.name}")},
            name=f"Keba Charging Coordinator - {coordinator.name}",
            manufacturer="Keba",
            model="Charging Coordinator",
        )

        entities = [
            CoordinatorStrategySelect(coordinator, entry, device_info),
        ]

        async_add_entities(entities)
    else:
        device_info = data["device_info"]

        entities = [
            ChargerPrioritySelect(hass, entry, device_info),
        ]

        async_add_entities(entities)


class CoordinatorStrategySelect(SelectEntity):
    """Select entity for choosing load balancing strategy."""

    _attr_options = [
        COORDINATOR_STRATEGY_OFF,
        COORDINATOR_STRATEGY_EQUAL,
    ]

    def __init__(
        self,
        coordinator: KebaChargingCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the select entity."""
        self._coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_strategy"
        self._attr_name = "Strategy"
        self._attr_icon = "mdi:strategy"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._coordinator.strategy

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("Setting coordinator strategy to %s", option)
        try:
            await self._coordinator.set_strategy(option)
            _LOGGER.info("Set coordinator strategy to %s", option)
        except Exception as err:
            _LOGGER.error("Failed to set coordinator strategy to %s: %s", option, err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success


class ChargerPrioritySelect(SelectEntity):
    """Select entity for setting charger priority."""

    _attr_options = [
        PRIORITY_LOW,
        PRIORITY_NORMAL,
        PRIORITY_HIGH,
    ]

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the select entity."""
        self._hass = hass
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_priority"
        self._attr_name = "Priority"
        self._attr_icon = "mdi:priority-high"

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._entry.options.get(CONF_CHARGER_PRIORITY, PRIORITY_NORMAL)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("Setting charger priority to %s", option)
        try:
            new_options = {**self._entry.options, CONF_CHARGER_PRIORITY: option}
            self._hass.config_entries.async_update_entry(
                self._entry, options=new_options
            )
            self.async_write_ha_state()
            _LOGGER.info("Set charger priority to %s", option)
        except Exception as err:
            _LOGGER.error("Failed to set charger priority to %s: %s", option, err)
            raise
