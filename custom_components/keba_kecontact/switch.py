"""Support for Keba KeContact switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Keba KeContact switch based on a config entry."""
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
        KebaChargerSwitch(coordinator, entry, device_info, client),
    ]

    async_add_entities(entities)


class KebaChargerSwitch(SwitchEntity):
    """Switch to enable/disable charging."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        client: KebaClient,
    ) -> None:
        """Initialize the switch."""
        self._coordinator = coordinator
        self._client = client
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_charging_enabled"
        self._attr_name = "Charging Enabled"

    @property
    def is_on(self) -> bool | None:
        """Return true if charging is enabled."""
        enable_user = self._coordinator.data.get("enable_user")
        if enable_user is None:
            return None
        return enable_user == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on charging."""
        try:
            await self._client.enable()
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to enable charging: %s", err)
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off charging."""
        try:
            await self._client.disable()
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to disable charging: %s", err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success
