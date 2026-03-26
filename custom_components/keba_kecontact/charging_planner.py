"""Algorithmic smart charging planner for cost-optimal EV charging."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

DEFAULT_EFFICIENCY = 0.95
VOLTAGE = 230
PHASES = 3
MIN_CURRENT_A = 6


@dataclass
class ChargingSlot:
    """Represents a single time slot's charging configuration."""

    hour: int
    minute: int
    date: str
    current_amps: int
    expected_soc_after: float
    price: float
    cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "minute": self.minute,
            "date": self.date,
            "current_amps": self.current_amps,
            "expected_soc_after": self.expected_soc_after,
            "price": self.price,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingSlot:
        return cls(
            hour=data["hour"],
            minute=data.get("minute", 0),
            date=data["date"],
            current_amps=data["current_amps"],
            expected_soc_after=data.get("expected_soc_after", data.get("soc_after", 0)),
            price=data["price"],
            cost=data["cost"],
        )


@dataclass
class ChargingPlan:
    """Represents a complete charging plan for one charger."""

    charger_id: str
    created_at: datetime
    departure_time: datetime
    slots: list[ChargingSlot] = field(default_factory=list)
    total_cost: float = 0.0
    reasoning: str = ""
    status: str = "active"
    initial_soc: float | None = None
    slot_minutes: int = 15

    def to_dict(self) -> dict[str, Any]:
        return {
            "charger_id": self.charger_id,
            "created_at": self.created_at.isoformat(),
            "departure_time": self.departure_time.isoformat(),
            "slots": [s.to_dict() for s in self.slots],
            "total_cost": self.total_cost,
            "reasoning": self.reasoning,
            "status": self.status,
            "initial_soc": self.initial_soc,
            "slot_minutes": self.slot_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargingPlan:
        return cls(
            charger_id=data["charger_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            departure_time=datetime.fromisoformat(data["departure_time"]),
            slots=[ChargingSlot.from_dict(s) for s in data.get("slots", [])],
            total_cost=data.get("total_cost", 0.0),
            reasoning=data.get("reasoning", ""),
            status=data.get("status", "active"),
            initial_soc=data.get("initial_soc"),
            slot_minutes=data.get("slot_minutes", 15),
        )

    def get_slot_for_time(self, hour: int, minute: int, date: str) -> ChargingSlot | None:
        if not self.slots:
            return None
        slot_minute = (minute // self.slot_minutes) * self.slot_minutes
        for slot in self.slots:
            if slot.hour == hour and slot.minute == slot_minute and slot.date == date:
                return slot
        return None


@dataclass
class ChargerRequirement:
    """Input data for a single charger's charging needs."""

    charger_id: str
    charger_name: str
    current_soc: float
    battery_capacity_kwh: float
    departure_time: datetime
    max_current_a: int
    target_soc: float = 100.0
    charging_efficiency: float | None = None


@dataclass
class PriceSlot:
    """A single price slot with time information."""

    hour: int
    minute: int
    price: float
    date: str


def _slot_to_datetime(slot: PriceSlot, tz) -> datetime:
    return datetime(
        int(slot.date[:4]), int(slot.date[5:7]), int(slot.date[8:10]),
        slot.hour, slot.minute, tzinfo=tz,
    )


def _power_kw(amps: int, efficiency: float) -> float:
    return amps * VOLTAGE * PHASES * efficiency / 1000


def _energy_kwh(amps: int, efficiency: float, slot_minutes: int) -> float:
    return _power_kw(amps, efficiency) * slot_minutes / 60


class ChargingPlanner:
    """Algorithmic planner that computes cost-optimal charging schedules."""

    def compute_plans(
        self,
        chargers: list[ChargerRequirement],
        total_max_current: int,
        today_prices: list[PriceSlot],
        tomorrow_prices: list[PriceSlot] | None,
        now: datetime,
    ) -> list[ChargingPlan]:
        if not chargers or not today_prices:
            return []

        slot_minutes = self._detect_slot_minutes(today_prices)
        all_prices = list(today_prices)
        if tomorrow_prices:
            all_prices.extend(tomorrow_prices)

        tz = now.tzinfo

        charger_needs: list[dict] = []
        for c in chargers:
            efficiency = c.charging_efficiency or DEFAULT_EFFICIENCY
            energy_needed = max(0, (c.target_soc - c.current_soc) / 100 * c.battery_capacity_kwh)
            energy_per_slot = _energy_kwh(c.max_current_a, efficiency, slot_minutes)
            slots_needed = math.ceil(energy_needed / energy_per_slot) if energy_per_slot > 0 else 0

            future_slots = [
                ps for ps in all_prices
                if _slot_to_datetime(ps, tz) >= now
                and _slot_to_datetime(ps, tz) + timedelta(minutes=slot_minutes) <= c.departure_time
            ]
            future_slots.sort(key=lambda ps: ps.price)

            desired = set()
            for ps in future_slots[:slots_needed]:
                desired.add((ps.date, ps.hour, ps.minute))

            charger_needs.append({
                "req": c,
                "efficiency": efficiency,
                "energy_needed": energy_needed,
                "energy_per_slot": energy_per_slot,
                "slots_needed": slots_needed,
                "slots_available": len(future_slots),
                "desired_slots": desired,
                "urgency": slots_needed / max(len(future_slots), 1),
            })

        all_time_keys = set()
        for cn in charger_needs:
            all_time_keys.update(cn["desired_slots"])

        slot_assignments: dict[str, dict[tuple, int]] = {
            cn["req"].charger_id: {} for cn in charger_needs
        }

        for time_key in all_time_keys:
            wanting = [
                cn for cn in charger_needs
                if time_key in cn["desired_slots"]
            ]
            if not wanting:
                continue

            wanting.sort(key=lambda cn: cn["urgency"], reverse=True)

            remaining_current = total_max_current
            for cn in wanting:
                amps = min(cn["req"].max_current_a, remaining_current)
                if amps < MIN_CURRENT_A:
                    amps = 0
                slot_assignments[cn["req"].charger_id][time_key] = amps
                remaining_current -= amps

        plans = []
        for cn in charger_needs:
            c = cn["req"]
            efficiency = cn["efficiency"]
            assigned = slot_assignments[c.charger_id]

            price_lookup = {(ps.date, ps.hour, ps.minute): ps.price for ps in all_prices}

            sorted_keys = sorted(assigned.keys(), key=lambda k: (k[0], k[1], k[2]))

            slots = []
            running_soc = c.current_soc
            total_cost = 0.0

            for date_str, hour, minute in sorted_keys:
                amps = assigned[(date_str, hour, minute)]
                if amps == 0:
                    continue
                energy = _energy_kwh(amps, efficiency, slot_minutes)
                soc_gain = energy / c.battery_capacity_kwh * 100
                running_soc = min(c.target_soc, running_soc + soc_gain)
                price = price_lookup.get((date_str, hour, minute), 0)
                cost = price * energy

                slots.append(ChargingSlot(
                    hour=hour,
                    minute=minute,
                    date=date_str,
                    current_amps=amps,
                    expected_soc_after=round(running_soc, 2),
                    price=price,
                    cost=round(cost, 4),
                ))
                total_cost += cost

            reasoning = self._build_reasoning(c, cn, slots, slot_minutes, efficiency, total_cost)

            plans.append(ChargingPlan(
                charger_id=c.charger_id,
                created_at=now,
                departure_time=c.departure_time,
                slots=slots,
                total_cost=round(total_cost, 4),
                reasoning=reasoning,
                status="active",
                initial_soc=c.current_soc,
                slot_minutes=slot_minutes,
            ))

        return plans

    def _build_reasoning(
        self,
        c: ChargerRequirement,
        cn: dict,
        slots: list[ChargingSlot],
        slot_minutes: int,
        efficiency: float,
        total_cost: float,
    ) -> str:
        energy_needed = cn["energy_needed"]
        slots_needed = cn["slots_needed"]
        slots_available = cn["slots_available"]
        soc_delta = c.target_soc - c.current_soc

        parts = [
            f"Behöver {energy_needed:.1f} kWh ({c.current_soc:.0f}%→{c.target_soc:.0f}%, {c.battery_capacity_kwh} kWh batteri).",
            f"{len(slots)} av {slots_available} tillgängliga {slot_minutes}-min slots valda (billigast först).",
        ]
        if efficiency != DEFAULT_EFFICIENCY:
            parts.append(f"Inlärd effektivitet: {efficiency:.0%}.")
        if slots:
            cheapest = min(s.price for s in slots)
            most_expensive = max(s.price for s in slots)
            parts.append(f"Prisspann: {cheapest:.4f}–{most_expensive:.4f} SEK/kWh.")
        parts.append(f"Beräknad kostnad: {total_cost:.2f} SEK.")
        return " ".join(parts)

    def _detect_slot_minutes(self, prices: list[PriceSlot]) -> int:
        count = len(prices)
        if count >= 96:
            return 15
        if count >= 48:
            return 30
        return 60
