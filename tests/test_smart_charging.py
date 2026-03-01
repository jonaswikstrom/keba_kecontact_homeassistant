"""Tests for AI smart charging functionality."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.keba_kecontact.anthropic_client import (
    AnthropicChargingPlanner,
    ChargingSlot,
    ChargingPlan,
    ChargerRequirement,
    ValidationResult,
)
from custom_components.keba_kecontact.charging_history import (
    ChargingSession,
    ChargingHistoryTracker,
)


class TestChargingSlot:
    def test_to_dict(self):
        slot = ChargingSlot(
            hour=14,
            date="2024-01-15",
            current_amps=16,
            expected_soc_after=75.5,
            price=0.45,
            cost=1.23,
        )

        result = slot.to_dict()

        assert result == {
            "hour": 14,
            "date": "2024-01-15",
            "current_amps": 16,
            "expected_soc_after": 75.5,
            "price": 0.45,
            "cost": 1.23,
        }

    def test_from_dict(self):
        data = {
            "hour": 14,
            "date": "2024-01-15",
            "current_amps": 16,
            "soc_after": 75.5,
            "price": 0.45,
            "cost": 1.23,
        }

        slot = ChargingSlot.from_dict(data)

        assert slot.hour == 14
        assert slot.date == "2024-01-15"
        assert slot.current_amps == 16
        assert slot.expected_soc_after == 75.5
        assert slot.price == 0.45
        assert slot.cost == 1.23

    def test_from_dict_with_expected_soc_after(self):
        data = {
            "hour": 14,
            "date": "2024-01-15",
            "current_amps": 16,
            "expected_soc_after": 80.0,
            "price": 0.45,
            "cost": 1.23,
        }

        slot = ChargingSlot.from_dict(data)

        assert slot.expected_soc_after == 80.0


class TestChargingPlan:
    def test_get_slot_for_hour_found(self):
        slots = [
            ChargingSlot(hour=14, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
            ChargingSlot(hour=15, date="2024-01-15", current_amps=20, expected_soc_after=65, price=0.4, cost=1.5),
        ]
        plan = ChargingPlan(
            charger_id="test_charger",
            created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10),
            slots=slots,
        )

        result = plan.get_slot_for_hour(15, "2024-01-15")

        assert result is not None
        assert result.current_amps == 20

    def test_get_slot_for_hour_not_found(self):
        slots = [
            ChargingSlot(hour=14, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        plan = ChargingPlan(
            charger_id="test_charger",
            created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10),
            slots=slots,
        )

        result = plan.get_slot_for_hour(20, "2024-01-15")

        assert result is None

    def test_get_slot_for_hour_wrong_date(self):
        slots = [
            ChargingSlot(hour=14, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        plan = ChargingPlan(
            charger_id="test_charger",
            created_at=datetime.now(),
            departure_time=datetime.now() + timedelta(hours=10),
            slots=slots,
        )

        result = plan.get_slot_for_hour(14, "2024-01-16")

        assert result is None

    def test_to_dict_and_from_dict_roundtrip(self):
        now = datetime(2024, 1, 15, 10, 0, 0)
        departure = datetime(2024, 1, 16, 7, 0, 0)
        slots = [
            ChargingSlot(hour=14, date="2024-01-15", current_amps=16, expected_soc_after=50, price=0.3, cost=1.0),
        ]
        original = ChargingPlan(
            charger_id="test_charger",
            created_at=now,
            departure_time=departure,
            slots=slots,
            total_cost=5.50,
            reasoning="Test reasoning",
            status="active",
        )

        data = original.to_dict()
        restored = ChargingPlan.from_dict(data)

        assert restored.charger_id == original.charger_id
        assert restored.created_at == original.created_at
        assert restored.departure_time == original.departure_time
        assert restored.total_cost == original.total_cost
        assert restored.reasoning == original.reasoning
        assert restored.status == original.status
        assert len(restored.slots) == len(original.slots)


class TestPriceExtraction:
    def test_extract_prices_from_dict_list(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        price_list = [
            {"hour": 2, "price": 0.26},
            {"hour": 0, "price": 0.32},
            {"hour": 1, "price": 0.29},
        ]

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._extract_prices_from_list(price_list)

        assert result == [0.32, 0.29, 0.26]

    def test_extract_prices_from_flat_list(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        price_list = [0.32, 0.29, 0.26]

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._extract_prices_from_list(price_list)

        assert result == [0.32, 0.29, 0.26]

    def test_extract_prices_from_empty_list(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._extract_prices_from_list([])

        assert result == []

    def test_extract_prices_full_day(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        price_list = [{"hour": h, "price": 0.20 + h * 0.01} for h in range(24)]

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._extract_prices_from_list(price_list)

        assert len(result) == 24
        assert result[0] == pytest.approx(0.20)
        assert result[23] == pytest.approx(0.43)


class TestAnthropicClientParsing:
    def test_parse_create_response(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        chargers = [
            ChargerRequirement(
                charger_id="charger_1",
                charger_name="Garage",
                current_soc=25.0,
                battery_capacity_kwh=75.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=32,
            )
        ]

        api_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "create_charging_plan",
                    "input": {
                        "plans": [
                            {
                                "charger_id": "charger_1",
                                "slots": [
                                    {"hour": 2, "date": "2024-01-16", "current_amps": 16, "soc_after": 45, "price": 0.25, "cost": 0.80},
                                    {"hour": 3, "date": "2024-01-16", "current_amps": 20, "soc_after": 70, "price": 0.22, "cost": 0.75},
                                ],
                                "total_cost": 1.55,
                            }
                        ],
                        "reasoning": "Charging during cheapest hours 02:00-04:00",
                    }
                }
            ]
        }

        current_time = datetime(2024, 1, 15, 20, 0)
        plans = planner._parse_create_response(chargers, api_response, current_time)

        assert len(plans) == 1
        assert plans[0].charger_id == "charger_1"
        assert len(plans[0].slots) == 2
        assert plans[0].total_cost == 1.55
        assert plans[0].reasoning == "Charging during cheapest hours 02:00-04:00"

    def test_parse_create_response_no_plans_raises(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        api_response = {"content": []}

        with pytest.raises(ValueError, match="No valid plans"):
            planner._parse_create_response([], api_response, datetime.now())

    def test_parse_validate_response_replan_needed(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        api_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "validate_plan",
                    "input": {
                        "replan_needed": True,
                        "reason": "Prices changed significantly in hours 02-04",
                    }
                }
            ]
        }

        result = planner._parse_validate_response(api_response)

        assert result.replan_needed is True
        assert "Prices changed" in result.reason

    def test_parse_validate_response_no_replan(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        api_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "validate_plan",
                    "input": {
                        "replan_needed": False,
                        "reason": "Current plan is still optimal",
                    }
                }
            ]
        }

        result = planner._parse_validate_response(api_response)

        assert result.replan_needed is False

    def test_parse_validate_response_invalid_returns_no_replan(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        api_response = {"content": []}

        result = planner._parse_validate_response(api_response)

        assert result.replan_needed is False


class TestAnthropicClientApiCall:
    @pytest.mark.asyncio
    async def test_create_plan_calls_api(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        chargers = [
            ChargerRequirement(
                charger_id="charger_1",
                charger_name="Garage",
                current_soc=25.0,
                battery_capacity_kwh=75.0,
                departure_time=datetime(2024, 1, 16, 7, 0),
                max_current_a=32,
            )
        ]

        mock_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "create_charging_plan",
                    "input": {
                        "plans": [
                            {
                                "charger_id": "charger_1",
                                "slots": [
                                    {"hour": 2, "date": "2024-01-16", "current_amps": 16, "soc_after": 100, "price": 0.25, "cost": 0.80},
                                ],
                                "total_cost": 0.80,
                            }
                        ],
                        "reasoning": "Test plan",
                    }
                }
            ]
        }

        with patch.object(planner, "_call_api", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            plans = await planner.create_plan(
                chargers=chargers,
                total_max_current_a=32,
                today_prices=[0.30] * 24,
                tomorrow_prices=[0.25] * 24,
            )

            mock_call.assert_called_once()
            assert len(plans) == 1

    @pytest.mark.asyncio
    async def test_validate_plan_calls_api(self):
        planner = AnthropicChargingPlanner("fake_api_key")

        plans = [
            ChargingPlan(
                charger_id="charger_1",
                created_at=datetime.now(),
                departure_time=datetime.now() + timedelta(hours=10),
                slots=[],
            )
        ]

        mock_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "validate_plan",
                    "input": {"replan_needed": False, "reason": "OK"},
                }
            ]
        }

        with patch.object(planner, "_call_api", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await planner.validate_plan(
                current_plans=plans,
                new_prices_today=[0.30] * 24,
                new_prices_tomorrow=[0.25] * 24,
            )

            mock_call.assert_called_once()
            assert result.replan_needed is False


class TestChargingHistory:
    def test_session_fields(self):
        now = datetime.now()
        session = ChargingSession(
            charger_entry_id="charger_1",
            vehicle_soc_entity="sensor.car_soc",
            start_time=now,
            end_time=now + timedelta(hours=5),
            start_soc=20.0,
            end_soc=80.0,
            energy_kwh=45.0,
            avg_power_kw=9.0,
        )

        assert session.avg_power_kw == 9.0
        assert session.energy_kwh == 45.0
        assert session.start_soc == 20.0
        assert session.end_soc == 80.0

    def test_get_expected_charging_rate_no_sessions(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)

        result = tracker.get_expected_charging_rate("unknown_charger")

        assert result is None

    def test_get_expected_charging_rate_with_sessions(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        now = datetime.now()

        tracker._data.sessions["charger_1"] = [
            ChargingSession(
                charger_entry_id="charger_1",
                vehicle_soc_entity="sensor.car_soc",
                start_time=now,
                end_time=now + timedelta(hours=5),
                start_soc=20.0,
                end_soc=80.0,
                energy_kwh=45.0,
                avg_power_kw=9.0,
            ),
            ChargingSession(
                charger_entry_id="charger_1",
                vehicle_soc_entity="sensor.car_soc",
                start_time=now,
                end_time=now + timedelta(hours=4),
                start_soc=30.0,
                end_soc=90.0,
                energy_kwh=42.0,
                avg_power_kw=10.5,
            ),
        ]

        result = tracker.get_expected_charging_rate("charger_1")

        assert result == pytest.approx(9.75, rel=0.01)

    def test_get_charging_efficiency(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        now = datetime.now()

        tracker._data.sessions["charger_1"] = [
            ChargingSession(
                charger_entry_id="charger_1",
                vehicle_soc_entity="sensor.car_soc",
                start_time=now,
                end_time=now + timedelta(hours=5),
                start_soc=20.0,
                end_soc=80.0,
                energy_kwh=45.0,
                avg_power_kw=9.0,
            ),
        ]

        result = tracker.get_charging_efficiency("charger_1")

        assert result == pytest.approx(0.75, rel=0.01)

    def test_get_sessions_for_charger(self):
        mock_hass = MagicMock()
        tracker = ChargingHistoryTracker(mock_hass)
        now = datetime.now()

        tracker._data.sessions["charger_1"] = [
            ChargingSession(
                charger_entry_id="charger_1",
                vehicle_soc_entity="sensor.car_soc",
                start_time=now, end_time=now + timedelta(hours=5),
                start_soc=20.0, end_soc=80.0, energy_kwh=45.0, avg_power_kw=9.0,
            ),
        ]
        tracker._data.sessions["charger_2"] = [
            ChargingSession(
                charger_entry_id="charger_2",
                vehicle_soc_entity="sensor.car_soc",
                start_time=now, end_time=now + timedelta(hours=4),
                start_soc=30.0, end_soc=90.0, energy_kwh=42.0, avg_power_kw=10.5,
            ),
        ]

        result = tracker.get_sessions_for_charger("charger_1")

        assert len(result) == 1
        assert result[0].charger_entry_id == "charger_1"


class TestSmartChargerDepartureTime:
    def test_parse_departure_time_tomorrow(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        now = datetime(2024, 1, 15, 22, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 16
        assert result.hour == 7
        assert result.minute == 0

    def test_parse_departure_time_today(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        now = datetime(2024, 1, 15, 5, 0, 0)
        result = charger._parse_departure_time("07:00:00", now)

        assert result.day == 15
        assert result.hour == 7

    def test_parse_departure_time_short_format(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        now = datetime(2024, 1, 15, 22, 0, 0)
        result = charger._parse_departure_time("07:30", now)

        assert result.hour == 7
        assert result.minute == 30


class TestSmartChargerNordpoolReading:
    def test_get_nordpool_prices_with_dict_format(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.attributes = {
            "prices_today": [
                {"hour": 0, "price": 0.30},
                {"hour": 1, "price": 0.28},
                {"hour": 2, "price": 0.25},
            ],
            "tomorrow_available": True,
            "prices_tomorrow": [
                {"hour": 0, "price": 0.22},
                {"hour": 1, "price": 0.20},
            ],
        }
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.electricity_price", [], 32)

        today, tomorrow = charger._get_nordpool_prices()

        assert today == [0.30, 0.28, 0.25]
        assert tomorrow == [0.22, 0.20]

    def test_get_nordpool_prices_tomorrow_not_available(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.attributes = {
            "prices_today": [{"hour": 0, "price": 0.30}],
            "tomorrow_available": False,
            "prices_tomorrow": [],
        }
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.electricity_price", [], 32)

        today, tomorrow = charger._get_nordpool_prices()

        assert today == [0.30]
        assert tomorrow is None

    def test_get_nordpool_prices_entity_not_found(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_hass.states.get.return_value = None

        charger = SmartCharger(mock_hass, "api_key", "sensor.electricity_price", [], 32)

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

        charger = SmartCharger(mock_hass, "api_key", "sensor.electricity_price", [], 32)

        today, _ = charger._get_nordpool_prices()

        assert today[0] == pytest.approx(0.30)

    def test_get_nordpool_prices_converts_ore_to_sek(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.attributes = {
            "prices_today": [{"hour": 0, "price": 150.0}],
            "tomorrow_available": False,
            "unit_of_measurement": "öre/kWh",
        }
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.electricity_price", [], 32)

        today, _ = charger._get_nordpool_prices()

        assert today[0] == pytest.approx(1.50)


class TestSocNormalization:
    def test_soc_percent_unchanged(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "75"
        mock_state.attributes = {"unit_of_measurement": "%"}
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._get_soc_normalized("sensor.car_soc")

        assert result == 75.0

    def test_soc_fraction_converted_to_percent(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "0.75"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._get_soc_normalized("sensor.car_soc")

        assert result == 75.0

    def test_soc_large_value_unchanged(self):
        from custom_components.keba_kecontact.smart_charger import SmartCharger

        mock_hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "42"
        mock_state.attributes = {}
        mock_hass.states.get.return_value = mock_state

        charger = SmartCharger(mock_hass, "api_key", "sensor.prices", [], 32)

        result = charger._get_soc_normalized("sensor.car_soc")

        assert result == 42.0
