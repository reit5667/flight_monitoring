from datetime import datetime

from db import get_conn as _get_conn

from models.cdc import CdcEvent
from models.flight import Flight


def _parse_key(flight_key: str) -> tuple[str, str | None, datetime, int]:
    provider, fn_str, dep_str, rid_str = flight_key.split("|")
    flight_number = None if fn_str == "None" else fn_str
    return provider, flight_number, datetime.fromisoformat(dep_str), int(rid_str)


def _index(flights: list[Flight]) -> dict[tuple, Flight]:
    return {(f.provider, f.flight_number, f.departure_time, f.route_id): f for f in flights}


def _params(f: Flight) -> dict:
    return {
        "route_id": f.route_id,
        "provider": f.provider,
        "airline": f.airline,
        "flight_number": f.flight_number,
        "origin": f.origin,
        "destination": f.destination,
        "departure_time": f.departure_time,
        "arrival_time": f.arrival_time,
        "duration_minutes": f.duration,
        "stops": f.stops,
        "price": float(f.price),
        "currency": f.currency,
        "scraped_at": f.scraped_at,
    }


_UPSERT = """
INSERT INTO flights_current (
    route_id, provider, airline, flight_number,
    origin, destination, departure_time, arrival_time,
    duration_minutes, stops, price, currency, scraped_at
) VALUES (
    %(route_id)s, %(provider)s, %(airline)s, %(flight_number)s,
    %(origin)s, %(destination)s, %(departure_time)s, %(arrival_time)s,
    %(duration_minutes)s, %(stops)s, %(price)s, %(currency)s, %(scraped_at)s
)
ON CONFLICT (provider, flight_number, departure_time, route_id) DO UPDATE SET
    airline          = EXCLUDED.airline,
    arrival_time     = EXCLUDED.arrival_time,
    duration_minutes = EXCLUDED.duration_minutes,
    stops            = EXCLUDED.stops,
    price            = EXCLUDED.price,
    currency         = EXCLUDED.currency,
    scraped_at       = EXCLUDED.scraped_at
"""

_UPDATE = """
UPDATE flights_current SET
    airline          = %(airline)s,
    arrival_time     = %(arrival_time)s,
    duration_minutes = %(duration_minutes)s,
    stops            = %(stops)s,
    price            = %(price)s,
    currency         = %(currency)s,
    scraped_at       = %(scraped_at)s
WHERE provider      = %(provider)s
  AND flight_number IS NOT DISTINCT FROM %(flight_number)s
  AND departure_time = %(departure_time)s
  AND route_id      = %(route_id)s
"""

_DELETE = """
DELETE FROM flights_current
WHERE provider      = %(provider)s
  AND flight_number IS NOT DISTINCT FROM %(flight_number)s
  AND departure_time = %(departure_time)s
  AND route_id      = %(route_id)s
"""


def apply_cdc_to_current(events: list[CdcEvent], flights: list[Flight]) -> None:
    if not events:
        return

    flight_index = _index(flights)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            for event in events:
                key = _parse_key(event.flight_key)
                if event.event_type == "INSERT":
                    cur.execute(_UPSERT, _params(flight_index[key]))
                elif event.event_type == "UPDATE":
                    cur.execute(_UPDATE, _params(flight_index[key]))
                else:  # DELETE
                    provider, flight_number, departure_time, route_id = key
                    cur.execute(_DELETE, {
                        "provider": provider,
                        "flight_number": flight_number,
                        "departure_time": departure_time,
                        "route_id": route_id,
                    })
