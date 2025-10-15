# Keba KeContact Integration

Control and monitor your Keba KeContact EV charger directly from Home Assistant.

## Features

- **Real-time Monitoring** - Power, energy, voltage, current, and charging state
- **Remote Control** - Enable/disable charging, set current limits, start/stop sessions
- **Multiple Chargers** - Support for multiple chargers on your network
- **Automatic Load Balancing** - Smart current distribution between chargers (2+ chargers)
- **Aggregated Statistics** - Combined metrics across all your chargers
- **Local Communication** - Direct UDP communication (no cloud required)
- **Easy Setup** - Simple UI configuration with just the IP address

## Quick Setup

1. Ensure your Keba charger is connected to your network
2. Note the IP address of your charger
3. In Home Assistant, go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for "Keba KeContact"
5. Enter your charger's IP address
6. Done! All entities will be created automatically

**Multiple Chargers?** When you add a second charger, a Charging Coordinator is automatically created to manage load balancing!

## Entities Created

### Sensors
- Power consumption (kW)
- Session energy (kWh)
- Total energy (kWh)
- Charging state
- Plug status
- Current per phase (A)
- Voltage per phase (V)

### Controls
- Enable/Disable switch
- Current limit slider (6-63A)
- Start/Stop charging buttons

### Charging Coordinator (2+ Chargers)
- Total power/energy sensors
- Active chargers count
- Max current control (total available)
- Strategy selector (Off/Equal)

## Example: Load Balancing Two Chargers

```yaml
# Set to equal distribution - both chargers share 32A
service: select.select_option
target:
  entity_id: select.keba_coordinator_strategy
data:
  option: "equal"

service: number.set_value
target:
  entity_id: number.keba_coordinator_max_current
data:
  value: 32
```

## Example: Smart Charging Based on Solar

```yaml
automation:
  - alias: "Charge car with solar excess"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_excess_power
        above: 6000
    action:
      - service: number.set_value
        target:
          entity_id: number.keba_current_limit
        data:
          value: >
            {{ (states('sensor.solar_excess_power') | float / 230) | round(0) }}
      - service: switch.turn_on
        target:
          entity_id: switch.keba_charging_enabled
```

## Support

Having issues? Check the [GitHub Issues](https://github.com/jonaswikstrom/keba_kecontact_homeassistant/issues) or enable debug logging:

```yaml
logger:
  logs:
    custom_components.keba_kecontact: debug
```
