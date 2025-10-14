"""Keba KeContact client for managing communication with a single charger."""

import asyncio
import logging
from typing import Optional, Dict, Any
from .udp_handler import KebaUdpHandler, UdpMessage
from .protocol import (
    KebaCommand,
    KebaResponse,
    Report1,
    Report2,
    Report3,
    Report100,
)

_LOGGER = logging.getLogger(__name__)


class KebaClient:
    """Client for communicating with a single Keba KeContact charger.

    This client handles communication with one specific charger via its IP address.
    Multiple clients can use the same UDP handler since filtering is done by IP.

    For Home Assistant integration, use KebaUdpManager to get a shared handler:

        from keba_kecontact.manager import KebaUdpManager

        manager = KebaUdpManager.get_instance()
        await manager.start()

        client = KebaClient("192.168.1.100", use_global_handler=True)
        await client.connect()
    """

    def __init__(
        self,
        ip_address: str,
        udp_handler: Optional[KebaUdpHandler] = None,
        use_global_handler: bool = False
    ):
        """Initialize the Keba client.

        Args:
            ip_address: IP address of the Keba charger
            udp_handler: Shared UDP handler, or None to create a new one
            use_global_handler: If True, use the global manager's handler (for Home Assistant)
        """
        self._ip_address = ip_address
        self._use_global_handler = use_global_handler
        self._owns_handler = False
        self._response_queue: asyncio.Queue[KebaResponse] = asyncio.Queue()
        self._connected = False

        if use_global_handler:
            from .manager import KebaUdpManager
            manager = KebaUdpManager.get_instance()
            self._udp_handler = manager.get_handler()
        elif udp_handler is not None:
            self._udp_handler = udp_handler
        else:
            self._udp_handler = KebaUdpHandler()
            self._owns_handler = True

    @property
    def ip_address(self) -> str:
        """Get the IP address of this charger."""
        return self._ip_address

    async def connect(self):
        """Connect to the charger."""
        if self._connected:
            return

        if self._owns_handler:
            await self._udp_handler.start()

        if self._use_global_handler:
            from .manager import KebaUdpManager
            manager = KebaUdpManager.get_instance()
            await manager.register_client()

        self._udp_handler.register_callback(self._ip_address, self._on_message)
        self._connected = True
        _LOGGER.info(f"Connected to Keba charger at {self._ip_address}")

    async def disconnect(self):
        """Disconnect from the charger."""
        if not self._connected:
            return

        self._udp_handler.unregister_callback(self._ip_address)

        if self._use_global_handler:
            from .manager import KebaUdpManager
            manager = KebaUdpManager.get_instance()
            await manager.unregister_client()

        if self._owns_handler:
            await self._udp_handler.stop()

        self._connected = False
        _LOGGER.info(f"Disconnected from Keba charger at {self._ip_address}")

    async def send_command(self, command: str, timeout: float = 2.0) -> KebaResponse:
        """Send a command and wait for response.

        Args:
            command: Command string to send
            timeout: Timeout in seconds

        Returns:
            Parsed response from the charger

        Raises:
            TimeoutError: If no response is received within timeout
            RuntimeError: If not connected
        """
        if not self._connected:
            raise RuntimeError("Client is not connected")

        while not self._response_queue.empty():
            self._response_queue.get_nowait()

        await self._udp_handler.send_message(self._ip_address, command)

        try:
            response = await asyncio.wait_for(
                self._response_queue.get(),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(f"No response received from {self._ip_address} within {timeout}s")

    async def get_report_1(self) -> Report1:
        """Get report 1 - Product information."""
        response = await self.send_command(KebaCommand.REPORT_1)
        if not response.is_json or not response.parsed_data:
            raise ValueError(f"Invalid response for report 1: {response.raw_data}")
        return Report1(response.parsed_data)

    async def get_report_2(self) -> Report2:
        """Get report 2 - Current state."""
        response = await self.send_command(KebaCommand.REPORT_2)
        if not response.is_json or not response.parsed_data:
            raise ValueError(f"Invalid response for report 2: {response.raw_data}")
        return Report2(response.parsed_data)

    async def get_report_3(self) -> Report3:
        """Get report 3 - Power and energy measurements."""
        response = await self.send_command(KebaCommand.REPORT_3)
        if not response.is_json or not response.parsed_data:
            raise ValueError(f"Invalid response for report 3: {response.raw_data}")
        return Report3(response.parsed_data)

    async def get_report_100(self) -> Report100:
        """Get report 100 - Session information."""
        response = await self.send_command(KebaCommand.REPORT_100)
        if not response.is_json or not response.parsed_data:
            raise ValueError(f"Invalid response for report 100: {response.raw_data}")
        return Report100(response.parsed_data)

    async def enable(self):
        """Enable the charging station."""
        await self.send_command(KebaCommand.ENABLE)

    async def disable(self):
        """Disable the charging station."""
        await self.send_command(KebaCommand.DISABLE)

    async def set_current(self, milliamps: int):
        """Set the charging current limit.

        Args:
            milliamps: Current limit in milliamps (mA)
        """
        command = KebaCommand.CURR.replace("{value}", str(milliamps))
        await self.send_command(command)

    async def set_energy(self, energy: int):
        """Set energy limit for charging session.

        Args:
            energy: Energy limit in 0.1 Wh units
        """
        command = KebaCommand.SETENERGY.replace("{energy}", str(energy))
        await self.send_command(command)

    async def set_output(self, output: int):
        """Set output/relay state.

        Args:
            output: Output value
        """
        command = KebaCommand.OUTPUT.replace("{output}", str(output))
        await self.send_command(command)

    async def start_charging(self):
        """Start charging session."""
        await self.send_command(KebaCommand.START)

    async def stop_charging(self):
        """Stop charging session."""
        await self.send_command(KebaCommand.STOP)

    async def display_text(self, text: str):
        """Display text on the charger display.

        Args:
            text: Text to display
        """
        command = KebaCommand.DISPLAY_TEXT.replace("{text}", text)
        await self.send_command(command)

    async def unlock_socket(self):
        """Unlock the socket to release the cable.

        Note: The charging process should be stopped before unlocking.
        """
        await self.send_command(KebaCommand.UNLOCK)

    def _on_message(self, message: UdpMessage):
        """Internal callback for received messages.

        Args:
            message: Received UDP message
        """
        response = KebaResponse.from_raw(message.data)
        self._response_queue.put_nowait(response)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
