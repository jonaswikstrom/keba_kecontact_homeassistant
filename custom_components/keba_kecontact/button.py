"""Support for Keba KeContact button entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .keba_kecontact.client import KebaClient

from .const import DOMAIN
from .sensor import KebaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact button based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") == "charging_coordinator":
        return

    coordinator = data["coordinator"]
    device_info = data["device_info"]
    client: KebaClient = data["client"]

    entities = [
        KebaStartChargingButton(coordinator, entry, device_info, client),
        KebaStopChargingButton(coordinator, entry, device_info, client),
        KebaUnlockSocketButton(coordinator, entry, device_info, client),
    ]

    async_add_entities(entities)


class KebaStartChargingButton(ButtonEntity):
    """Button to start charging session."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        client: KebaClient,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._client = client
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_start_charging"
        self._attr_has_entity_name = True
        self._attr_name = "Start Charging"
        self._attr_icon = "mdi:play"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Starting charging session on %s", self._client.ip_address)
        try:
            await self._client.start_charging()
            _LOGGER.info("Started charging session on %s", self._client.ip_address)
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to start charging on %s: %s", self._client.ip_address, err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success


class KebaStopChargingButton(ButtonEntity):
    """Button to stop charging session."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        client: KebaClient,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._client = client
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_stop_charging"
        self._attr_has_entity_name = True
        self._attr_name = "Stop Charging"
        self._attr_icon = "mdi:stop"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Stopping charging session on %s", self._client.ip_address)
        try:
            await self._client.stop_charging()
            _LOGGER.info("Stopped charging session on %s", self._client.ip_address)
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to stop charging on %s: %s", self._client.ip_address, err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success


class KebaUnlockSocketButton(ButtonEntity):
    """Button to unlock the socket and release the cable."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        client: KebaClient,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._client = client
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_unlock_socket"
        self._attr_has_entity_name = True
        self._attr_name = "Unlock Socket"
        self._attr_icon = "mdi:lock-open-variant"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Unlocking socket on %s", self._client.ip_address)
        try:
            await self._client.unlock_socket()
            _LOGGER.info("Unlocked socket on %s", self._client.ip_address)
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to unlock socket on %s: %s", self._client.ip_address, err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success
