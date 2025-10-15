"""Support for Keba KeContact display notifications."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.notify import (
    ATTR_DATA,
    BaseNotificationService,
    NotifyEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MAX_DISPLAY_LENGTH = 23
ATTR_DURATION = "duration"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact notify based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") == "charging_coordinator":
        return

    coordinator = data["coordinator"]
    device_info = data["device_info"]
    client = data["client"]

    entities = [
        KebaNotifyEntity(coordinator, entry, device_info, client)
    ]

    async_add_entities(entities)


class KebaNotifyEntity(CoordinatorEntity, NotifyEntity):
    """Notify entity for Keba charger display."""

    _attr_supported_features = 0

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
        self._attr_has_entity_name = True
        self._attr_name = "Display"
        self._client = client

    async def async_send_message(self, message: str = "", **kwargs: Any) -> None:
        """Send a message to the charger display.

        Optional data parameters:
        - min_time: Minimum time in seconds to show message (default: 2)
        - max_time: Maximum time in seconds to show message (default: 10)
        """
        if not message:
            raise ServiceValidationError("Message cannot be empty")

        text = message.replace(" ", "$")

        if len(text) > MAX_DISPLAY_LENGTH:
            _LOGGER.warning(
                "Message too long (%d chars), truncating to %d: %s",
                len(text),
                MAX_DISPLAY_LENGTH,
                text
            )
            text = text[:MAX_DISPLAY_LENGTH]

        data = kwargs.get(ATTR_DATA) or {}
        min_time = int(data.get("min_time", 2))
        max_time = int(data.get("max_time", 10))

        # [a] parameter: 0 = use defaults, 1 = use custom min/max times
        # Format: display [a] [min] [max] [tk] [text]
        # When a=0, min and max are ignored and defaults (2s, 10s) are used
        # When a=1, custom min and max times are used
        use_custom_time = 1 if ("min_time" in data or "max_time" in data) else 0

        command = f"display {use_custom_time} {min_time} {max_time} 0 {text}"

        try:
            _LOGGER.info(
                "Sending display command: '%s' (original message: '%s')",
                command,
                message
            )
            await self._client.send_command(command)
            _LOGGER.info("Display command sent successfully")
        except Exception as err:
            _LOGGER.error("Failed to send message to display: %s", err)
            raise ServiceValidationError(
                f"Failed to send message to display: {err}"
            ) from err
