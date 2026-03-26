"""Tests for smart charging functionality."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from custom_components.keba_kecontact.charging_planner import (
    ChargingPlanner,
    ChargingSlot,
    ChargingPlan,
    ChargerRequirement,
    PriceSlot,
)
from custom_components.keba_kecontact.charging_history import (
    ChargingSession,
    ChargingHistoryTracker,
)


class TestChargingSlot:
    def test_to_dict(self):
        slot = ChargingSlot(
            hour=14, minute=30, date="2024-01-15",
            current_amps=16, expected_soc_after=75.5, price=0.45, cost=1.23,
        )
        result = slot.to_dict()
        assert result == {
            "hour": 14, "minute": 30, "date": "2024-01-15",
            "current_amps": 16, "expected_soc_after": 75.5, "price": 0.45, "cost": 1.23,
        }

    def test_from_dict(self):
        data = {
            "hour": 14, "minute": 15, "date": "2024-01-15",
            "current_amps": 16, "soc_after": 75.5, "price": 0.45, "cost": 1.23,
        }
        slot = ChargingSlot.from_dict(data)
        assert slot.hour == 14
        assert slot.minute == 15
        assert slot.expected_soc_after == 75.5

    def test_from_dict_without_minute_defaults_to_zero(self):
        data = {
            "hour": 14, "date": "2024-01-15",
            "current_amps": 16, "soc_after": 75.5, "price": 0.45, "cost": 1.23,
        }
        slot = ChargingSlot.from_dict(data)
        assert slot.minute == 0

    def test_from_dict_with_expected_soc_after(self):
        data = {
            "hour": 14, "minute": 0, "date": "2024-01-15",
            "current_amps": 16, "expected_soc_after": 80.0, "price": 0.45, "cost": 1.23,
        }
        slot = ChargingSlot.from_dict(data)
        assert slot.expected_soc_after == 80.0


class TestChargingPlan:
    def test_get_slot_for_time_found_15min(self):
        slots = [
            ChargingSlot(hour=14, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
            ChargingSlot(hour=14, minute=15, date="2024-01-15", current_amps=20, expected_soc_after=55, price=0.35, cost=1.2),
            ChargingSlot(hour=14, minute=30, date="2024-01-15", current_amps=24, expected_soc_after=60, price=0.4, cost=1.4),
        ]
        plan = ChargingPlan(
            charger_id="test", created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10), slots=slots,
        )
        result = plan.get_slot_for_time(14, 32, "2024-01-15")
        assert result is not None
        assert result.minute == 30

    def test_get_slot_for_time_not_found(self):
        slots = [
            ChargingSlot(hour=14, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        plan = ChargingPlan(
            charger_id="test", created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10), slots=slots,
        )
        assert plan.get_slot_for_time(20, 0, "2024-01-15") is None

    def test_get_slot_for_time_wrong_date(self):
        slots = [
            ChargingSlot(hour=14, minute=0, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        plan = ChargingPlan(
            charger_id="test", created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10), slots=slots,
        )
        assert plan.get_slot_for_time(14, 0, "2024-01-16") is None

    def test_to_dict_and_from_dict_roundtrip(self):
        now = datetime(2024, 1, 15, 10, 0, 0)
        departure = datetime(2024, 1, 16, 7, 0, 0)
        slots = [
            ChargingSlot(hour=14, minute=30, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        original = ChargingPlan(
            charger_id="test", created_at=now, departure_time=departure,
            slots=slots, total_cost=5.50, reasoning="Test", status="active",
        )
        data = original.to_dict()
        restored = ChargingPlan.from_dict(data)
        assert restored.charger_id == original.charger_id
        assert restored.total_cost == original.total_cost
        assert len(restored.slots) == 1


def _make_prices(date: str, count: int = 24, base_price: float = 0.30) -> list[PriceSlot]:
    """Helper to create hourly price slots."""
    return [PriceSlot(hour=h, minute=0, price=base_price + h * 0.01, date=date) for h in range(count)]


def _make_15min_prices(date: str, base_price: float = 0.10) -> list[PriceSlot]:
    """Helper to create 15-min price slots for a full day."""
    slots = []
    for i in range(96):
        h = i // 4
        m = (i % 4) * 15
        slots.append(PriceSlot(hour=h, minute=m, price=base_price + i * 0.001, date=date))
    return slots


class TestChargingPlanner:
    def test_single_charger_selects_cheapest_slots(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=50.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16, charging_efficiency=0.95,
        )]

        plans = planner.compute_plans(chargers, 16, prices, None, now)

        assert len(plans) == 1
        plan = plans[0]
        assert len(plan.slots) > 0
        assert all(s.current_amps > 0 for s in plan.slots)
        assert plan.total_cost > 0

        tomorrow_slots = [s for s in plan.slots if s.date == "2024-01-16"]
        today_slots = [s for s in plan.slots if s.date == "2024-01-15"]
        assert len(tomorrow_slots) > len(today_slots)

    def test_respects_departure_time(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.05)

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=80.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]

        plans = planner.compute_plans(chargers, 16, prices, None, now)
        plan = plans[0]

        for slot in plan.slots:
            slot_dt = datetime(int(slot.date[:4]), int(slot.date[5:7]), int(slot.date[8:10]), slot.hour, slot.minute)
            assert slot_dt < datetime(2024, 1, 16, 7, 0)

    def test_no_slots_when_soc_at_target(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15")

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=100.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]

        plans = planner.compute_plans(chargers, 16, prices, None, now)
        assert len(plans) == 1
        assert len(plans[0].slots) == 0

    def test_multi_charger_respects_total_max_current(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        chargers = [
            ChargerRequirement(
                charger_id="c1", charger_name="Charger 1",
                current_soc=20.0, battery_capacity_kwh=80.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=16,
            ),
            ChargerRequirement(
                charger_id="c2", charger_name="Charger 2",
                current_soc=20.0, battery_capacity_kwh=20.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=10,
            ),
        ]

        plans = planner.compute_plans(chargers, 16, prices, None, now)

        plan_by_id = {p.charger_id: p for p in plans}
        p1_slots = {(s.date, s.hour, s.minute): s.current_amps for s in plan_by_id["c1"].slots}
        p2_slots = {(s.date, s.hour, s.minute): s.current_amps for s in plan_by_id["c2"].slots}

        all_times = set(p1_slots.keys()) | set(p2_slots.keys())
        for t in all_times:
            total = p1_slots.get(t, 0) + p2_slots.get(t, 0)
            assert total <= 16, f"Total {total}A at {t} exceeds max 16A"

    def test_minimum_current_constraint(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        chargers = [
            ChargerRequirement(
                charger_id="c1", charger_name="Charger 1",
                current_soc=20.0, battery_capacity_kwh=80.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=10,
            ),
            ChargerRequirement(
                charger_id="c2", charger_name="Charger 2",
                current_soc=20.0, battery_capacity_kwh=20.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=10,
            ),
        ]

        plans = planner.compute_plans(chargers, 16, prices, None, now)

        for plan in plans:
            for slot in plan.slots:
                assert slot.current_amps == 0 or slot.current_amps >= 6

    def test_efficiency_affects_slot_count(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        base = dict(
            charger_id="c1", charger_name="Garage",
            current_soc=50.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )

        plans_high = planner.compute_plans(
            [ChargerRequirement(**base, charging_efficiency=0.95)],
            16, prices, None, now,
        )
        plans_low = planner.compute_plans(
            [ChargerRequirement(**base, charging_efficiency=0.60)],
            16, prices, None, now,
        )

        assert len(plans_low[0].slots) > len(plans_high[0].slots)

    def test_reasoning_string_generated(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=50.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]

        plans = planner.compute_plans(chargers, 16, prices, None, now)
        assert plans[0].reasoning != ""
        assert "kWh" in plans[0].reasoning

    def test_plan_updates_when_soc_changes(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15") + _make_prices("2024-01-16", base_price=0.10)

        base = dict(
            charger_id="c1", charger_name="Garage",
            battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )

        plans_20 = planner.compute_plans(
            [ChargerRequirement(current_soc=20.0, **base)], 16, prices, None, now,
        )
        plans_80 = planner.compute_plans(
            [ChargerRequirement(current_soc=80.0, **base)], 16, prices, None, now,
        )

        assert len(plans_80[0].slots) < len(plans_20[0].slots)

    def test_tomorrow_prices_included(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 22, 0)
        today_prices = _make_prices("2024-01-15", base_price=0.50)
        tomorrow_prices = _make_prices("2024-01-16", base_price=0.05)

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=50.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]

        plans = planner.compute_plans(chargers, 16, today_prices, tomorrow_prices, now)
        plan = plans[0]

        tomorrow_slots = [s for s in plan.slots if s.date == "2024-01-16"]
        assert len(tomorrow_slots) > 0

    def test_empty_chargers_returns_empty(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_prices("2024-01-15")
        assert planner.compute_plans([], 16, prices, None, now) == []

    def test_empty_prices_returns_empty(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=50.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]
        assert planner.compute_plans(chargers, 16, [], None, now) == []

    def test_15min_slot_detection(self):
        planner = ChargingPlanner()
        now = datetime(2024, 1, 15, 20, 0)
        prices = _make_15min_prices("2024-01-15") + _make_15min_prices("2024-01-16")

        chargers = [ChargerRequirement(
            charger_id="c1", charger_name="Garage",
            current_soc=90.0, battery_capacity_kwh=80.0,
            departure_time=datetime(2024, 1, 16, 7, 0),
            max_current_a=16,
        )]

        plans = planner.compute_plans(chargers, 16, prices, None, now)
        assert plans[0].slot_minutes == 15


class TestPriceExtraction:
    def test_extract_prices_to_slots_hourly(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)

        result = charger._extract_prices_to_slots([0.32, 0.29, 0.26], "2024-01-15")
        assert len(result) == 3
        assert result[0].price == pytest.approx(0.32)

    def test_extract_prices_to_slots_15min(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)

        result = charger._extract_prices_to_slots(
            [0.30 + i * 0.01 for i in range(96)], "2024-01-15"
        )
        assert len(result) == 96
        assert result[1].minute == 15
        assert result[4].hour == 1

    def test_extract_prices_to_slots_empty_list(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)
        assert charger._extract_prices_to_slots([], "2024-01-15") == []


class TestSmartChargerDepartureTime:
    def test_parse_departure_time_tomorrow(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)

        now = datetime(2024, 1, 15, 22, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)
        assert result.day == 16
        assert result.hour == 7

    def test_parse_departure_time_today(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)

        now = datetime(2024, 1, 15, 5, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)
        assert result.day == 15
        assert result.hour == 7


class TestSmartChargerNordpoolReading:
    def test_get_nordpool_prices_returns_price_slots(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.attributes = {
            "prices_today": [{"hour": 0, "price": 0.30}, {"hour": 1, "price": 0.28}],
            "tomorrow_available": False,
        }
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "sensor.electricity_price", [], 32)
        today, tomorrow = charger._get_nordpool_prices()

        assert len(today) == 2
        assert today[0].price == pytest.approx(0.30)
        assert tomorrow is None

    def test_get_nordpool_prices_entity_not_found(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_hass.states.get.return_value = None

        charger = SmartCharger(mock_hass, "sensor.electricity_price", [], 32)
        today, tomorrow = charger._get_nordpool_prices()

        assert today == []
        assert tomorrow is None

    def test_get_nordpool_prices_converts_mwh_to_kwh(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.attributes = {
            "prices_today": [{"hour": 0, "price": 300.0}],
            "tomorrow_available": False,
            "unit_of_measurement": "EUR/MWh",
        }
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "sensor.electricity_price", [], 32)
        today, _ = charger._get_nordpool_prices()
        assert today[0].price == pytest.approx(0.30)


class TestSocNormalization:
    def test_soc_percent_unchanged(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "75"
        mock_state.attributes = {"unit_of_measurement": "%"}
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)
        assert charger._get_soc_normalized("sensor.car_soc") == 75.0

    def test_soc_fraction_converted_to_percent(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "0.75"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "sensor.prices", [], 32)
        assert charger._get_soc_normalized("sensor.car_soc") == 75.0


class TestPowerEfficiency:
    def test_efficiency_calculated_from_sessions(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        now = datetime.now()

        tracker._data.sessions["charger_1"] = [
            ChargingSession(
                charger_entry_id="charger_1", vehicle_soc_entity="sensor.car_soc",
                start_time=now, end_time=now + timedelta(hours=5),
                start_soc=20.0, end_soc=80.0, energy_kwh=60.0,
            ),
        ]

        result = tracker.get_power_efficiency("charger_1", battery_capacity_kwh=82.0)
        expected = (60.0 / 100.0 * 82.0) / 60.0
        assert result == pytest.approx(expected, rel=0.01)

    def test_efficiency_none_when_no_sessions(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        assert tracker.get_power_efficiency("charger_1", battery_capacity_kwh=82.0) is None

    def test_efficiency_clamped_to_max_1(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        now = datetime.now()

        tracker._data.sessions["charger_1"] = [
            ChargingSession(
                charger_entry_id="charger_1", vehicle_soc_entity="sensor.car_soc",
                start_time=now, end_time=now + timedelta(hours=5),
                start_soc=20.0, end_soc=80.0, energy_kwh=10.0,
            ),
        ]

        assert tracker.get_power_efficiency("charger_1", battery_capacity_kwh=82.0) == 1.0
