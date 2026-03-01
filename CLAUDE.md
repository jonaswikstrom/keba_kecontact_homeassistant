# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration for Keba KeContact P20/P30 EV chargers. Communicates via UDP on port 7090. Distributed through HACS (Home Assistant Community Store).

## Commands

```bash
# Run tests
pytest tests/

# Run specific test class
pytest tests/test_smart_charging.py::TestChargingPlan

# Run with verbose output
pytest -v tests/
```

## Architecture

### Entry Types

The integration creates two types of config entries in `__init__.py`:

1. **Charger entries** (`CONF_IP_ADDRESS` present) - Individual Keba chargers
2. **Coordinator entries** (`CONF_COORDINATOR_NAME` present) - Load balancing coordinator managing multiple chargers

When 2+ chargers exist without a coordinator, one is auto-created.

### Key Components

**UDP Communication Layer** (`keba_kecontact/`)
- `KebaUdpManager` - Singleton managing UDP socket shared across chargers
- `KebaClient` - Per-charger client using global handler

**Load Balancing** (`coordinator.py`)
- `KebaChargingCoordinator` - Manages current distribution across chargers
- Strategies: `off`, `equal` (split evenly), `smart` (AI-powered)

**AI Smart Charging** (`smart_charger.py`, `anthropic_client.py`)
- Uses Anthropic API (Sonnet for planning, Haiku for validation)
- Integrates with Nordpool electricity prices
- Creates hourly charging schedules optimizing for cost
- Tracks charging history for efficiency estimates (`charging_history.py`)

**Entity Structure**
- Per-charger: sensors, binary_sensors, switches, numbers, buttons, lock, notify
- Coordinator-level: aggregate sensors, strategy select, max current number
- Smart charging: status and AI reasoning sensors (`smart_charging_sensor.py`)

### Data Flow

1. `KebaDataUpdateCoordinator` (in `sensor.py`) polls charger every 10s
2. Data stored in `hass.data[DOMAIN][entry_id]` with keys: `client`, `coordinator`, `config_entry`, `device_info`
3. `KebaChargingCoordinator` aggregates data from all chargers and applies load balancing

### Smart Charging Flow

1. Car connection detected via charger state sensor change
2. `SmartCharger._on_car_connected()` triggers planning
3. `AnthropicChargingPlanner.create_plan()` calls API with requirements and Nordpool prices
4. Plans stored in `_active_plans`, executed minute-by-minute
5. Nordpool `tomorrow_available` change triggers overnight replan validation

## Testing

Tests mock Home Assistant dependencies in `conftest.py`. The mock structure allows testing smart charging logic without a running HA instance.

## Configuration Options

Per-charger AI config: `vehicle_soc_entity`, `battery_capacity_kwh`, `departure_time`
Coordinator config: `anthropic_api_key`, `nordpool_entity`, `coordinator_max_current`, `coordinator_strategy`
