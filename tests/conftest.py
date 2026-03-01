"""Pytest configuration and fixtures for Keba KeContact tests."""
import sys
from types import ModuleType
from unittest.mock import MagicMock


def create_mock_module(name: str) -> ModuleType:
    mock = MagicMock()
    mock.__name__ = name
    return mock


mock_ha = create_mock_module("homeassistant")
mock_ha.core = create_mock_module("homeassistant.core")
mock_ha.core.HomeAssistant = MagicMock
mock_ha.core.callback = lambda f: f
mock_ha.core.Event = MagicMock

mock_ha.config_entries = create_mock_module("homeassistant.config_entries")
mock_ha.config_entries.ConfigEntry = MagicMock

mock_ha.exceptions = create_mock_module("homeassistant.exceptions")
mock_ha.exceptions.ConfigEntryNotReady = Exception

mock_ha.helpers = create_mock_module("homeassistant.helpers")
mock_ha.helpers.event = create_mock_module("homeassistant.helpers.event")
mock_ha.helpers.event.async_track_state_change_event = MagicMock()
mock_ha.helpers.event.async_track_time_interval = MagicMock()

mock_ha.helpers.entity = create_mock_module("homeassistant.helpers.entity")
mock_ha.helpers.entity.DeviceInfo = dict

mock_ha.helpers.entity_platform = create_mock_module("homeassistant.helpers.entity_platform")
mock_ha.helpers.entity_platform.AddEntitiesCallback = MagicMock

mock_ha.helpers.restore_state = create_mock_module("homeassistant.helpers.restore_state")
mock_ha.helpers.restore_state.RestoreEntity = MagicMock

mock_ha.helpers.selector = create_mock_module("homeassistant.helpers.selector")

mock_ha.components = create_mock_module("homeassistant.components")
mock_ha.components.sensor = create_mock_module("homeassistant.components.sensor")
mock_ha.components.sensor.SensorEntity = MagicMock
mock_ha.components.sensor.SensorStateClass = MagicMock()

mock_ha.components.binary_sensor = create_mock_module("homeassistant.components.binary_sensor")
mock_ha.components.binary_sensor.BinarySensorEntity = MagicMock

mock_ha.components.button = create_mock_module("homeassistant.components.button")
mock_ha.components.button.ButtonEntity = MagicMock

mock_ha.components.number = create_mock_module("homeassistant.components.number")
mock_ha.components.number.NumberEntity = MagicMock
mock_ha.components.number.NumberMode = MagicMock()

mock_ha.components.select = create_mock_module("homeassistant.components.select")
mock_ha.components.select.SelectEntity = MagicMock

mock_ha.const = create_mock_module("homeassistant.const")
mock_ha.const.CONF_IP_ADDRESS = "ip_address"
mock_ha.const.UnitOfPower = MagicMock()
mock_ha.const.UnitOfEnergy = MagicMock()
mock_ha.const.UnitOfElectricCurrent = MagicMock()

mock_ha.data_entry_flow = create_mock_module("homeassistant.data_entry_flow")
mock_ha.data_entry_flow.FlowResult = dict

class SubscriptableMock(MagicMock):
    def __class_getitem__(cls, item):
        return cls

mock_ha.helpers.update_coordinator = create_mock_module("homeassistant.helpers.update_coordinator")
mock_ha.helpers.update_coordinator.DataUpdateCoordinator = SubscriptableMock
mock_ha.helpers.update_coordinator.CoordinatorEntity = SubscriptableMock

sys.modules["homeassistant"] = mock_ha
sys.modules["homeassistant.core"] = mock_ha.core
sys.modules["homeassistant.config_entries"] = mock_ha.config_entries
sys.modules["homeassistant.exceptions"] = mock_ha.exceptions
sys.modules["homeassistant.helpers"] = mock_ha.helpers
sys.modules["homeassistant.helpers.event"] = mock_ha.helpers.event
sys.modules["homeassistant.helpers.entity"] = mock_ha.helpers.entity
sys.modules["homeassistant.helpers.entity_platform"] = mock_ha.helpers.entity_platform
sys.modules["homeassistant.helpers.restore_state"] = mock_ha.helpers.restore_state
sys.modules["homeassistant.helpers.selector"] = mock_ha.helpers.selector
sys.modules["homeassistant.helpers.update_coordinator"] = mock_ha.helpers.update_coordinator
sys.modules["homeassistant.components"] = mock_ha.components
sys.modules["homeassistant.components.sensor"] = mock_ha.components.sensor
sys.modules["homeassistant.components.binary_sensor"] = mock_ha.components.binary_sensor
sys.modules["homeassistant.components.button"] = mock_ha.components.button
sys.modules["homeassistant.components.number"] = mock_ha.components.number
sys.modules["homeassistant.components.select"] = mock_ha.components.select
sys.modules["homeassistant.const"] = mock_ha.const
sys.modules["homeassistant.data_entry_flow"] = mock_ha.data_entry_flow

voluptuous_mock = MagicMock()
sys.modules["voluptuous"] = voluptuous_mock
