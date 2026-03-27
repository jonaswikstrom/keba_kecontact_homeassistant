"""Tests for the SmartCharger controller."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from custom_components.keba_kecontact.smart_charger import SmartCharger
from custom_components.keba_kecontact.charging_planner import (
    ChargingPlan,
    ChargingSlot,
    ChargerRequirement,
    PriceSlot,
)
from custom_components.keba_kecontact.const import (
    DOMAIN,
    CONF_VEHICLE_SOC_ENTITY,
    CONF_BATTERY_CAPACITY,
    CONF_DEPARTURE_TIME,
    CONF_TARGET_SOC,
)


def _mock_state(value, unit="%", attrs=None):
    state = MagicMock()
    state.state = str(value)
    state.attributes = {"unit_of_measurement": unit}
    if attrs:
        state.attributes.update(attrs)
    return state


def _make_config_entry(soc_entity="sensor.car_soc", battery=80, departure="07:00:00", target_soc=100, current_limit=16):
    entry = MagicMock()
    entry.title = "Garage (12345)"
    entry.options = {
        CONF_VEHICLE_SOC_ENTITY: soc_entity,
        CONF_BATTERY_CAPACITY: battery,
        CONF_DEPARTURE_TIME: departure,
        CONF_TARGET_SOC: target_soc,
        "current_limit": current_limit,
    }
    return entry


def _setup_charger_in_hass(mock_hass, entry_id, config_entry=None, curr_hw=32000, e_pres=100000):
    coordinator = MagicMock()
    coordinator.data = {"curr_hw": curr_hw, "e_pres": e_pres}
    if config_entry is None:
        config_entry = _make_config_entry()
    mock_hass.data[DOMAIN][entry_id] = {
        "coordinator": coordinator,
        "config_entry": config_entry,
        "device_info": {},
    }


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.is_running = True
    hass.data = {DOMAIN: {}}
    hass.config.path = lambda f: f"/tmp/{f}"
    return hass


@pytest.fixture
def charger(mock_hass):
    return SmartCharger(mock_hass, "sensor.nordpool", ["e1"], 32)


class TestSmartChargerInit:
    def test_properties(self, charger):
        assert charger._nordpool_entity_id == "sensor.nordpool"
        assert charger._charger_entry_ids == ["e1"]
        assert charger._max_current == 32
        assert charger._active_plans == {}
        assert charger.last_error is None

    def test_active_plans_returns_copy(self, charger):
        plan = MagicMock()
        charger._active_plans["e1"] = plan
        copy = charger.active_plans
        copy.pop("e1")
        assert "e1" in charger._active_plans

    def test_get_plan_none(self, charger):
        assert charger.get_plan("nonexistent") is None

    def test_get_plan_found(self, charger):
        plan = MagicMock()
        charger._active_plans["e1"] = plan
        assert charger.get_plan("e1") is plan

    def test_clear_error(self, charger):
        charger._last_error = "some error"
        charger.clear_error()
        assert charger.last_error is None


class TestSmartChargerHelpers:
    def test_get_charger_serial(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        assert charger._get_charger_serial("e1") == "12345"

    def test_get_charger_serial_no_config(self, charger, mock_hass):
        assert charger._get_charger_serial("nonexistent") is None

    def test_get_state_entity_id(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        assert charger._get_state_entity_id("e1") == "sensor.keba_kecontact_12345_status"

    def test_get_plugged_on_ev_entity_id(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        assert charger._get_plugged_on_ev_entity_id("e1") == "binary_sensor.keba_kecontact_12345_plugged_on_ev"

    def test_get_entry_id_from_plugged_entity_found(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        assert charger._get_entry_id_from_plugged_entity("binary_sensor.keba_kecontact_12345_plugged_on_ev") == "e1"

    def test_get_entry_id_from_plugged_entity_not_found(self, charger, mock_hass):
        assert charger._get_entry_id_from_plugged_entity("binary_sensor.unknown") is None

    def test_get_entity_state_float_valid(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("42.5")
        assert charger._get_entity_state_float("sensor.x") == 42.5

    def test_get_entity_state_float_unknown(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("unknown")
        assert charger._get_entity_state_float("sensor.x") is None

    def test_get_entity_state_float_unavailable(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("unavailable")
        assert charger._get_entity_state_float("sensor.x") is None

    def test_get_entity_state_float_non_numeric(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("abc")
        assert charger._get_entity_state_float("sensor.x") is None

    def test_get_entity_state_float_none(self, charger, mock_hass):
        mock_hass.states.get.return_value = None
        assert charger._get_entity_state_float("sensor.x") is None

    def test_get_charger_session_energy(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", e_pres=100000)
        assert charger._get_charger_session_energy("e1") == pytest.approx(10.0)

    def test_get_charger_session_energy_no_data(self, charger, mock_hass):
        assert charger._get_charger_session_energy("nonexistent") is None

    def test_get_charger_max_current_hw_limit(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", curr_hw=16000)
        assert charger._get_charger_max_current("e1") == 16

    def test_get_charger_max_current_coord_limit(self, charger, mock_hass):
        charger._max_current = 10
        _setup_charger_in_hass(mock_hass, "e1", curr_hw=32000)
        assert charger._get_charger_max_current("e1") == 10

    def test_get_charger_max_current_no_data(self, charger, mock_hass):
        assert charger._get_charger_max_current("nonexistent") == 32


class TestSocNormalization:
    def test_percent_unchanged(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("75", unit="%")
        assert charger._get_soc_normalized("sensor.soc") == 75.0

    def test_fraction_converted(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("0.75", unit="")
        assert charger._get_soc_normalized("sensor.soc") == 75.0

    def test_value_over_1_treated_as_percent(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("85", unit="")
        assert charger._get_soc_normalized("sensor.soc") == 85.0

    def test_unknown_returns_none(self, charger, mock_hass):
        mock_hass.states.get.return_value = _mock_state("unknown")
        assert charger._get_soc_normalized("sensor.soc") is None

    def test_none_state_returns_none(self, charger, mock_hass):
        mock_hass.states.get.return_value = None
        assert charger._get_soc_normalized("sensor.soc") is None


class TestIsChargerSmartReady:
    def test_all_config_present(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        assert charger._is_charger_smart_ready("e1") is True

    def test_missing_soc(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(soc_entity=None))
        assert charger._is_charger_smart_ready("e1") is False

    def test_missing_battery(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(battery=None))
        assert charger._is_charger_smart_ready("e1") is False

    def test_missing_departure(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(departure=None))
        assert charger._is_charger_smart_ready("e1") is False

    def test_no_config_entry(self, charger, mock_hass):
        assert charger._is_charger_smart_ready("nonexistent") is False


class TestBuildChargerRequirement:
    def test_valid(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("50")

        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 22, 0)
            req = charger._build_charger_requirement("e1")

        assert req is not None
        assert req.charger_id == "e1"
        assert req.current_soc == 50.0
        assert req.battery_capacity_kwh == 80
        assert req.max_current_a == 32

    def test_no_config(self, charger, mock_hass):
        assert charger._build_charger_requirement("nonexistent") is None

    def test_no_soc_entity(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(soc_entity=None))
        assert charger._build_charger_requirement("e1") is None

    def test_soc_unavailable(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("unavailable")
        assert charger._build_charger_requirement("e1") is None

    def test_hw_limit_caps_current(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", curr_hw=16000)
        mock_hass.states.get.return_value = _mock_state("50")

        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 22, 0)
            req = charger._build_charger_requirement("e1")

        assert req.max_current_a == 16


class TestDepartureTime:
    def test_tomorrow_when_past(self, charger):
        now = datetime(2024, 1, 15, 22, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)
        assert result.day == 16
        assert result.hour == 7

    def test_today_when_future(self, charger):
        now = datetime(2024, 1, 15, 5, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)
        assert result.day == 15
        assert result.hour == 7

    def test_invalid_defaults_to_7am_tomorrow(self, charger):
        now = datetime(2024, 1, 15, 22, 0, 0)
        result = charger._parse_departure_time("invalid", now)
        assert result.hour == 7
        assert result.day == 16


class TestPriceMultiplier:
    def test_mwh(self, charger):
        assert charger._get_price_multiplier("EUR/MWh") == 0.001

    def test_ore(self, charger):
        assert charger._get_price_multiplier("öre/kWh") == 0.01

    def test_cent(self, charger):
        assert charger._get_price_multiplier("cent/kWh") == 0.01

    def test_kwh(self, charger):
        assert charger._get_price_multiplier("SEK/kWh") == 1.0

    def test_empty(self, charger):
        assert charger._get_price_multiplier("") == 1.0


class TestGetConnectedChargers:
    def test_returns_connected_smart_ready(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("on")
        result = charger._get_connected_chargers()
        assert result == ["e1"]

    def test_excludes_not_smart_ready(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(soc_entity=None))
        mock_hass.states.get.return_value = _mock_state("on")
        assert charger._get_connected_chargers() == []

    def test_excludes_unplugged(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("off")
        assert charger._get_connected_chargers() == []


class TestCreatePlans:
    def test_creates_and_stores_plan(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")

        def states_side_effect(entity_id):
            if entity_id == "sensor.nordpool":
                return _mock_state("0.30", attrs={
                    "prices_today": [0.30 + i * 0.01 for i in range(24)],
                    "tomorrow_available": False,
                })
            return _mock_state("50")

        mock_hass.states.get.side_effect = states_side_effect

        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 22, 0)
            charger._create_plans_for_chargers(["e1"])

        assert "e1" in charger._active_plans
        assert charger.last_error is None

    def test_no_requirements_sets_error(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1", config_entry=_make_config_entry(soc_entity=None))
        charger._create_plans_for_chargers(["e1"])
        assert charger.last_error is not None

    def test_no_prices_sets_error(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")

        def states_side_effect(entity_id):
            if entity_id == "sensor.nordpool":
                return None
            return _mock_state("50")

        mock_hass.states.get.side_effect = states_side_effect

        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 22, 0)
            charger._create_plans_for_chargers(["e1"])

        assert charger.last_error is not None


class TestApplySlot:
    @pytest.mark.asyncio
    async def test_charges_at_amps(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=60, price=0.30, cost=1.0)

        await charger._apply_slot("e1", slot)

        calls = mock_hass.services.async_call.call_args_list
        assert any(c[0][0] == "number" and c[0][1] == "set_value" for c in calls)
        assert any(c[0][0] == "switch" and c[0][1] == "turn_on" for c in calls)

    @pytest.mark.asyncio
    async def test_zero_amps_pauses(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=0, expected_soc_after=50, price=0.30, cost=0.0)

        await charger._apply_slot("e1", slot)

        calls = mock_hass.services.async_call.call_args_list
        assert any(c[0][0] == "switch" and c[0][1] == "turn_off" for c in calls)

    @pytest.mark.asyncio
    async def test_uses_correct_entity_ids(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=60, price=0.30, cost=1.0)

        await charger._apply_slot("e1", slot)

        calls = mock_hass.services.async_call.call_args_list
        entity_ids = [c[1].get("entity_id") or c[0][2].get("entity_id") for c in calls]
        assert any("12345_current_limit" in eid for eid in entity_ids)
        assert any("12345_charging_enabled" in eid for eid in entity_ids)

    @pytest.mark.asyncio
    async def test_tracks_last_applied(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=60, price=0.30, cost=1.0)

        await charger._apply_slot("e1", slot)
        assert "e1" in charger._last_applied_slot

    @pytest.mark.asyncio
    async def test_no_serial_returns_early(self, charger, mock_hass):
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=60, price=0.30, cost=1.0)
        await charger._apply_slot("nonexistent", slot)
        mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_service_error(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.services.async_call.side_effect = Exception("service error")
        slot = ChargingSlot(hour=22, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=60, price=0.30, cost=1.0)
        await charger._apply_slot("e1", slot)


class TestRestoreCharger:
    @pytest.mark.asyncio
    async def test_restores_user_limit(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        await charger._restore_charger_to_normal("e1")
        calls = mock_hass.services.async_call.call_args_list
        assert any(c[0][0] == "number" for c in calls)
        assert any(c[0][0] == "switch" and c[0][1] == "turn_on" for c in calls)

    @pytest.mark.asyncio
    async def test_no_serial_returns_early(self, charger, mock_hass):
        await charger._restore_charger_to_normal("nonexistent")
        mock_hass.services.async_call.assert_not_called()


class TestPauseCharger:
    @pytest.mark.asyncio
    async def test_calls_switch_off(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        await charger._pause_charger("e1", "waiting")
        calls = mock_hass.services.async_call.call_args_list
        assert any(c[0][0] == "switch" and c[0][1] == "turn_off" for c in calls)

    @pytest.mark.asyncio
    async def test_deduplicates_same_reason(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        await charger._pause_charger("e1", "waiting")
        await charger._pause_charger("e1", "waiting")
        assert charger._last_pause_reason["e1"] == "waiting"

    @pytest.mark.asyncio
    async def test_no_serial_returns_early(self, charger, mock_hass):
        await charger._pause_charger("nonexistent")
        mock_hass.services.async_call.assert_not_called()


class TestExecutePlans:
    @pytest.mark.asyncio
    async def test_noop_when_no_plans(self, charger, mock_hass):
        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.as_local.return_value = datetime(2024, 1, 15, 22, 0)
            await charger._execute_plans(datetime(2024, 1, 15, 22, 0))
        mock_hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_expired_plans(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        plan = ChargingPlan(
            charger_id="e1",
            created_at=datetime(2024, 1, 15, 20, 0),
            departure_time=datetime(2024, 1, 15, 21, 0),
            slots=[],
        )
        charger._active_plans["e1"] = plan

        now = datetime(2024, 1, 15, 22, 0)
        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.as_local.return_value = now
            mock_dt.now.return_value = now
            await charger._execute_plans(now)

        assert "e1" not in charger._active_plans


class TestNordpoolChange:
    def test_replan_when_tomorrow_becomes_available(self, charger, mock_hass):
        charger._last_tomorrow_valid = False
        charger._active_plans["e1"] = MagicMock()

        new_state = MagicMock()
        new_state.attributes = {"tomorrow_available": True}
        event = MagicMock()
        event.data = {"new_state": new_state}

        with patch.object(charger, "_create_plans_for_chargers") as mock_create:
            charger._handle_nordpool_change(event)
            mock_create.assert_called_once_with(["e1"])

    def test_no_replan_when_already_available(self, charger):
        charger._last_tomorrow_valid = True

        new_state = MagicMock()
        new_state.attributes = {"tomorrow_available": True}
        event = MagicMock()
        event.data = {"new_state": new_state}

        with patch.object(charger, "_create_plans_for_chargers") as mock_create:
            charger._handle_nordpool_change(event)
            mock_create.assert_not_called()

    def test_no_replan_without_active_plans(self, charger):
        charger._last_tomorrow_valid = False

        new_state = MagicMock()
        new_state.attributes = {"tomorrow_available": True}
        event = MagicMock()
        event.data = {"new_state": new_state}

        with patch.object(charger, "_create_plans_for_chargers") as mock_create:
            charger._handle_nordpool_change(event)
            mock_create.assert_not_called()

    def test_ignored_without_new_state(self, charger):
        event = MagicMock()
        event.data = {"new_state": None}
        charger._handle_nordpool_change(event)
        assert charger._last_tomorrow_valid is None


class TestPluggedStateChange:
    def _make_plug_event(self, charger, mock_hass, old_val, new_val):
        _setup_charger_in_hass(mock_hass, "e1")
        old = MagicMock()
        old.state = old_val
        new = MagicMock()
        new.state = new_val
        event = MagicMock()
        event.data = {
            "entity_id": "binary_sensor.keba_kecontact_12345_plugged_on_ev",
            "old_state": old,
            "new_state": new,
        }
        return event

    def test_plug_in_creates_plan(self, charger, mock_hass):
        event = self._make_plug_event(charger, mock_hass, "off", "on")
        charger._handle_plugged_state_change(event)
        mock_hass.async_create_task.assert_called()

    def test_unplug_triggers_disconnect(self, charger, mock_hass):
        event = self._make_plug_event(charger, mock_hass, "on", "off")
        charger._handle_plugged_state_change(event)
        mock_hass.async_create_task.assert_called()

    def test_ignores_unknown_entry(self, charger, mock_hass):
        old = MagicMock()
        old.state = "off"
        new = MagicMock()
        new.state = "on"
        event = MagicMock()
        event.data = {
            "entity_id": "binary_sensor.unknown_plugged_on_ev",
            "old_state": old,
            "new_state": new,
        }
        charger._handle_plugged_state_change(event)
        mock_hass.async_create_task.assert_not_called()

    def test_ignores_missing_states(self, charger, mock_hass):
        event = MagicMock()
        event.data = {"entity_id": "sensor.x", "old_state": None, "new_state": None}
        charger._handle_plugged_state_change(event)
        mock_hass.async_create_task.assert_not_called()

    def test_plug_in_resumes_existing_plan_same_soc(self, charger, mock_hass):
        _setup_charger_in_hass(mock_hass, "e1")
        plan = ChargingPlan(
            charger_id="e1",
            created_at=datetime(2024, 1, 15, 20, 0),
            departure_time=datetime(2024, 1, 16, 7, 0),
            initial_soc=50.0,
        )
        charger._active_plans["e1"] = plan

        mock_hass.states.get.return_value = _mock_state("50")

        event = self._make_plug_event(charger, mock_hass, "off", "on")

        with patch("custom_components.keba_kecontact.smart_charger.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 23, 0)
            charger._handle_plugged_state_change(event)

        mock_hass.async_create_task.assert_called()


class TestCarConnected:
    @pytest.mark.asyncio
    async def test_skips_when_planning_in_progress(self, charger, mock_hass):
        charger._planning_in_progress = True
        await charger._on_car_connected("e1")

    @pytest.mark.asyncio
    async def test_clears_planning_flag_on_error(self, charger, mock_hass):
        charger._planning_in_progress = False
        with patch.object(charger, "_create_plans_for_all_connected", side_effect=Exception("err")):
            await charger._on_car_connected("e1")
        assert not charger._planning_in_progress


class TestCarDisconnected:
    @pytest.mark.asyncio
    async def test_removes_plan(self, charger, mock_hass):
        charger._active_plans["e1"] = MagicMock()
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("80")
        await charger._on_car_disconnected("e1")
        assert "e1" not in charger._active_plans

    @pytest.mark.asyncio
    async def test_replans_remaining(self, charger, mock_hass):
        charger._active_plans["e1"] = MagicMock()
        _setup_charger_in_hass(mock_hass, "e1")
        mock_hass.states.get.return_value = _mock_state("80")

        with patch.object(charger, "_get_connected_chargers", return_value=[]):
            await charger._on_car_disconnected("e1")


class TestStartStop:
    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self, charger, mock_hass):
        unsub_nordpool = MagicMock()
        unsub_interval = MagicMock()
        unsub_state = MagicMock()
        charger._unsub_nordpool = unsub_nordpool
        charger._unsub_interval = unsub_interval
        charger._unsub_charger_states = [unsub_state]

        await charger.async_stop()

        unsub_nordpool.assert_called_once()
        unsub_interval.assert_called_once()
        unsub_state.assert_called_once()


class TestPriceExtraction:
    def test_dict_with_start_key(self, charger):
        prices = [
            {"start": "2024-01-15T00:00:00", "price": 0.30},
            {"start": "2024-01-15T01:00:00", "price": 0.25},
        ]
        result = charger._extract_prices_to_slots(prices, "2024-01-15")
        assert len(result) == 2

    def test_dict_with_hour_key(self, charger):
        prices = [{"hour": i, "price": 0.30 + i * 0.01} for i in range(24)]
        result = charger._extract_prices_to_slots(prices, "2024-01-15")
        assert len(result) == 24
        assert result[0].hour == 0

    def test_dict_with_value_key(self, charger):
        prices = [{"value": 0.30 + i * 0.01} for i in range(24)]
        result = charger._extract_prices_to_slots(prices, "2024-01-15")
        assert len(result) == 24
        assert result[0].price == pytest.approx(0.30)

    def test_multiplier_applied(self, charger):
        result = charger._extract_prices_to_slots([300.0], "2024-01-15", multiplier=0.001)
        assert result[0].price == pytest.approx(0.30)
