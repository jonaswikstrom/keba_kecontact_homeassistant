"""Support for Keba KeContact sensors."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from keba_kecontact.client import KebaClient

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Keba KeContact sensor based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client: KebaClient = data["client"]
    ip_address: str = data["ip_address"]

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
        KebaPowerSensor(coordinator, entry, device_info),
        KebaSessionEnergySensor(coordinator, entry, device_info),
        KebaTotalEnergySensor(coordinator, entry, device_info),
        KebaStateSensor(coordinator, entry, device_info),
        KebaPlugSensor(coordinator, entry, device_info),
        KebaCurrent1Sensor(coordinator, entry, device_info),
        KebaCurrent2Sensor(coordinator, entry, device_info),
        KebaCurrent3Sensor(coordinator, entry, device_info),
        KebaVoltage1Sensor(coordinator, entry, device_info),
        KebaVoltage2Sensor(coordinator, entry, device_info),
        KebaVoltage3Sensor(coordinator, entry, device_info),
        KebaMaxCurrentSensor(coordinator, entry, device_info),
    ]

    async_add_entities(entities)


class KebaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Keba data."""

    def __init__(self, hass: HomeAssistant, client: KebaClient) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Keba charger."""
        _LOGGER.debug("Polling charger %s for updates", self._client.ip_address)
        try:
            report1 = await self._client.get_report_1()
            report2 = await self._client.get_report_2()
            report3 = await self._client.get_report_3()

            data = {
                "product": report1.product,
                "serial": report1.serial,
                "firmware": report1.firmware,
                "state": report2.state,
                "plug": report2.plug,
                "enable_sys": report2.enable_sys,
                "enable_user": report2.enable_user,
                "max_curr": report2.max_curr,
                "power_kw": report3.power_kw,
                "energy_present_kwh": report3.energy_present_kwh,
                "energy_total_kwh": report3.energy_total_kwh,
                "u1": report3.u1,
                "u2": report3.u2,
                "u3": report3.u3,
                "i1": report3.i1,
                "i2": report3.i2,
                "i3": report3.i3,
            }

            _LOGGER.debug(
                "Charger %s: state=%s, plug=%s, power=%.2f kW, session_energy=%.2f kWh",
                self._client.ip_address,
                report2.state,
                report2.plug,
                report3.power_kw or 0,
                report3.energy_present_kwh or 0,
            )

            return data
        except Exception as err:
            _LOGGER.error(
                "Failed to update charger %s: %s",
                self._client.ip_address,
                err,
                exc_info=True,
            )
            raise UpdateFailed(f"Error communicating with charger: {err}") from err


class KebaBaseSensor(CoordinatorEntity[KebaDataUpdateCoordinator], SensorEntity):
    """Base class for Keba sensors."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._entry = entry


class KebaPowerSensor(KebaBaseSensor):
    """Sensor for current power consumption."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_name = "Power"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("power_kw")


class KebaSessionEnergySensor(KebaBaseSensor):
    """Sensor for current session energy."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_session_energy"
        self._attr_name = "Session Energy"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("energy_present_kwh")


class KebaTotalEnergySensor(KebaBaseSensor):
    """Sensor for total energy."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_total_energy"
        self._attr_name = "Total Energy"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("energy_total_kwh")


class KebaStateSensor(KebaBaseSensor):
    """Sensor for charger state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["starting", "not_ready", "ready", "charging", "error", "auth_rejected"]

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_state"
        self._attr_name = "State"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        state = self.coordinator.data.get("state")
        if state is None:
            return None

        state_map = {
            0: "starting",
            1: "not_ready",
            2: "ready",
            3: "charging",
            4: "error",
            5: "auth_rejected",
        }
        return state_map.get(state, f"unknown_{state}")


class KebaPlugSensor(KebaBaseSensor):
    """Sensor for plug connection status."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "unplugged",
        "plugged_station",
        "plugged_station_locked",
        "plugged_station_ev",
        "plugged_station_ev_locked",
    ]

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_plug"
        self._attr_name = "Plug Status"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        plug = self.coordinator.data.get("plug")
        if plug is None:
            return None

        plug_map = {
            0: "unplugged",
            1: "plugged_station",
            3: "plugged_station_locked",
            5: "plugged_station_ev",
            7: "plugged_station_ev_locked",
        }
        return plug_map.get(plug, f"unknown_{plug}")


class KebaCurrent1Sensor(KebaBaseSensor):
    """Sensor for phase 1 current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_1"
        self._attr_name = "Current Phase 1"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        i1 = self.coordinator.data.get("i1")
        return i1 / 1000.0 if i1 is not None else None


class KebaCurrent2Sensor(KebaBaseSensor):
    """Sensor for phase 2 current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_2"
        self._attr_name = "Current Phase 2"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        i2 = self.coordinator.data.get("i2")
        return i2 / 1000.0 if i2 is not None else None


class KebaCurrent3Sensor(KebaBaseSensor):
    """Sensor for phase 3 current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_3"
        self._attr_name = "Current Phase 3"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        i3 = self.coordinator.data.get("i3")
        return i3 / 1000.0 if i3 is not None else None


class KebaVoltage1Sensor(KebaBaseSensor):
    """Sensor for phase 1 voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_voltage_1"
        self._attr_name = "Voltage Phase 1"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("u1")


class KebaVoltage2Sensor(KebaBaseSensor):
    """Sensor for phase 2 voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_voltage_2"
        self._attr_name = "Voltage Phase 2"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("u2")


class KebaVoltage3Sensor(KebaBaseSensor):
    """Sensor for phase 3 voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_voltage_3"
        self._attr_name = "Voltage Phase 3"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("u3")


class KebaMaxCurrentSensor(KebaBaseSensor):
    """Sensor for maximum current setting."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_max_current"
        self._attr_name = "Max Current"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        max_curr = self.coordinator.data.get("max_curr")
        return max_curr / 1000.0 if max_curr is not None else None
