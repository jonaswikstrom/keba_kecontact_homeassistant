"""Support for Keba KeContact number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
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
    """Set up Keba KeContact number based on a config entry."""
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
        KebaCurrentLimitNumber(coordinator, entry, device_info, client),
    ]

    async_add_entities(entities)


class KebaCurrentLimitNumber(NumberEntity):
    """Number entity for setting current limit."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 6.0
    _attr_native_max_value = 32.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        client: KebaClient,
    ) -> None:
        """Initialize the number entity."""
        self._coordinator = coordinator
        self._client = client
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_current_limit"
        self._attr_name = "Current Limit"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        max_curr = self._coordinator.data.get("max_curr")
        if max_curr is None:
            return None
        return max_curr / 1000.0

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            milliamps = int(value * 1000)
            await self._client.set_current(milliamps)
            await self._coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set current limit: %s", err)
            raise

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._coordinator.last_update_success
