import orjson
import psycopg2.extras
from decimal import Decimal
from datetime import datetime

from db import get_conn as _get_conn
from models.cdc import CdcEvent


def _serialize_changed_fields(changed_fields: dict) -> str:
    # orjson handles Decimal and datetime; result must be str for psycopg2 JSONB
    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Not serializable: {type(obj)}")

    return orjson.dumps(changed_fields, default=default).decode()


def save_cdc_events(events: list[CdcEvent]) -> None:
    if not events:
        return

    rows = [
        (
            e.route_id,
            e.source,
            e.flight_key,
            e.event_type,
            e.old_price,
            e.new_price,
            _serialize_changed_fields(e.changed_fields),
            e.occurred_at,
        )
        for e in events
    ]

    with _get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO cdc_events
                    (route_id, source, flight_key, event_type,
                     old_price, new_price, changed_fields, occurred_at)
                VALUES %s
                """,
                rows,
                template="(%s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            )
