"""Support for Keba KeContact button entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from keba_kecontact.client import KebaClient

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
    client: KebaClient = data["client"]
    ip_address: str = data["ip_address"]

    coordinator = None
    for platform_data in hass.data[DOMAIN].values():
        if isinstance(platform_data, dict) and "client" in platform_data:
            if platform_data["client"] == client:
                for entity_list in hass.data.get("entity_platform", {}).values():
                    for entity in entity_list:
                        if hasattr(entity, "coordinator") and isinstance(
                            entity.coordinator, KebaDataUpdateCoordinator
                        ):
                            coordinator = entity.coordinator
                            break

    if coordinator is None:
        from .sensor import KebaDataUpdateCoordinator

        coordinator = KebaDataUpdateCoordinator(hass, client)
        await coordinator.async_config_entry_first_refresh()

    device_info = DeviceInfo(
        identifiers={(DOMAIN, ip_address)},
        name=f"Keba KeContact {ip_address}",
        manufacturer="Keba",
        model=coordinator.data.get("product", "KeContact"),
        sw_version=coordinator.data.get("firmware"),
        serial_number=coordinator.data.get("serial"),
    )

    entities = [
        KebaStartChargingButton(coordinator, entry, device_info, client),
        KebaStopChargingButton(coordinator, entry, device_info, client),
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
        self._attr_name = "Start Charging"
        self._attr_icon = "mdi:play"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._client.start_charging()
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to start charging: %s", err)
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
        self._attr_name = "Stop Charging"
        self._attr_icon = "mdi:stop"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._client.stop_charging()
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to stop charging: %s", err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success
