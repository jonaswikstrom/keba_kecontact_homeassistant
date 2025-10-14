"""Support for Keba KeContact binary sensors."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLUG_UNPLUGGED = 0
PLUG_STATION = 1
PLUG_STATION_LOCKED = 3
PLUG_STATION_EV = 5
PLUG_STATION_EV_LOCKED = 7

STATE_CHARGING = 3


@dataclass
class KebaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Keba binary sensor entity."""

    value_fn: Callable[[dict], bool | None] = lambda data: None


def _is_plugged_on_ev(data: dict) -> bool | None:
    """Check if cable is plugged to EV."""
    plug = data.get("plug")
    return plug in [PLUG_STATION_EV, PLUG_STATION_EV_LOCKED] if plug is not None else None


def _is_charging(data: dict) -> bool | None:
    """Check if currently charging."""
    state = data.get("state")
    return state == STATE_CHARGING if state is not None else None


def _is_enable_user(data: dict) -> bool | None:
    """Check if user enable is active."""
    enable_user = data.get("enable_user")
    return enable_user == 1 if enable_user is not None else None


def _is_cable_plugged_station(data: dict) -> bool | None:
    """Check if cable is plugged to station."""
    plug = data.get("plug")
    return plug != PLUG_UNPLUGGED if plug is not None else None


def _is_cable_locked(data: dict) -> bool | None:
    """Check if cable is locked."""
    plug = data.get("plug")
    return plug in [PLUG_STATION_LOCKED, PLUG_STATION_EV_LOCKED] if plug is not None else None


def _is_enable_sys(data: dict) -> bool | None:
    """Check if system enable is active."""
    enable_sys = data.get("enable_sys")
    return enable_sys == 1 if enable_sys is not None else None


def _is_failsafe_mode(data: dict) -> bool | None:
    """Check if failsafe mode is active."""
    return data.get("failsafe_mode")


def _is_authreq(data: dict) -> bool | None:
    """Check if authentication is required."""
    return data.get("authreq")


def _is_authon(data: dict) -> bool | None:
    """Check if authentication is enabled."""
    return data.get("authon")


def _is_x2_phase_switch(data: dict) -> bool | None:
    """Check X2 phase switch status."""
    return data.get("x2_phase_switch")


BINARY_SENSOR_TYPES: tuple[KebaBinarySensorEntityDescription, ...] = (
    KebaBinarySensorEntityDescription(
        key="plugged_on_ev",
        name="Plugged on EV",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_is_plugged_on_ev,
    ),
    KebaBinarySensorEntityDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_is_charging,
    ),
    KebaBinarySensorEntityDescription(
        key="enable_user",
        name="Enable User",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_is_enable_user,
    ),
    KebaBinarySensorEntityDescription(
        key="cable_plugged_station",
        name="Cable Plugged on Station",
        device_class=BinarySensorDeviceClass.PLUG,
        entity_registry_enabled_default=False,
        value_fn=_is_cable_plugged_station,
    ),
    KebaBinarySensorEntityDescription(
        key="cable_locked",
        name="Cable Locked",
        device_class=BinarySensorDeviceClass.LOCK,
        entity_registry_enabled_default=False,
        value_fn=_is_cable_locked,
    ),
    KebaBinarySensorEntityDescription(
        key="enable_sys",
        name="Enable System",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_is_enable_sys,
    ),
    KebaBinarySensorEntityDescription(
        key="failsafe_mode",
        name="Failsafe Mode",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=_is_failsafe_mode,
    ),
    KebaBinarySensorEntityDescription(
        key="authreq",
        name="Authentication Required",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_is_authreq,
    ),
    KebaBinarySensorEntityDescription(
        key="authon",
        name="Authentication Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_is_authon,
    ),
    KebaBinarySensorEntityDescription(
        key="x2_phase_switch",
        name="X2 Phase Switch",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_is_x2_phase_switch,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact binary sensor based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]

    if data.get("type") == "charging_coordinator":
        from .coordinator_binary_sensor import async_setup_entry as async_setup_coordinator_binary_sensors
        return await async_setup_coordinator_binary_sensors(hass, entry, async_add_entities)

    coordinator = data["coordinator"]
    device_info = data["device_info"]

    entities = [
        KebaBinarySensor(coordinator, entry, device_info, description)
        for description in BINARY_SENSOR_TYPES
    ]

    async_add_entities(entities)


class KebaBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for Keba charger."""

    entity_description: KebaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info,
        description: KebaBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.value_fn(self.coordinator.data)
