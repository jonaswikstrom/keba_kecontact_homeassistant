"""The Keba KeContact integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .keba_kecontact import KebaClient, KebaUdpManager

from .const import CONF_IP_ADDRESS, DOMAIN

if TYPE_CHECKING:
    from .keba_kecontact.client import KebaClient as KebaClientType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.NOTIFY,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Keba KeContact from a config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]

    manager = KebaUdpManager.get_instance()

    if not manager.is_started:
        try:
            await manager.start()
            _LOGGER.info("Started global Keba UDP manager")
        except Exception as err:
            _LOGGER.error("Failed to start UDP manager: %s", err)
            raise ConfigEntryNotReady(f"Failed to start UDP manager: {err}") from err

    client = KebaClient(ip_address, use_global_handler=True)

    try:
        await client.connect()
        report1 = await client.get_report_1()
        _LOGGER.info(
            "Connected to Keba charger at %s (Serial: %s, Product: %s)",
            ip_address,
            report1.serial,
            report1.product,
        )
    except Exception as err:
        _LOGGER.error("Failed to connect to charger at %s: %s", ip_address, err)
        await client.disconnect()
        raise ConfigEntryNotReady(
            f"Failed to connect to charger at {ip_address}: {err}"
        ) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "manager": manager,
        "ip_address": ip_address,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        client: KebaClientType = data["client"]
        manager: KebaUdpManager = data["manager"]

        await client.disconnect()
        _LOGGER.info("Disconnected from charger at %s", data["ip_address"])

        if manager.client_count == 0:
            await manager.stop()
            _LOGGER.info("Stopped global Keba UDP manager (no more clients)")

    return unload_ok
