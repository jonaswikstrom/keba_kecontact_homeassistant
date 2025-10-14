"""Constants for the Keba KeContact integration."""

DOMAIN = "keba_kecontact"

CONF_IP_ADDRESS = "ip_address"

DEFAULT_SCAN_INTERVAL = 10

ATTR_CURRENT_LIMIT = "current_limit"
ATTR_MAX_CURRENT = "max_current"
ATTR_SESSION_ENERGY = "session_energy"
ATTR_TOTAL_ENERGY = "total_energy"
ATTR_STATE = "state"
ATTR_PLUG = "plug"
ATTR_SERIAL = "serial"
ATTR_PRODUCT = "product"
ATTR_FIRMWARE = "firmware"

STATE_STARTING = "starting"
STATE_NOT_READY = "not_ready"
STATE_READY = "ready"
STATE_CHARGING = "charging"
STATE_ERROR = "error"
STATE_AUTHORIZATION_REJECTED = "authorization_rejected"

PLUG_UNPLUGGED = "unplugged"
PLUG_PLUGGED_ON_STATION = "plugged_on_station"
PLUG_PLUGGED_ON_STATION_LOCKED = "plugged_on_station_locked"
PLUG_PLUGGED_ON_STATION_AND_EV = "plugged_on_station_and_ev"
PLUG_PLUGGED_ON_STATION_AND_EV_LOCKED = "plugged_on_station_and_ev_locked"
