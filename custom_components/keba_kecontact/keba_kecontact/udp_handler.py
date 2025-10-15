"""UDP communication handler with IP-based filtering for multiple chargers."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Dict
import json

_LOGGER = logging.getLogger(__name__)

KEBA_UDP_PORT = 7090


@dataclass
class UdpMessage:
    """Represents a UDP message with IP information."""

    ip_address: str
    data: str
    raw_bytes: bytes


class KebaUdpHandler:
    """Handles UDP communication with multiple Keba chargers on port 7090.

    Since all Keba chargers communicate on the same port (7090), this handler
    filters messages based on IP address to route them to the correct client.
    """

    def __init__(self, local_ip: str = "0.0.0.0"):
        """Initialize the UDP handler.

        Args:
            local_ip: Local IP address to bind to. Use "0.0.0.0" for all interfaces.
        """
        self._local_ip = local_ip
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional['KebaUdpProtocol'] = None
        self._callbacks: Dict[str, Callable[[UdpMessage], None]] = {}
        self._running = False

    async def start(self):
        """Start the UDP handler."""
        if self._running:
            return

        loop = asyncio.get_event_loop()

        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: KebaUdpProtocol(self._on_message_received),
            local_addr=(self._local_ip, KEBA_UDP_PORT)
        )

        self._running = True
        _LOGGER.info(f"UDP handler started on {self._local_ip}:{KEBA_UDP_PORT}")

    async def stop(self):
        """Stop the UDP handler."""
        if not self._running:
            return

        if self._transport:
            self._transport.close()

        self._running = False
        self._callbacks.clear()
        _LOGGER.info("UDP handler stopped")

    def register_callback(self, ip_address: str, callback: Callable[[UdpMessage], None]):
        """Register a callback for messages from a specific IP address.

        Args:
            ip_address: IP address of the Keba charger
            callback: Function to call when a message is received from this IP
        """
        self._callbacks[ip_address] = callback
        _LOGGER.debug(f"Registered callback for {ip_address}")

    def unregister_callback(self, ip_address: str):
        """Unregister callback for a specific IP address.

        Args:
            ip_address: IP address to unregister
        """
        if ip_address in self._callbacks:
            del self._callbacks[ip_address]
            _LOGGER.debug(f"Unregistered callback for {ip_address}")

    async def send_message(self, ip_address: str, message: str):
        """Send a message to a specific Keba charger.

        Args:
            ip_address: IP address of the target charger
            message: Message to send
        """
        if not self._running or not self._transport:
            raise RuntimeError("UDP handler is not running")

        data = message.encode('cp437', 'ignore')
        self._transport.sendto(data, (ip_address, KEBA_UDP_PORT))
        _LOGGER.debug(f"Sent to {ip_address}: {message}")

    def _on_message_received(self, data: bytes, addr: tuple):
        """Internal callback when a message is received.

        Args:
            data: Raw bytes received
            addr: (ip, port) tuple of sender
        """
        ip_address = addr[0]

        try:
            decoded = data.decode('utf-8').strip()
            message = UdpMessage(
                ip_address=ip_address,
                data=decoded,
                raw_bytes=data
            )

            _LOGGER.debug(f"Received from {ip_address}: {decoded}")

            if ip_address in self._callbacks:
                self._callbacks[ip_address](message)
            else:
                _LOGGER.warning(f"No callback registered for {ip_address}, message ignored")

        except UnicodeDecodeError:
            _LOGGER.error(f"Failed to decode message from {ip_address}: {data.hex()}")


class KebaUdpProtocol(asyncio.DatagramProtocol):
    """Asyncio DatagramProtocol implementation for Keba UDP communication."""

    def __init__(self, message_callback: Callable[[bytes, tuple], None]):
        """Initialize the protocol.

        Args:
            message_callback: Function to call when a message is received
        """
        self._message_callback = message_callback

    def connection_made(self, transport):
        """Called when connection is established."""
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        """Called when a datagram is received.

        Args:
            data: Raw bytes received
            addr: (ip, port) tuple of sender
        """
        self._message_callback(data, addr)

    def error_received(self, exc):
        """Called when an error is received."""
        _LOGGER.error(f"UDP error: {exc}")

    def connection_lost(self, exc):
        """Called when connection is lost."""
        if exc:
            _LOGGER.error(f"UDP connection lost: {exc}")
