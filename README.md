<h1 align="center">Keba KeContact Home Assistant Integration</h1>

<p align="center">
  <a href="https://github.com/custom-components/hacs">
    <img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS Custom"/>
  </a>
  <a href="https://github.com/jonaswikstrom/keba_kecontact_homeassistant/releases">
    <img src="https://img.shields.io/github/v/release/jonaswikstrom/keba_kecontact_homeassistant" alt="GitHub Release"/>
  </a>
  <a href="https://github.com/jonaswikstrom/keba_kecontact_homeassistant/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/jonaswikstrom/keba_kecontact_homeassistant" alt="License"/>
  </a>
</p>

<p align="center">
  Home Assistant integration for Keba KeContact P20/P30 electric vehicle chargers.
</p>

## Features

- **Multiple Charger Support** - Control multiple Keba chargers on your network
- **Automatic Load Balancing** - Intelligent current distribution between multiple chargers
- **Real-time Monitoring** - Power, energy, voltage, current, and state sensors
- **Aggregated Statistics** - Combined power and energy metrics across all chargers
- **Binary Sensors** - Charging status, cable connection, and lock state
- **Remote Control** - Enable/disable charging, set current limits, start/stop sessions
- **RFID Authentication** - Lock/unlock control for chargers with authentication
- **Display Messages** - Send text notifications to charger display
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

**Automatic Load Balancing**: When you add a second charger, a **Charging Coordinator** is automatically created! This coordinator:
- Manages load balancing between all your chargers
- Provides aggregated statistics (total power, energy, etc.)
- Prevents overload by distributing available current intelligently

### RFID Configuration (Optional)

If your charger requires RFID authentication, you can configure RFID tags:

1. Go to **Settings** → **Devices & Services**
2. Find your Keba KeContact integration
3. Click **Configure**
4. Enter your RFID tag and class (obtained from your charger)
5. Click **Submit**

The lock entity will only be created if authentication is required (DIP-Sw2 bit 4).

## Entities

The integration creates the following entities for each charger:

### Sensors (Per Charger)

- **Power** - Current power consumption (kW)
- **Session Energy** - Energy consumed in current session (kWh)
- **Total Energy** - Total energy consumed by charger (kWh)
- **State** - Current charging state (starting, ready, charging, etc.)
- **Plug Status** - Connection status of charging cable
- **Current Phase 1/2/3** - Current per phase (A)
- **Voltage Phase 1/2/3** - Voltage per phase (V)
- **Max Current** - Current limit setting (A)

### Binary Sensors (Per Charger)

- **Plugged on EV** - Is cable plugged into vehicle
- **Charging** - Is currently charging
- **Enable User** - User enable status
- **Cable Plugged on Station** - Is cable plugged into station (disabled by default)
- **Cable Locked** - Is cable locked (disabled by default)
- **Enable System** - System enable status (diagnostic, disabled by default)

### Controls (Per Charger)

- **Charging Enabled** (Switch) - Enable/disable charging
- **Current Limit** (Number) - Set charging current limit (6-32A)
- **Start Charging** (Button) - Start a charging session
- **Stop Charging** (Button) - Stop a charging session
- **Authentication** (Lock) - Lock/unlock charging with RFID (only if auth required)
- **Display** (Notify) - Send text messages to charger display (max 23 characters)

### Charging Coordinator (Automatic with 2+ Chargers)

When you have multiple chargers, a Charging Coordinator is automatically created with these entities:

#### Coordinator Sensors
- **Total Power** - Combined power consumption from all chargers (kW)
- **Total Session Energy** - Combined session energy from all chargers (kWh)
- **Total Energy** - Combined lifetime energy from all chargers (kWh)
- **Active Chargers** - Number of chargers currently charging
- **Current Distribution** - Description of how current is distributed

#### Coordinator Binary Sensors
- **Load Balancing Active** - Shows if load balancing is actively distributing current (on when 2+ chargers are charging and strategy is not "Off")

#### Coordinator Controls
- **Max Current** (Number) - Total available current to distribute (6-63A)
- **Strategy** (Select) - Load balancing strategy:
  - **Off** - No automatic balancing, manual control only
  - **Equal** - Distribute current equally between active chargers
  - **Priority** - Distribute based on priority (configurable in options)

#### Configuring Priority
To set which charger gets priority when using Priority strategy:
1. Go to **Settings** → **Devices & Services** → **Keba KeContact**
2. Click **Configure** on the Charging Coordinator device
3. Set priority numbers for each charger (1 = highest priority, 2 = second, etc.)
4. Lower priority number = gets current first

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

### Load Balancing Based on Main Fuse Capacity

```yaml
automation:
  - alias: "Set charging coordinator max current based on house load"
    trigger:
      - platform: state
        entity_id: sensor.house_power_consumption
    action:
      - service: number.set_value
        target:
          entity_id: number.keba_coordinator_max_current
        data:
          value: >
            {% set main_fuse = 25 %}
            {% set house_load_a = (states('sensor.house_power_consumption') | float / 230) %}
            {% set available = main_fuse - house_load_a %}
            {{ [6, [available, 32] | min] | max | round(0) }}
```

### Smart Equal Distribution for Two Chargers

With the coordinator strategy set to "Equal", both chargers automatically share available current:

```yaml
# Set coordinator to equal distribution mode
service: select.select_option
target:
  entity_id: select.keba_coordinator_strategy
data:
  option: "equal"

# Set total available current (e.g., 32A main fuse)
service: number.set_value
target:
  entity_id: number.keba_coordinator_max_current
data:
  value: 32
```

Now when both cars charge, each gets 16A automatically!

### Priority Charging for Company vs Guest Car

```yaml
# Set coordinator to priority mode
service: select.select_option
target:
  entity_id: select.keba_coordinator_strategy
data:
  option: "priority"

# Company car (first charger) gets priority, guest car gets remainder
```

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
        entity_id: binary_sensor.keba_192_168_1_100_charging
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Charging Complete"
          message: "Your vehicle has finished charging ({{ states('sensor.keba_192_168_1_100_session_energy') }} kWh)"
```

### Display Welcome Message When Cable Connected

```yaml
automation:
  - alias: "Display welcome when cable plugged"
    trigger:
      - platform: state
        entity_id: binary_sensor.keba_192_168_1_100_plugged_on_ev
        to: "on"
    action:
      - service: notify.keba_192_168_1_100_display
        data:
          message: "Welcome! Charging..."
```

### Auto-lock After Charging

```yaml
automation:
  - alias: "Lock charger after charging complete"
    trigger:
      - platform: state
        entity_id: binary_sensor.keba_192_168_1_100_charging
        from: "on"
        to: "off"
        for: "00:05:00"
    action:
      - service: lock.lock
        target:
          entity_id: lock.keba_192_168_1_100_authentication
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