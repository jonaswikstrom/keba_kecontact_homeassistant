"""Global UDP handler manager for shared communication across multiple chargers.

This module provides a singleton pattern for managing a shared UDP handler,
which is essential for Home Assistant integration where multiple device entities
need to share the same UDP socket on port 7090.
"""

import asyncio
import logging
from typing import Optional, Dict
from .udp_handler import KebaUdpHandler

_LOGGER = logging.getLogger(__name__)


class KebaUdpManager:
    """Singleton manager for shared UDP handler.

    This manager ensures that only one UDP handler is created and shared
    across all KebaClient instances. This is critical for Home Assistant
    where multiple entities (sensors, switches, etc.) need to communicate
    with different chargers on the same UDP port.

    Example:
        # In Home Assistant integration setup
        manager = KebaUdpManager.get_instance()
        await manager.start()

        # Each device/entity gets its own client
        client1 = KebaClient("192.168.1.100")
        client2 = KebaClient("192.168.1.101")

        await client1.connect()  # Uses shared handler
        await client2.connect()  # Uses same shared handler
    """

    _instance: Optional['KebaUdpManager'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        """Private constructor. Use get_instance() instead."""
        if KebaUdpManager._instance is not None:
            raise RuntimeError("Use KebaUdpManager.get_instance() instead")

        self._handler: Optional[KebaUdpHandler] = None
        self._client_count: int = 0
        self._started: bool = False

    @classmethod
    def get_instance(cls) -> 'KebaUdpManager':
        """Get the singleton instance of KebaUdpManager.

        Returns:
            The singleton KebaUdpManager instance
        """
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._handler = None
            cls._instance._client_count = 0
            cls._instance._started = False

        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None

    async def start(self):
        """Start the shared UDP handler.

        This should be called once during Home Assistant integration setup.
        """
        async with self._lock:
            if self._started:
                _LOGGER.debug("UDP manager already started")
                return

            if self._handler is None:
                self._handler = KebaUdpHandler()

            await self._handler.start()
            self._started = True
            _LOGGER.info("Global Keba UDP manager started")

    async def stop(self):
        """Stop the shared UDP handler.

        This should be called during Home Assistant integration shutdown.
        Only stops if no clients are connected.
        """
        async with self._lock:
            if not self._started:
                return

            if self._client_count > 0:
                _LOGGER.warning(
                    f"Cannot stop UDP manager, {self._client_count} clients still connected"
                )
                return

            if self._handler:
                await self._handler.stop()

            self._started = False
            _LOGGER.info("Global Keba UDP manager stopped")

    def get_handler(self) -> KebaUdpHandler:
        """Get the shared UDP handler.

        Returns:
            The shared KebaUdpHandler instance

        Raises:
            RuntimeError: If manager has not been started
        """
        if not self._started or self._handler is None:
            raise RuntimeError("KebaUdpManager not started. Call start() first.")

        return self._handler

    async def register_client(self):
        """Register a client that will use the shared handler.

        This increments the client count to prevent premature shutdown.
        """
        async with self._lock:
            self._client_count += 1
            _LOGGER.debug(f"Client registered, total clients: {self._client_count}")

    async def unregister_client(self):
        """Unregister a client.

        This decrements the client count.
        """
        async with self._lock:
            if self._client_count > 0:
                self._client_count -= 1
                _LOGGER.debug(f"Client unregistered, total clients: {self._client_count}")

    @property
    def is_started(self) -> bool:
        """Check if the manager is started."""
        return self._started

    @property
    def client_count(self) -> int:
        """Get the number of registered clients."""
        return self._client_count
