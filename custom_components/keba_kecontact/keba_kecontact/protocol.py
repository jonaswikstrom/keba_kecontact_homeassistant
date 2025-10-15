"""Keba KeContact protocol definitions and command handling."""

import json
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class KebaCommand(str, Enum):
    """Available Keba KeContact commands.

    Commands are sent as plain text without CR/LF.
    Responses are received as JSON.
    """

    REPORT_1 = "report 1"
    REPORT_2 = "report 2"
    REPORT_3 = "report 3"
    REPORT_100 = "report 100"

    ENABLE = "ena 1"
    DISABLE = "ena 0"

    DISPLAY_TEXT = "display 0 0 0 0 {text}"

    CURR = "curr {value}"

    SETENERGY = "setenergy {energy}"

    OUTPUT = "output {output}"

    START = "start"
    STOP = "stop"

    UNLOCK = "unlock"

    BROADCAST = "i"


@dataclass
class KebaResponse:
    """Represents a parsed response from a Keba charger.

    Keba chargers respond with JSON-formatted data.
    """

    raw_data: str
    parsed_data: Optional[Dict[str, Any]] = None
    is_json: bool = False

    @classmethod
    def from_raw(cls, raw_data: str) -> 'KebaResponse':
        """Create a KebaResponse from raw UDP data.

        Args:
            raw_data: Raw string data from UDP (JSON format)

        Returns:
            Parsed KebaResponse object
        """
        parsed = None
        is_json = False

        stripped = raw_data.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                parsed = json.loads(stripped)
                is_json = True
            except json.JSONDecodeError:
                pass

        return cls(
            raw_data=raw_data,
            parsed_data=parsed,
            is_json=is_json
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from parsed JSON data.

        Args:
            key: Key to retrieve
            default: Default value if key not found

        Returns:
            Value from parsed data or default
        """
        if self.parsed_data:
            return self.parsed_data.get(key, default)
        return default

    @property
    def report_id(self) -> Optional[int]:
        """Get report ID if this is a report response."""
        return self.get("ID")


class Report1:
    """Report 1 - Product information and serial."""

    def __init__(self, data: Dict[str, Any]):
        self.product = data.get("Product")
        self.serial = data.get("Serial")
        self.firmware = data.get("Firmware")
        self.com_module = data.get("COM-module")
        self.backend = data.get("Backend")
        self.dip_switch_1 = data.get("DIP-Sw1")
        self.dip_switch_2 = data.get("DIP-Sw2")

    @property
    def auth_required(self) -> bool:
        """Check if authentication is required (DIP-Sw2 bit 4)."""
        if self.dip_switch_2 is not None:
            try:
                dip_value = int(self.dip_switch_2) if isinstance(self.dip_switch_2, str) else self.dip_switch_2
                return bool(dip_value & 0x10)
            except (ValueError, TypeError):
                return False
        return False

    def __repr__(self):
        return f"Report1(product={self.product}, serial={self.serial}, firmware={self.firmware})"


class Report2:
    """Report 2 - Current state of the charging station."""

    def __init__(self, data: Dict[str, Any]):
        self.state = data.get("State")
        self.error_1 = data.get("Error1")
        self.error_2 = data.get("Error2")
        self.plug = data.get("Plug")
        self.enable_sys = data.get("Enable sys")
        self.enable_user = data.get("Enable user")
        self.max_curr = data.get("Max curr")
        self.max_curr_percent = data.get("Max curr %")
        self.curr_hw = data.get("Curr HW")
        self.curr_user = data.get("Curr user")
        self.curr_fs = data.get("Curr FS")
        self.tmo_fs = data.get("Tmo FS")
        self.curr_timer = data.get("Curr timer")
        self.tmo_ct = data.get("Tmo CT")
        self.setenergy = data.get("Setenergy")
        self.output = data.get("Output")
        self.input = data.get("Input")
        self.serial = data.get("Serial")
        self.sec = data.get("Sec")

    @property
    def failsafe_mode(self) -> bool:
        """Check if failsafe mode is active (Curr FS > 0)."""
        return self.curr_fs is not None and self.curr_fs > 0

    @property
    def authreq(self) -> bool:
        """Check if authentication is required (Input bit 4)."""
        if self.input is not None:
            return bool(self.input & 0x10)
        return False

    @property
    def authon(self) -> bool:
        """Check if authentication is enabled (Input bit 3)."""
        if self.input is not None:
            return bool(self.input & 0x08)
        return False

    @property
    def x2_phase_switch(self) -> bool:
        """Check X2 phase switch status (Input bit 5)."""
        if self.input is not None:
            return bool(self.input & 0x20)
        return False

    @property
    def state_details(self) -> str:
        """Get detailed state description."""
        if self.state is None:
            return "Unknown"

        state_map = {
            0: "Starting",
            1: "Not ready for charging",
            2: "Ready for charging",
            3: "Charging",
            4: "Error",
            5: "Authorization rejected"
        }
        return state_map.get(self.state, f"Unknown state {self.state}")

    def __repr__(self):
        return f"Report2(state={self.state}, plug={self.plug}, max_curr={self.max_curr})"


class Report3:
    """Report 3 - Power and energy measurements."""

    def __init__(self, data: Dict[str, Any]):
        self.u1 = data.get("U1")
        self.u2 = data.get("U2")
        self.u3 = data.get("U3")
        self.i1 = data.get("I1")
        self.i2 = data.get("I2")
        self.i3 = data.get("I3")
        self.p = data.get("P")
        self.pf = data.get("PF")
        self.e_pres = data.get("E pres")
        self.e_total = data.get("E total")
        self.serial = data.get("Serial")
        self.sec = data.get("Sec")

    @property
    def power_kw(self) -> Optional[float]:
        """Get power in kW."""
        if self.p is not None:
            return self.p / 1000.0
        return None

    @property
    def energy_present_kwh(self) -> Optional[float]:
        """Get present energy in kWh."""
        if self.e_pres is not None:
            return self.e_pres / 10000.0
        return None

    @property
    def energy_total_kwh(self) -> Optional[float]:
        """Get total energy in kWh."""
        if self.e_total is not None:
            return self.e_total / 10000.0
        return None

    def __repr__(self):
        return f"Report3(power={self.power_kw}kW, energy={self.energy_present_kwh}kWh)"


class Report100:
    """Report 100 - Session information for RFID."""

    def __init__(self, data: Dict[str, Any]):
        self.session_id = data.get("Session ID")
        self.curr_hw = data.get("Curr HW")
        self.e_start = data.get("E start")
        self.e_pres = data.get("E pres")
        self.started = data.get("started")
        self.ended = data.get("ended")
        self.reason = data.get("reason")
        self.rfid_tag = data.get("RFID tag")
        self.rfid_class = data.get("RFID class")
        self.serial = data.get("Serial")
        self.sec = data.get("Sec")

    @property
    def e_start_kwh(self) -> Optional[float]:
        """Get start energy in kWh."""
        if self.e_start is not None:
            return self.e_start / 10000.0
        return None

    def __repr__(self):
        return f"Report100(session_id={self.session_id}, rfid={self.rfid_tag})"
