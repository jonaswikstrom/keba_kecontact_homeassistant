"""Support for Keba KeContact lock (authentication control)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_RFID, CONF_RFID_CLASS

_LOGGER = logging.getLogger(__name__)

LOCK_DESCRIPTION = LockEntityDescription(
    key="authentication",
    name="Authentication",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact lock based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device_info = data["device_info"]
    client = data["client"]

    rfid_tag = entry.options.get(CONF_RFID, entry.data.get(CONF_RFID))
    rfid_class = entry.options.get(CONF_RFID_CLASS, entry.data.get(CONF_RFID_CLASS))

    if not coordinator.data.get("auth_required"):
        _LOGGER.debug(
            "Authentication not required for %s, skipping lock entity",
            client.ip_address
        )
        return

    entities = [
        KebaLock(
            coordinator,
            entry,
            device_info,
            client,
            LOCK_DESCRIPTION,
            rfid_tag,
            rfid_class,
        )
    ]

    async_add_entities(entities)


class KebaLock(CoordinatorEntity, LockEntity):
    """Lock entity for Keba charger authentication control."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info,
        client,
        description: LockEntityDescription,
        rfid_tag: str | None = None,
        rfid_class: str | None = None,
    ) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._client = client
        self._rfid_tag = rfid_tag or "00000000"
        self._rfid_class = rfid_class or "00000000000000000000"

    @property
    def is_locked(self) -> bool:
        """Return true if the lock is locked."""
        state = self.coordinator.data.get("state")
        if state is None:
            return True
        return state in [0, 1, 2]

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the charger (stop charging session)."""
        try:
            await self._client.stop_charging()
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to lock charger: %s", err)
            raise

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the charger (start charging session with RFID)."""
        try:
            if self._rfid_tag and self._rfid_class:
                command = f"start {self._rfid_tag} {self._rfid_class}"
                await self._client.send_command(command)
            else:
                await self._client.start_charging()

            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to unlock charger: %s", err)
            raise
