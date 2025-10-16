"""The Keba KeContact integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .keba_kecontact import KebaClient, KebaUdpManager
from .coordinator import KebaChargingCoordinator

from .const import (
    CONF_IP_ADDRESS,
    CONF_COORDINATOR_NAME,
    CONF_COORDINATOR_CHARGERS,
    CONF_COORDINATOR_MAX_CURRENT,
    CONF_COORDINATOR_STRATEGY,
    DOMAIN,
)

if TYPE_CHECKING:
    from .keba_kecontact.client import KebaClient as KebaClientType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.NOTIFY,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Keba KeContact from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if CONF_COORDINATOR_NAME in entry.data:
        return await async_setup_coordinator_entry(hass, entry)
    else:
        return await async_setup_charger_entry(hass, entry)


async def async_setup_charger_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Keba charger from a config entry."""
    from .sensor import KebaDataUpdateCoordinator
    from homeassistant.helpers.entity import DeviceInfo

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

    coordinator = KebaDataUpdateCoordinator(hass, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to fetch initial data from charger at %s: %s", ip_address, err)
        await client.disconnect()
        raise ConfigEntryNotReady(
            f"Failed to fetch initial data from charger at {ip_address}: {err}"
        ) from err

    serial = coordinator.data.get("serial")
    device_name = entry.title if entry.title else f"Keba KeContact {serial}" if serial else f"Keba KeContact {ip_address}"

    device_info = DeviceInfo(
        identifiers={(DOMAIN, ip_address)},
        name=device_name,
        manufacturer="Keba",
        model=coordinator.data.get("product", "KeContact"),
        sw_version=coordinator.data.get("firmware"),
        serial_number=serial,
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "manager": manager,
        "ip_address": ip_address,
        "coordinator": coordinator,
        "device_info": device_info,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    saved_current_limit = entry.options.get("current_limit")
    if saved_current_limit is not None:
        try:
            milliamps = int(saved_current_limit * 1000)
            await client.set_current(milliamps)
            _LOGGER.info(
                "Applied saved Current Limit %.1f A to charger at %s",
                saved_current_limit,
                ip_address
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to apply saved Current Limit to charger at %s: %s",
                ip_address,
                err
            )

    await _check_and_create_coordinator(hass)

    return True


async def _check_and_create_coordinator(hass: HomeAssistant) -> None:
    """Check if we should create a coordinator automatically."""
    charger_entries = []
    coordinator_exists = False

    for entry in hass.config_entries.async_entries(DOMAIN):
        if CONF_IP_ADDRESS in entry.data:
            charger_entries.append(entry)
        elif CONF_COORDINATOR_NAME in entry.data:
            coordinator_exists = True

    if len(charger_entries) >= 2 and not coordinator_exists:
        _LOGGER.info(
            "Found %d chargers without coordinator, creating automatic coordinator",
            len(charger_entries)
        )

        charger_ids = [entry.entry_id for entry in charger_entries]

        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "automatic"},
            data={
                CONF_COORDINATOR_NAME: "Keba Load Balancing",
                CONF_COORDINATOR_CHARGERS: charger_ids,
                CONF_COORDINATOR_MAX_CURRENT: 32,
                CONF_COORDINATOR_STRATEGY: "equal",
            },
        )


async def async_setup_coordinator_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Keba Charging Coordinator from a config entry."""
    from homeassistant.helpers.entity import DeviceInfo

    name = entry.data[CONF_COORDINATOR_NAME]
    charger_entry_ids = entry.data[CONF_COORDINATOR_CHARGERS]
    max_current = entry.options.get(
        CONF_COORDINATOR_MAX_CURRENT,
        entry.data[CONF_COORDINATOR_MAX_CURRENT]
    )
    strategy = entry.options.get(
        CONF_COORDINATOR_STRATEGY,
        entry.data[CONF_COORDINATOR_STRATEGY]
    )

    coordinator = KebaChargingCoordinator(
        hass,
        name,
        charger_entry_ids,
        max_current,
        strategy,
    )

    await coordinator.async_start()

    device_name = entry.title if entry.title else name

    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"coordinator_{name}")},
        name=device_name,
        manufacturer="Keba",
        model="Charging Coordinator",
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "type": "charging_coordinator",
        "config_entry": entry,
        "device_info": device_info,
    }

    entry.async_on_unload(entry.add_update_listener(async_reload_coordinator_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "Set up Keba Charging Coordinator '%s' managing %d chargers",
        name,
        len(charger_entry_ids),
    )

    return True


async def async_reload_coordinator_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload coordinator when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)

        if data.get("type") == "charging_coordinator":
            coordinator: KebaChargingCoordinator = data["coordinator"]
            await coordinator.async_stop()
            _LOGGER.info("Stopped Keba Charging Coordinator")
        else:
            client: KebaClientType = data["client"]
            manager: KebaUdpManager = data["manager"]

            await client.disconnect()
            _LOGGER.info("Disconnected from charger at %s", data["ip_address"])

            if manager.client_count == 0:
                await manager.stop()
                _LOGGER.info("Stopped global Keba UDP manager (no more clients)")

    return unload_ok
