"""Support for Keba KeContact display notifications."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import BaseNotificationService, NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_DISPLAY_LENGTH = 23


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact notify based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device_info = data["device_info"]
    client = data["client"]

    entities = [
        KebaNotifyEntity(coordinator, entry, device_info, client)
    ]

    async_add_entities(entities)


class KebaNotifyEntity(CoordinatorEntity, NotifyEntity):
    """Notify entity for Keba charger display."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info,
        client,
    ) -> None:
        """Initialize the notify entity."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_display"
        self._attr_name = "Display"
        self._client = client

    async def async_send_message(self, message: str = "", **kwargs: Any) -> None:
        """Send a message to the charger display."""
        if not message:
            raise ServiceValidationError("Message cannot be empty")

        if len(message) > MAX_DISPLAY_LENGTH:
            _LOGGER.warning(
                "Message too long (%d chars), truncating to %d: %s",
                len(message),
                MAX_DISPLAY_LENGTH,
                message
            )
            message = message[:MAX_DISPLAY_LENGTH]

        try:
            await self._client.display_text(message)
            _LOGGER.debug("Sent message to display: %s", message)
        except Exception as err:
            _LOGGER.error("Failed to send message to display: %s", err)
            raise ServiceValidationError(
                f"Failed to send message to display: {err}"
            ) from err
