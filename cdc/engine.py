from datetime import datetime, timezone
from typing import Any

from models.cdc import CdcEvent
from models.flight import Flight

_COMPARE_FIELDS = ("airline", "arrival_time", "duration", "stops", "price", "currency")


def _flight_key(flight: Flight) -> tuple:
    return (flight.provider, flight.flight_number, flight.departure_time, flight.route_id)


def _flight_key_str(flight: Flight) -> str:
    return f"{flight.provider}|{flight.flight_number}|{flight.departure_time.isoformat()}|{flight.route_id}"


def compare_snapshots(previous: list[Flight], current: list[Flight]) -> list[CdcEvent]:
    now = datetime.now(timezone.utc)
    prev_map: dict[tuple, Flight] = {_flight_key(f): f for f in previous}
    curr_map: dict[tuple, Flight] = {_flight_key(f): f for f in current}

    events: list[CdcEvent] = []

    for key, curr in curr_map.items():
        if key not in prev_map:
            events.append(CdcEvent(
                event_type="INSERT",
                route_id=curr.route_id,
                source=curr.provider,
                flight_key=_flight_key_str(curr),
                new_price=float(curr.price),
                occurred_at=now,
            ))
        else:
            prev = prev_map[key]
            changed: dict[str, dict[str, Any]] = {}
            for field in _COMPARE_FIELDS:
                old_val = getattr(prev, field)
                new_val = getattr(curr, field)
                if old_val != new_val:
                    changed[field] = {"old": old_val, "new": new_val}
            if changed:
                events.append(CdcEvent(
                    event_type="UPDATE",
                    route_id=curr.route_id,
                    source=curr.provider,
                    flight_key=_flight_key_str(curr),
                    old_price=float(prev.price),
                    new_price=float(curr.price),
                    changed_fields=changed,
                    occurred_at=now,
                ))

    for key, prev in prev_map.items():
        if key not in curr_map:
            events.append(CdcEvent(
                event_type="DELETE",
                route_id=prev.route_id,
                source=prev.provider,
                flight_key=_flight_key_str(prev),
                old_price=float(prev.price),
                occurred_at=now,
            ))

    return events
