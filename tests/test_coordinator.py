"""Tests for the KebaChargingCoordinator."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.keba_kecontact.coordinator import KebaChargingCoordinator
from custom_components.keba_kecontact.const import (
    DOMAIN,
    COORDINATOR_STRATEGY_OFF,
    COORDINATOR_STRATEGY_EQUAL,
    COORDINATOR_STRATEGY_SMART,
)


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.async_create_task = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


def _make_charger_entry(mock_hass, entry_id, state=3, power_kw=7.0, serial="12345", curr_hw=32000, current_limit=16):
    coordinator = MagicMock()
    coordinator.data = {
        "state": state,
        "power_kw": power_kw,
        "energy_present_kwh": 10.0,
        "energy_total_kwh": 500.0,
        "serial": serial,
        "max_curr": 16000,
        "curr_hw": curr_hw,
    }
    client = AsyncMock()
    client.ip_address = f"192.168.1.{hash(entry_id) % 254 + 1}"
    config_entry = MagicMock()
    config_entry.options = {"current_limit": current_limit}
    mock_hass.data[DOMAIN][entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "config_entry": config_entry,
        "device_info": {},
    }
    return client


@pytest.fixture
def coordinator(mock_hass):
    return KebaChargingCoordinator(
        hass=mock_hass,
        name="test",
        charger_entry_ids=["e1", "e2"],
        max_current=32,
        strategy=COORDINATOR_STRATEGY_EQUAL,
    )


class TestCoordinatorInit:
    def test_properties(self, coordinator):
        assert coordinator.charger_entry_ids == ["e1", "e2"]
        assert coordinator.max_current == 32
        assert coordinator.strategy == COORDINATOR_STRATEGY_EQUAL
        assert coordinator.smart_charger is None

    def test_update_config(self, coordinator):
        coordinator.update_config("sensor.prices")
        assert coordinator._nordpool_entity == "sensor.prices"


class TestCoordinatorStartStop:
    @pytest.mark.asyncio
    async def test_start_registers_state_listener(self, coordinator, mock_hass):
        coordinator.async_refresh = AsyncMock()
        await coordinator.async_start()
        mock_hass.bus.async_listen.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_removes_state_listener(self, coordinator, mock_hass):
        unsub = MagicMock()
        mock_hass.bus.async_listen.return_value = unsub
        coordinator.async_refresh = AsyncMock()
        await coordinator.async_start()
        await coordinator.async_stop()
        unsub.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_smart_without_nordpool_logs_warning(self, mock_hass):
        coord = KebaChargingCoordinator(
            hass=mock_hass, name="test", charger_entry_ids=["e1"],
            max_current=32, strategy=COORDINATOR_STRATEGY_SMART,
        )
        coord.async_refresh = AsyncMock()
        await coord.async_start()
        assert coord.smart_charger is None


class TestCoordinatorDistribution:
    def test_off(self, coordinator):
        coordinator._strategy = COORDINATOR_STRATEGY_OFF
        result = coordinator._calculate_distribution({})
        assert result == "Off - No load balancing"

    def test_smart_with_plans(self, coordinator):
        coordinator._strategy = COORDINATOR_STRATEGY_SMART
        coordinator._smart_charger = MagicMock()
        coordinator._smart_charger.active_plans = {"e1": MagicMock()}
        result = coordinator._calculate_distribution({})
        assert "Smart" in result
        assert "1" in result

    def test_smart_no_plans(self, coordinator):
        coordinator._strategy = COORDINATOR_STRATEGY_SMART
        coordinator._smart_charger = MagicMock()
        coordinator._smart_charger.active_plans = {}
        result = coordinator._calculate_distribution({})
        assert "Waiting" in result

    def test_equal_no_active(self, coordinator):
        result = coordinator._calculate_distribution({})
        assert "32A available" in result

    def test_equal_one_active(self, coordinator):
        states = {"e1": {"state": 3}}
        result = coordinator._calculate_distribution(states)
        assert "32A" in result
        assert "to charger" in result

    def test_equal_two_active(self, coordinator):
        states = {"e1": {"state": 3}, "e2": {"state": 3}}
        result = coordinator._calculate_distribution(states)
        assert "16A per charger" in result


class TestLoadBalancingActive:
    def test_off_never_active(self, coordinator):
        coordinator._strategy = COORDINATOR_STRATEGY_OFF
        assert not coordinator._is_load_balancing_active(3)

    def test_one_charger_not_active(self, coordinator):
        assert not coordinator._is_load_balancing_active(1)

    def test_two_chargers_active(self, coordinator):
        assert coordinator._is_load_balancing_active(2)


class TestApplyLoadBalancing:
    @pytest.mark.asyncio
    async def test_off_noop(self, coordinator, mock_hass):
        coordinator._strategy = COORDINATOR_STRATEGY_OFF
        coordinator.async_request_refresh = AsyncMock()
        await coordinator._apply_load_balancing()
        coordinator.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_noop(self, coordinator, mock_hass):
        coordinator._strategy = COORDINATOR_STRATEGY_SMART
        coordinator.async_request_refresh = AsyncMock()
        await coordinator._apply_load_balancing()
        coordinator.async_request_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_equal_no_active_restores(self, coordinator, mock_hass):
        client1 = _make_charger_entry(mock_hass, "e1", state=1)
        client2 = _make_charger_entry(mock_hass, "e2", state=1)
        coordinator.async_request_refresh = AsyncMock()

        await coordinator._apply_load_balancing()

        client1.set_current.assert_called_once()
        client2.set_current.assert_called_once()

    @pytest.mark.asyncio
    async def test_equal_two_active_splits(self, coordinator, mock_hass):
        client1 = _make_charger_entry(mock_hass, "e1", state=3)
        client2 = _make_charger_entry(mock_hass, "e2", state=3)
        coordinator.async_request_refresh = AsyncMock()

        await coordinator._apply_load_balancing()

        client1.set_current.assert_called_once_with(16000)
        client2.set_current.assert_called_once_with(16000)

    @pytest.mark.asyncio
    async def test_equal_respects_hw_limit(self, coordinator, mock_hass):
        client1 = _make_charger_entry(mock_hass, "e1", state=3, curr_hw=10000)
        client2 = _make_charger_entry(mock_hass, "e2", state=3)
        coordinator.async_request_refresh = AsyncMock()

        await coordinator._apply_load_balancing()

        client1.set_current.assert_called_once_with(10000)
        client2.set_current.assert_called_once_with(16000)

    @pytest.mark.asyncio
    async def test_equal_insufficient_current_warns(self, coordinator, mock_hass):
        coordinator._max_current = 5
        _make_charger_entry(mock_hass, "e1", state=3)
        _make_charger_entry(mock_hass, "e2", state=3)
        coordinator.async_request_refresh = AsyncMock()

        await coordinator._apply_load_balancing()

        for entry_id in ["e1", "e2"]:
            mock_hass.data[DOMAIN][entry_id]["client"].set_current.assert_not_called()


class TestRestoreChargers:
    @pytest.mark.asyncio
    async def test_restore_uses_user_limit(self, coordinator, mock_hass):
        client = _make_charger_entry(mock_hass, "e1", state=1, current_limit=20)
        charger_states = {"e1": {"state": 1, "client": client}}

        await coordinator._restore_all_chargers_to_user_limits(charger_states)

        client.set_current.assert_called_once_with(20000)

    @pytest.mark.asyncio
    async def test_restore_caps_to_hw_limit(self, coordinator, mock_hass):
        client = _make_charger_entry(mock_hass, "e1", state=1, current_limit=32, curr_hw=16000)
        charger_states = {"e1": {"state": 1, "client": client}}

        await coordinator._restore_all_chargers_to_user_limits(charger_states)

        client.set_current.assert_called_once_with(16000)

    @pytest.mark.asyncio
    async def test_restore_skips_no_config_entry(self, coordinator, mock_hass):
        client = AsyncMock()
        mock_hass.data[DOMAIN]["e1"] = {}
        charger_states = {"e1": {"state": 1, "client": client}}

        await coordinator._restore_all_chargers_to_user_limits(charger_states)
        client.set_current.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_sends_display_message(self, coordinator, mock_hass):
        client = _make_charger_entry(mock_hass, "e1", state=1, current_limit=16)
        charger_states = {"e1": {"state": 1, "client": client}}

        await coordinator._restore_all_chargers_to_user_limits(charger_states)
        client.display_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_handles_client_error(self, coordinator, mock_hass):
        client = _make_charger_entry(mock_hass, "e1", state=1)
        client.set_current.side_effect = Exception("UDP error")
        charger_states = {"e1": {"state": 1, "client": client}}

        await coordinator._restore_all_chargers_to_user_limits(charger_states)


class TestDisplayMessage:
    @pytest.mark.asyncio
    async def test_truncates_long_message(self, coordinator):
        client = AsyncMock()
        await coordinator._send_display_message(client, "A" * 30)
        msg = client.display_text.call_args[0][0]
        assert len(msg) == 23

    @pytest.mark.asyncio
    async def test_short_message_unchanged(self, coordinator):
        client = AsyncMock()
        await coordinator._send_display_message(client, "Hello")
        client.display_text.assert_called_once_with("Hello")

    @pytest.mark.asyncio
    async def test_handles_display_error(self, coordinator):
        client = AsyncMock()
        client.display_text.side_effect = Exception("display error")
        await coordinator._send_display_message(client, "Hi")


class TestStrategy:
    @pytest.mark.asyncio
    async def test_set_strategy_equal_to_off(self, coordinator, mock_hass):
        coordinator.async_request_refresh = AsyncMock()
        await coordinator.set_strategy(COORDINATOR_STRATEGY_OFF)
        assert coordinator.strategy == COORDINATOR_STRATEGY_OFF

    @pytest.mark.asyncio
    async def test_set_strategy_smart_to_off_disables(self, coordinator, mock_hass):
        coordinator._strategy = COORDINATOR_STRATEGY_SMART
        coordinator._smart_charger = MagicMock()
        coordinator._smart_charger.async_stop = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        await coordinator.set_strategy(COORDINATOR_STRATEGY_OFF)
        coordinator._smart_charger is None

    @pytest.mark.asyncio
    async def test_set_max_current(self, coordinator, mock_hass):
        coordinator.async_request_refresh = AsyncMock()
        _make_charger_entry(mock_hass, "e1", state=1)
        _make_charger_entry(mock_hass, "e2", state=1)
        await coordinator.set_max_current(16)
        assert coordinator.max_current == 16


class TestHandleStateChange:
    def test_keba_state_triggers_rebalance(self, coordinator, mock_hass):
        event = MagicMock()
        event.data = {"entity_id": "sensor.keba_kecontact_12345_state"}
        coordinator._handle_state_change(event)
        mock_hass.async_create_task.assert_called_once()

    def test_non_keba_ignored(self, coordinator, mock_hass):
        event = MagicMock()
        event.data = {"entity_id": "sensor.weather_temperature"}
        coordinator._handle_state_change(event)
        mock_hass.async_create_task.assert_not_called()

    def test_keba_non_state_ignored(self, coordinator, mock_hass):
        event = MagicMock()
        event.data = {"entity_id": "sensor.keba_kecontact_12345_power"}
        coordinator._handle_state_change(event)
        mock_hass.async_create_task.assert_not_called()


class TestUpdateData:
    @pytest.mark.asyncio
    async def test_aggregates_power(self, coordinator, mock_hass):
        _make_charger_entry(mock_hass, "e1", state=3, power_kw=7.0)
        _make_charger_entry(mock_hass, "e2", state=3, power_kw=3.5)
        result = await coordinator._async_update_data()
        assert result["total_power"] == pytest.approx(10.5)

    @pytest.mark.asyncio
    async def test_counts_active_chargers(self, coordinator, mock_hass):
        _make_charger_entry(mock_hass, "e1", state=3)
        _make_charger_entry(mock_hass, "e2", state=1)
        result = await coordinator._async_update_data()
        assert result["active_chargers"] == 1

    @pytest.mark.asyncio
    async def test_skips_missing_entries(self, coordinator, mock_hass):
        _make_charger_entry(mock_hass, "e1", state=1)
        result = await coordinator._async_update_data()
        assert result["active_chargers"] == 0

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self, coordinator, mock_hass):
        _make_charger_entry(mock_hass, "e1", state=1)
        _make_charger_entry(mock_hass, "e2", state=1)
        result = await coordinator._async_update_data()
        assert "total_power" in result
        assert "total_session_energy" in result
        assert "total_energy" in result
        assert "active_chargers" in result
        assert "charger_states" in result
        assert "distribution" in result
        assert "max_current" in result
        assert "strategy" in result
        assert "is_load_balancing_active" in result
