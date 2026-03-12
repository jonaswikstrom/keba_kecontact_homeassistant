"""Charging history tracker for learning actual charging rates."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HISTORY_FILE = "keba_charging_history.json"
MAX_SESSIONS_PER_CHARGER = 50


@dataclass
class ChargingSession:
    """Record of a completed charging session."""

    charger_entry_id: str
    vehicle_soc_entity: str
    start_time: datetime
    end_time: datetime
    start_soc: float
    end_soc: float
    energy_kwh: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "charger_entry_id": self.charger_entry_id,
            "vehicle_soc_entity": self.vehicle_soc_entity,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "start_soc": self.start_soc,
            "end_soc": self.end_soc,
            "energy_kwh": self.energy_kwh,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingSession:
        """Deserialize from dictionary."""
        return cls(
            charger_entry_id=data["charger_entry_id"],
            vehicle_soc_entity=data["vehicle_soc_entity"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            start_soc=data["start_soc"],
            end_soc=data["end_soc"],
            energy_kwh=data["energy_kwh"],
        )


@dataclass
class ActiveSession:
    """Tracks an ongoing charging session."""

    charger_entry_id: str
    vehicle_soc_entity: str
    start_time: datetime
    start_soc: float
    start_energy_kwh: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "charger_entry_id": self.charger_entry_id,
            "vehicle_soc_entity": self.vehicle_soc_entity,
            "start_time": self.start_time.isoformat(),
            "start_soc": self.start_soc,
            "start_energy_kwh": self.start_energy_kwh,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveSession:
        """Deserialize from dictionary."""
        return cls(
            charger_entry_id=data["charger_entry_id"],
            vehicle_soc_entity=data["vehicle_soc_entity"],
            start_time=datetime.fromisoformat(data["start_time"]),
            start_soc=data["start_soc"],
            start_energy_kwh=data["start_energy_kwh"],
        )


@dataclass
class ChargingHistoryData:
    """Complete charging history storage."""

    sessions: dict[str, list[ChargingSession]] = field(default_factory=dict)
    active_sessions: dict[str, ActiveSession] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize all data."""
        return {
            "sessions": {
                charger_id: [s.to_dict() for s in sessions]
                for charger_id, sessions in self.sessions.items()
            },
            "active_sessions": {
                charger_id: session.to_dict()
                for charger_id, session in self.active_sessions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingHistoryData:
        """Deserialize from storage."""
        sessions = {}
        for charger_id, session_list in data.get("sessions", {}).items():
            sessions[charger_id] = [ChargingSession.from_dict(s) for s in session_list]
        active_sessions = {}
        for charger_id, session_data in data.get("active_sessions", {}).items():
            active_sessions[charger_id] = ActiveSession.from_dict(session_data)
        return cls(sessions=sessions, active_sessions=active_sessions)


class ChargingHistoryTracker:
    """Tracks charging sessions to learn actual charging rates per vehicle."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the tracker."""
        self.hass = hass
        self._data = ChargingHistoryData()
        self._active_sessions: dict[str, ActiveSession] = {}
        self._storage_path = Path(hass.config.path(HISTORY_FILE))

    async def async_load(self) -> None:
        """Load history from storage."""
        try:
            if self._storage_path.exists():
                content = await self.hass.async_add_executor_job(
                    self._storage_path.read_text
                )
                data = json.loads(content)
                self._data = ChargingHistoryData.from_dict(data)
                self._active_sessions = self._data.active_sessions.copy()
                _LOGGER.info(
                    "Loaded charging history: %d chargers, %d active sessions",
                    len(self._data.sessions),
                    len(self._active_sessions),
                )
        except Exception as err:
            _LOGGER.error("Failed to load charging history: %s", err)
            self._data = ChargingHistoryData()

    async def async_save(self) -> None:
        """Save history to storage."""
        try:
            self._data.active_sessions = self._active_sessions.copy()
            content = json.dumps(self._data.to_dict(), indent=2)
            await self.hass.async_add_executor_job(
                self._storage_path.write_text, content
            )
            _LOGGER.debug("Saved charging history")
        except Exception as err:
            _LOGGER.error("Failed to save charging history: %s", err)

    async def start_session(
        self,
        charger_entry_id: str,
        vehicle_soc_entity: str,
        current_soc: float,
        current_energy_kwh: float,
    ) -> None:
        """Start tracking a new charging session."""
        self._active_sessions[charger_entry_id] = ActiveSession(
            charger_entry_id=charger_entry_id,
            vehicle_soc_entity=vehicle_soc_entity,
            start_time=datetime.now(),
            start_soc=current_soc,
            start_energy_kwh=current_energy_kwh,
        )
        _LOGGER.info(
            "Started tracking session for %s at SoC %.1f%%",
            charger_entry_id,
            current_soc,
        )
        await self.async_save()

    async def end_session(
        self,
        charger_entry_id: str,
        current_soc: float,
        current_energy_kwh: float,
    ) -> ChargingSession | None:
        """End a charging session and calculate statistics."""
        active = self._active_sessions.pop(charger_entry_id, None)
        if not active:
            _LOGGER.debug("No active session found for %s", charger_entry_id)
            return None

        end_time = datetime.now()
        duration_hours = (end_time - active.start_time).total_seconds() / 3600

        if duration_hours < 0.1:
            _LOGGER.debug("Session too short (%.2f hours), not recording", duration_hours)
            return None

        energy_delivered = current_energy_kwh - active.start_energy_kwh
        if energy_delivered <= 0:
            _LOGGER.debug("No energy delivered, not recording session")
            return None

        soc_gained = current_soc - active.start_soc

        session = ChargingSession(
            charger_entry_id=charger_entry_id,
            vehicle_soc_entity=active.vehicle_soc_entity,
            start_time=active.start_time,
            end_time=end_time,
            start_soc=active.start_soc,
            end_soc=current_soc,
            energy_kwh=energy_delivered,
        )

        if charger_entry_id not in self._data.sessions:
            self._data.sessions[charger_entry_id] = []

        self._data.sessions[charger_entry_id].append(session)

        if len(self._data.sessions[charger_entry_id]) > MAX_SESSIONS_PER_CHARGER:
            self._data.sessions[charger_entry_id] = self._data.sessions[charger_entry_id][
                -MAX_SESSIONS_PER_CHARGER:
            ]

        await self.async_save()

        _LOGGER.info(
            "Recorded charging session for %s: %.1f kWh, %.1f%% -> %.1f%% (+%.1f%%)",
            charger_entry_id,
            energy_delivered,
            active.start_soc,
            current_soc,
            soc_gained,
        )

        return session

    def get_charging_efficiency(
        self,
        charger_entry_id: str,
        vehicle_soc_entity: str | None = None,
    ) -> float | None:
        """Calculate charging efficiency (kWh per % SoC) from history."""
        sessions = self._data.sessions.get(charger_entry_id, [])

        if not sessions:
            return None

        if vehicle_soc_entity:
            vehicle_sessions = [
                s for s in sessions if s.vehicle_soc_entity == vehicle_soc_entity
            ]
            if vehicle_sessions:
                sessions = vehicle_sessions

        valid_sessions = [
            s for s in sessions
            if s.end_soc > s.start_soc and s.energy_kwh > 0
        ]

        if not valid_sessions:
            return None

        recent = valid_sessions[-10:]

        total_energy = sum(s.energy_kwh for s in recent)
        total_soc_gained = sum(s.end_soc - s.start_soc for s in recent)

        if total_soc_gained <= 0:
            return None

        kwh_per_percent = total_energy / total_soc_gained

        return kwh_per_percent

    def is_session_active(self, charger_entry_id: str) -> bool:
        """Check if a session is currently being tracked."""
        return charger_entry_id in self._active_sessions

    def get_sessions_for_charger(self, charger_entry_id: str) -> list[ChargingSession]:
        """Get all recorded sessions for a charger."""
        return self._data.sessions.get(charger_entry_id, [])

    def get_all_active_sessions(self) -> dict[str, ActiveSession]:
        """Get all active sessions (for restart detection)."""
        return self._active_sessions.copy()

    def get_active_session(self, charger_entry_id: str) -> ActiveSession | None:
        """Get active session for a specific charger."""
        return self._active_sessions.get(charger_entry_id)
