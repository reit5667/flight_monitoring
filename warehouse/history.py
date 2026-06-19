from datetime import datetime, timezone

from db import get_conn as _get_conn

from models.cdc import CdcEvent
from models.flight import Flight
from warehouse.current import _parse_key, _index, _params


_CLOSE_CURRENT = """
UPDATE flights_history SET
    valid_to   = %(now)s,
    is_current = false
WHERE provider       = %(provider)s
  AND flight_number  IS NOT DISTINCT FROM %(flight_number)s
  AND departure_time = %(departure_time)s
  AND route_id       = %(route_id)s
  AND is_current     = true
"""

_INSERT_HISTORY = """
INSERT INTO flights_history (
    route_id, provider, airline, flight_number,
    origin, destination, departure_time, arrival_time,
    duration_minutes, stops, price, currency, scraped_at,
    valid_from, valid_to, is_current
) VALUES (
    %(route_id)s, %(provider)s, %(airline)s, %(flight_number)s,
    %(origin)s, %(destination)s, %(departure_time)s, %(arrival_time)s,
    %(duration_minutes)s, %(stops)s, %(price)s, %(currency)s, %(scraped_at)s,
    %(valid_from)s, NULL, true
)
"""


def append_history(events: list[CdcEvent], flights: list[Flight]) -> None:
    if not events:
        return

    now = datetime.now(timezone.utc)
    flight_index = _index(flights)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            for event in events:
                key = _parse_key(event.flight_key)
                provider, flight_number, departure_time, route_id = key
                close_params = {
                    "now": now,
                    "provider": provider,
                    "flight_number": flight_number,
                    "departure_time": departure_time,
                    "route_id": route_id,
                }

                if event.event_type == "INSERT":
                    flight = flight_index[key]
                    cur.execute(_INSERT_HISTORY, {**_params(flight), "valid_from": now})

                elif event.event_type == "UPDATE":
                    cur.execute(_CLOSE_CURRENT, close_params)
                    flight = flight_index[key]
                    cur.execute(_INSERT_HISTORY, {**_params(flight), "valid_from": now})

                else:  # DELETE
                    cur.execute(_CLOSE_CURRENT, close_params)
