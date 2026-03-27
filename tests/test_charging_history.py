"""Tests for charging history tracker."""
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.keba_kecontact.charging_history import (
    ChargingSession,
    ActiveSession,
    ChargingHistoryData,
    ChargingHistoryTracker,
    MAX_SESSIONS_PER_CHARGER,
)


def _make_session(
    charger="charger_1",
    soc_entity="sensor.car_soc",
    start_soc=20.0,
    end_soc=80.0,
    energy=50.0,
    hours_ago=5,
):
    now = datetime.now()
    return ChargingSession(
        charger_entry_id=charger,
        vehicle_soc_entity=soc_entity,
        start_time=now - timedelta(hours=hours_ago),
        end_time=now,
        start_soc=start_soc,
        end_soc=end_soc,
        energy_kwh=energy,
    )


class TestChargingSession:
    def test_to_dict_roundtrip(self):
        session = _make_session()
        data = session.to_dict()
        restored = ChargingSession.from_dict(data)
        assert restored.charger_entry_id == session.charger_entry_id
        assert restored.start_soc == session.start_soc
        assert restored.end_soc == session.end_soc
        assert restored.energy_kwh == session.energy_kwh
        assert restored.start_time.isoformat() == session.start_time.isoformat()

    def test_from_dict_parses_iso_dates(self):
        data = {
            "charger_entry_id": "c1",
            "vehicle_soc_entity": "sensor.soc",
            "start_time": "2024-06-15T10:00:00",
            "end_time": "2024-06-15T15:00:00",
            "start_soc": 20.0,
            "end_soc": 80.0,
            "energy_kwh": 50.0,
        }
        session = ChargingSession.from_dict(data)
        assert session.start_time == datetime(2024, 6, 15, 10, 0, 0)
        assert session.end_time == datetime(2024, 6, 15, 15, 0, 0)


class TestActiveSession:
    def test_to_dict_roundtrip(self):
        active = ActiveSession(
            charger_entry_id="c1",
            vehicle_soc_entity="sensor.soc",
            start_time=datetime(2024, 6, 15, 10, 0),
            start_soc=30.0,
            start_energy_kwh=5.0,
        )
        data = active.to_dict()
        restored = ActiveSession.from_dict(data)
        assert restored.charger_entry_id == active.charger_entry_id
        assert restored.start_soc == active.start_soc
        assert restored.start_energy_kwh == active.start_energy_kwh


class TestChargingHistoryData:
    def test_to_dict_empty(self):
        data = ChargingHistoryData()
        result = data.to_dict()
        assert result == {"sessions": {}, "active_sessions": {}}

    def test_to_dict_with_sessions(self):
        data = ChargingHistoryData(
            sessions={"c1": [_make_session(charger="c1")]},
            active_sessions={
                "c2": ActiveSession(
                    charger_entry_id="c2",
                    vehicle_soc_entity="sensor.soc",
                    start_time=datetime.now(),
                    start_soc=50.0,
                    start_energy_kwh=0.0,
                )
            },
        )
        result = data.to_dict()
        assert "c1" in result["sessions"]
        assert len(result["sessions"]["c1"]) == 1
        assert "c2" in result["active_sessions"]

    def test_from_dict_roundtrip(self):
        original = ChargingHistoryData(
            sessions={"c1": [_make_session(charger="c1")]},
        )
        restored = ChargingHistoryData.from_dict(original.to_dict())
        assert "c1" in restored.sessions
        assert len(restored.sessions["c1"]) == 1

    def test_from_dict_empty(self):
        restored = ChargingHistoryData.from_dict({})
        assert restored.sessions == {}
        assert restored.active_sessions == {}


@pytest.fixture
def mock_hass(tmp_path):
    hass = MagicMock()
    hass.config.path = lambda filename: str(tmp_path / filename)

    async def run_sync(fn, *args):
        return fn(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=run_sync)
    return hass


@pytest.fixture
def tracker(mock_hass):
    return ChargingHistoryTracker(mock_hass)


class TestTrackerLoadSave:
    @pytest.mark.asyncio
    async def test_load_no_file(self, tracker):
        await tracker.async_load()
        assert tracker._data.sessions == {}

    @pytest.mark.asyncio
    async def test_load_valid_file(self, tracker, tmp_path):
        session = _make_session()
        data = {"sessions": {"c1": [session.to_dict()]}, "active_sessions": {}}
        (tmp_path / "keba_charging_history.json").write_text(json.dumps(data))

        await tracker.async_load()
        assert "c1" in tracker._data.sessions
        assert len(tracker._data.sessions["c1"]) == 1

    @pytest.mark.asyncio
    async def test_load_corrupt_file(self, tracker, tmp_path):
        (tmp_path / "keba_charging_history.json").write_text("not json{{{")
        await tracker.async_load()
        assert tracker._data.sessions == {}

    @pytest.mark.asyncio
    async def test_save_creates_file(self, tracker, tmp_path):
        tracker._data.sessions["c1"] = [_make_session(charger="c1")]
        await tracker.async_save()
        content = (tmp_path / "keba_charging_history.json").read_text()
        data = json.loads(content)
        assert "c1" in data["sessions"]

    @pytest.mark.asyncio
    async def test_load_restores_active_sessions(self, tracker, tmp_path):
        active = ActiveSession(
            charger_entry_id="c1",
            vehicle_soc_entity="sensor.soc",
            start_time=datetime(2024, 6, 15, 10, 0),
            start_soc=30.0,
            start_energy_kwh=0.0,
        )
        data = {"sessions": {}, "active_sessions": {"c1": active.to_dict()}}
        (tmp_path / "keba_charging_history.json").write_text(json.dumps(data))

        await tracker.async_load()
        assert tracker.is_session_active("c1")
        assert tracker.get_active_session("c1").start_soc == 30.0


class TestTrackerSessions:
    @pytest.mark.asyncio
    async def test_start_session(self, tracker):
        await tracker.start_session("c1", "sensor.soc", 40.0, 5.0)
        assert tracker.is_session_active("c1")

    @pytest.mark.asyncio
    async def test_end_session_no_active(self, tracker):
        result = await tracker.end_session("c1", 80.0, 50.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_end_session_too_short(self, tracker):
        await tracker.start_session("c1", "sensor.soc", 40.0, 0.0)
        tracker._active_sessions["c1"].start_time = datetime.now() - timedelta(seconds=30)
        result = await tracker.end_session("c1", 80.0, 50.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_end_session_no_energy(self, tracker):
        await tracker.start_session("c1", "sensor.soc", 40.0, 10.0)
        tracker._active_sessions["c1"].start_time = datetime.now() - timedelta(hours=2)
        result = await tracker.end_session("c1", 80.0, 5.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_end_session_valid(self, tracker):
        await tracker.start_session("c1", "sensor.soc", 40.0, 0.0)
        tracker._active_sessions["c1"].start_time = datetime.now() - timedelta(hours=3)
        result = await tracker.end_session("c1", 80.0, 50.0)
        assert result is not None
        assert result.start_soc == 40.0
        assert result.end_soc == 80.0
        assert result.energy_kwh == 50.0
        assert not tracker.is_session_active("c1")
        assert len(tracker._data.sessions["c1"]) == 1

    @pytest.mark.asyncio
    async def test_end_session_trims_to_max(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1") for _ in range(MAX_SESSIONS_PER_CHARGER)
        ]
        await tracker.start_session("c1", "sensor.soc", 10.0, 0.0)
        tracker._active_sessions["c1"].start_time = datetime.now() - timedelta(hours=2)
        await tracker.end_session("c1", 90.0, 60.0)
        assert len(tracker._data.sessions["c1"]) == MAX_SESSIONS_PER_CHARGER


class TestTrackerQueries:
    def test_is_session_active_false_initially(self, tracker):
        assert not tracker.is_session_active("c1")

    def test_get_sessions_for_charger_empty(self, tracker):
        assert tracker.get_sessions_for_charger("nonexistent") == []

    def test_get_all_active_sessions_returns_copy(self, tracker):
        tracker._active_sessions["c1"] = ActiveSession(
            charger_entry_id="c1",
            vehicle_soc_entity="sensor.soc",
            start_time=datetime.now(),
            start_soc=50.0,
            start_energy_kwh=0.0,
        )
        copy = tracker.get_all_active_sessions()
        copy.pop("c1")
        assert tracker.is_session_active("c1")

    def test_get_active_session_none(self, tracker):
        assert tracker.get_active_session("nonexistent") is None


class TestChargingEfficiency:
    def test_no_sessions(self, tracker):
        assert tracker.get_charging_efficiency("c1") is None

    def test_calculates_kwh_per_percent(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", start_soc=20.0, end_soc=80.0, energy=48.0),
        ]
        result = tracker.get_charging_efficiency("c1")
        assert result == pytest.approx(48.0 / 60.0)

    def test_filters_by_vehicle(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", soc_entity="sensor.car_a", start_soc=20, end_soc=80, energy=48),
            _make_session(charger="c1", soc_entity="sensor.car_b", start_soc=20, end_soc=80, energy=60),
        ]
        result = tracker.get_charging_efficiency("c1", vehicle_soc_entity="sensor.car_a")
        assert result == pytest.approx(48.0 / 60.0)

    def test_uses_last_10(self, tracker):
        sessions = []
        for i in range(15):
            sessions.append(_make_session(charger="c1", start_soc=20, end_soc=80, energy=50 + i))
        tracker._data.sessions["c1"] = sessions
        result = tracker.get_charging_efficiency("c1")
        last_10_energy = sum(50 + i for i in range(5, 15))
        expected = last_10_energy / (60.0 * 10)
        assert result == pytest.approx(expected)

    def test_ignores_invalid_sessions(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", start_soc=80, end_soc=20, energy=10),
            _make_session(charger="c1", start_soc=20, end_soc=80, energy=0),
            _make_session(charger="c1", start_soc=20, end_soc=80, energy=48),
        ]
        result = tracker.get_charging_efficiency("c1")
        assert result == pytest.approx(48.0 / 60.0)


class TestPowerEfficiency:
    def test_none_when_no_sessions(self, tracker):
        assert tracker.get_power_efficiency("c1", battery_capacity_kwh=80.0) is None

    def test_calculates_correctly(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", start_soc=20, end_soc=80, energy=60),
        ]
        result = tracker.get_power_efficiency("c1", battery_capacity_kwh=82.0)
        expected = (60.0 / 100.0 * 82.0) / 60.0
        assert result == pytest.approx(expected, rel=0.01)

    def test_clamped_max_1(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", start_soc=20, end_soc=80, energy=10),
        ]
        assert tracker.get_power_efficiency("c1", battery_capacity_kwh=82.0) == 1.0

    def test_clamped_min_0_1(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", start_soc=20, end_soc=21, energy=500),
        ]
        assert tracker.get_power_efficiency("c1", battery_capacity_kwh=80.0) == 0.1

    def test_filters_by_vehicle(self, tracker):
        tracker._data.sessions["c1"] = [
            _make_session(charger="c1", soc_entity="sensor.car_a", start_soc=20, end_soc=80, energy=60),
            _make_session(charger="c1", soc_entity="sensor.car_b", start_soc=20, end_soc=80, energy=100),
        ]
        result_a = tracker.get_power_efficiency("c1", battery_capacity_kwh=80.0, vehicle_soc_entity="sensor.car_a")
        result_b = tracker.get_power_efficiency("c1", battery_capacity_kwh=80.0, vehicle_soc_entity="sensor.car_b")
        assert result_a != result_b
