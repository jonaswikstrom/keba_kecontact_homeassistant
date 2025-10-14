"""Support for Keba KeContact diagnostic sensors."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfTime,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


class KebaDiagnosticBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Keba diagnostic sensors."""

    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._entry = entry


class KebaRFIDTagSensor(KebaDiagnosticBaseSensor):
    """Sensor for RFID tag."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_rfid_tag"
        self._attr_name = "RFID Tag"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("rfid_tag")


class KebaRFIDClassSensor(KebaDiagnosticBaseSensor):
    """Sensor for RFID class."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_rfid_class"
        self._attr_name = "RFID Class"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("rfid_class")


class KebaPowerFactorSensor(KebaDiagnosticBaseSensor):
    """Sensor for power factor."""

    _attr_icon = "mdi:angle-acute"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_power_factor"
        self._attr_name = "Power Factor"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        pf = self.coordinator.data.get("pf")
        return pf / 1000.0 if pf is not None else None


class KebaMaxCurrentPercentSensor(KebaDiagnosticBaseSensor):
    """Sensor for maximum current percent."""

    _attr_native_unit_of_measurement = "%"
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_max_current_percent"
        self._attr_name = "Maximum Current %"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        max_curr_percent = self.coordinator.data.get("max_curr_percent")
        return max_curr_percent / 10.0 if max_curr_percent is not None else None


class KebaCurrentHWSensor(KebaDiagnosticBaseSensor):
    """Sensor for current hardware limit."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_hw"
        self._attr_name = "Current Hardware"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        curr_hw = self.coordinator.data.get("curr_hw")
        return curr_hw / 1000.0 if curr_hw is not None else None


class KebaCurrentTimerSensor(KebaDiagnosticBaseSensor):
    """Sensor for planned current."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_current_timer"
        self._attr_name = "Planned Current"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        curr_timer = self.coordinator.data.get("curr_timer")
        return curr_timer / 1000.0 if curr_timer is not None else None


class KebaTmoCTSensor(KebaDiagnosticBaseSensor):
    """Sensor for time until planned current."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_tmo_ct"
        self._attr_name = "Time Until Planned Current"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("tmo_ct")


class KebaOutputSensor(KebaDiagnosticBaseSensor):
    """Sensor for output status."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_output"
        self._attr_name = "Output"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("output")


class KebaInputSensor(KebaDiagnosticBaseSensor):
    """Sensor for input status."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_input"
        self._attr_name = "Input"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("input")


class KebaError1Sensor(KebaDiagnosticBaseSensor):
    """Sensor for error code 1."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_error1"
        self._attr_name = "Error 1"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("error_1")


class KebaError2Sensor(KebaDiagnosticBaseSensor):
    """Sensor for error code 2."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_error2"
        self._attr_name = "Error 2"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("error_2")


class KebaStateRawSensor(KebaDiagnosticBaseSensor):
    """Sensor for raw state value."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_state_raw"
        self._attr_name = "State (Raw)"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("state")


class KebaPlugRawSensor(KebaDiagnosticBaseSensor):
    """Sensor for raw plug value."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_plug_raw"
        self._attr_name = "Plug (Raw)"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("plug")


class KebaEnableSysRawSensor(KebaDiagnosticBaseSensor):
    """Sensor for raw enable sys value."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_enable_sys_raw"
        self._attr_name = "Enable Sys (Raw)"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("enable_sys")


class KebaEnableUserRawSensor(KebaDiagnosticBaseSensor):
    """Sensor for raw enable user value."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_enable_user_raw"
        self._attr_name = "Enable User (Raw)"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("enable_user")


class KebaSessionIDSensor(KebaDiagnosticBaseSensor):
    """Sensor for session ID."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_session_id"
        self._attr_name = "Session ID"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("session_id")


class KebaEStartSensor(KebaDiagnosticBaseSensor):
    """Sensor for session start energy."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_e_start"
        self._attr_name = "Session Start Energy"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("e_start")


class KebaStartedSensor(KebaDiagnosticBaseSensor):
    """Sensor for session start time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_started"
        self._attr_name = "Session Start Time"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        started = self.coordinator.data.get("started")
        if started:
            try:
                return datetime.fromisoformat(started.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None


class KebaEndedSensor(KebaDiagnosticBaseSensor):
    """Sensor for session end time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_ended"
        self._attr_name = "Session End Time"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        ended = self.coordinator.data.get("ended")
        if ended:
            try:
                return datetime.fromisoformat(ended.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None


class KebaReasonSensor(KebaDiagnosticBaseSensor):
    """Sensor for session end reason."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_reason"
        self._attr_name = "Session End Reason"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("reason")


class KebaUptimeSensor(KebaDiagnosticBaseSensor):
    """Sensor for uptime."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_uptime"
        self._attr_name = "Uptime"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("sec")
