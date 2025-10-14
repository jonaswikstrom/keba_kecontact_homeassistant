# Keba KeContact Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant integration for Keba KeContact P20/P30 electric vehicle chargers.

## Features

- **Multiple Charger Support** - Control multiple Keba chargers on your network
- **Real-time Monitoring** - Power, energy, voltage, current, and state sensors
- **Remote Control** - Enable/disable charging, set current limits, start/stop sessions
- **UDP Communication** - Direct local communication via UDP (no cloud required)
- **Shared UDP Handler** - Efficient management of multiple chargers using a single UDP socket

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/jonaswikstrom/keba_kecontact_homeassistant`
6. Select category "Integration"
7. Click "Add"
8. Search for "Keba KeContact" and install
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/keba_kecontact` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **Keba KeContact**
4. Enter the IP address of your Keba charger
5. Click **Submit**

The integration will automatically discover the charger and create all entities.

### Multiple Chargers

To add additional chargers, simply repeat the configuration process with each charger's IP address. The integration automatically manages the shared UDP communication.

## Entities

The integration creates the following entities for each charger:

### Sensors

- **Power** - Current power consumption (kW)
- **Session Energy** - Energy consumed in current session (kWh)
- **Total Energy** - Total energy consumed by charger (kWh)
- **State** - Current charging state (starting, ready, charging, etc.)
- **Plug Status** - Connection status of charging cable
- **Current Phase 1/2/3** - Current per phase (A)
- **Voltage Phase 1/2/3** - Voltage per phase (V)
- **Max Current** - Current limit setting (A)

### Controls

- **Charging Enabled** (Switch) - Enable/disable charging
- **Current Limit** (Number) - Set charging current limit (6-32A)
- **Start Charging** (Button) - Start a charging session
- **Stop Charging** (Button) - Stop a charging session

## State Values

### Charging State

- `starting` - Charger is starting up
- `not_ready` - Charger is not ready for charging
- `ready` - Ready to charge, waiting for vehicle
- `charging` - Currently charging
- `error` - Error state
- `auth_rejected` - Authorization rejected (RFID)

### Plug Status

- `unplugged` - No cable connected
- `plugged_station` - Cable connected to station only
- `plugged_station_locked` - Cable locked to station
- `plugged_station_ev` - Cable connected to station and vehicle
- `plugged_station_ev_locked` - Cable locked to both station and vehicle

## Example Automations

### Start Charging When Energy is Cheap

```yaml
automation:
  - alias: "Start charging during cheap energy hours"
    trigger:
      - platform: time
        at: "02:00:00"
    condition:
      - condition: state
        entity_id: sensor.keba_192_168_1_100_state
        state: "ready"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.keba_192_168_1_100_charging_enabled
      - service: button.press
        target:
          entity_id: button.keba_192_168_1_100_start_charging
```

### Limit Current Based on Grid Load

```yaml
automation:
  - alias: "Reduce charging current when grid load is high"
    trigger:
      - platform: numeric_state
        entity_id: sensor.grid_power
        above: 8000
    action:
      - service: number.set_value
        target:
          entity_id: number.keba_192_168_1_100_current_limit
        data:
          value: 6
```

### Notify When Charging Complete

```yaml
automation:
  - alias: "Notify when charging complete"
    trigger:
      - platform: state
        entity_id: sensor.keba_192_168_1_100_state
        from: "charging"
        to: "ready"
    action:
      - service: notify.mobile_app
        data:
          title: "Charging Complete"
          message: "Your vehicle has finished charging ({{ states('sensor.keba_192_168_1_100_session_energy') }} kWh)"
```

## Troubleshooting

### Cannot Connect to Charger

1. Verify the IP address is correct
2. Ensure the charger is on the same network as Home Assistant
3. Check that UDP port 7090 is not blocked by your firewall
4. Try pinging the charger from Home Assistant: `ping <charger_ip>`

### Charger Shows as Unavailable

1. Check network connectivity
2. Restart the integration
3. Check Home Assistant logs for errors: **Settings** → **System** → **Logs**

### Enable Debug Logging

For detailed troubleshooting, add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.keba_kecontact: debug
    keba_kecontact: debug
```

Then restart Home Assistant or reload the logger. Debug logs will show:
- Polling activity every 10 seconds with charger state
- UDP commands sent and responses received
- Detailed error messages with stack traces
- Connection lifecycle events

### Multiple Chargers Not Working

The integration uses a shared UDP handler to support multiple chargers. If you experience issues:

1. Remove all charger integrations
2. Restart Home Assistant
3. Re-add chargers one at a time

## Technical Details

### UDP Communication

Keba KeContact chargers communicate via UDP on port 7090. The integration uses a singleton UDP handler to manage communication with multiple chargers efficiently. Messages are filtered by IP address to route responses to the correct charger.

### Polling Interval

The integration polls the chargers every 10 seconds by default. This provides a good balance between responsiveness and network load.

## Support

- **Issues**: [GitHub Issues](https://github.com/jonaswikstrom/keba_kecontact_homeassistant/issues)
- **Framework**: [Keba KeContact Python Framework](https://github.com/jonaswikstrom/keba_kecontact)

## Credits

This integration is built on the [Keba KeContact Python Framework](https://github.com/jonaswikstrom/keba_kecontact).

## License

MIT License - see LICENSE file for details.