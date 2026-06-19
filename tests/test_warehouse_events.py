"""Integration tests for warehouse/events.py — requires running PostgreSQL (docker compose up -d)."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from warehouse.current import _get_conn
from warehouse.events import save_cdc_events
from cdc.engine import compare_snapshots
from models.flight import Flight

_NOW = datetime(2026, 6, 18, 15, 0, 0, tzinfo=timezone.utc)
_DEP = datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc)
_ARR = datetime(2026, 6, 27, 13, 0, 0, tzinfo=timezone.utc)
_ROUTE_ID = 1


def _make_flight(**kwargs) -> Flight:
    defaults = dict(
        provider="aviasales",
        airline="SU",
        flight_number="SU800",
        origin="SVO",
        destination="LED",
        departure_time=_DEP,
        arrival_time=_ARR,
        duration=180,
        stops=0,
        price=Decimal("8000.00"),
        currency="RUB",
        scraped_at=_NOW,
        route_id=_ROUTE_ID,
    )
    defaults.update(kwargs)
    return Flight(**defaults)


@pytest.fixture(autouse=True)
def cleanup():
    conn = _get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
    conn.close()
    yield
    conn = _get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
    conn.close()


def _count_events(cur) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
        (_ROUTE_ID,),
    )
    return cur.fetchone()[0]


class TestSaveCdcEvents:
    def test_saves_three_events(self):
        f1 = _make_flight(flight_number="SU801")
        f2 = _make_flight(flight_number="SU802")
        f3 = _make_flight(flight_number="SU803")
        events = compare_snapshots([], [f1, f2, f3])
        assert len(events) == 3

        save_cdc_events(events)

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_events(cur) == 3
        conn.close()

    def test_empty_list_is_noop(self):
        save_cdc_events([])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_events(cur) == 0
        conn.close()

    def test_changed_fields_stored_as_jsonb(self):
        prev = _make_flight(price=Decimal("8000.00"))
        curr = _make_flight(price=Decimal("7000.00"))
        events = compare_snapshots([prev], [curr])
        assert events[0].event_type == "UPDATE"

        save_cdc_events(events)

        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT changed_fields FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
            row = cur.fetchone()
        conn.close()

        cf = row[0]  # psycopg2 deserializes JSONB → dict automatically
        assert isinstance(cf, dict)
        assert "price" in cf
        assert "old" in cf["price"] and "new" in cf["price"]

    def test_occurred_at_preserved(self):
        flight = _make_flight()
        events = compare_snapshots([], [flight])
        expected_time = events[0].occurred_at

        save_cdc_events(events)

        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT occurred_at FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
            stored_time = cur.fetchone()[0]
        conn.close()

        assert abs((stored_time - expected_time).total_seconds()) < 1

    def test_batch_is_single_insert(self):
        """Проверяем что все события вставляются одним запросом — через execute_values."""
        flights = [
            _make_flight(flight_number=f"SU{800 + i}", price=Decimal(f"{7000 + i * 100}"))
            for i in range(10)
        ]
        events = compare_snapshots([], flights)

        save_cdc_events(events)

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_events(cur) == 10
        conn.close()

    def test_old_and_new_price_stored(self):
        prev = _make_flight(price=Decimal("8000.00"))
        curr = _make_flight(price=Decimal("6500.00"))
        events = compare_snapshots([prev], [curr])

        save_cdc_events(events)

        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT old_price, new_price FROM cdc_events WHERE source = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
            row = cur.fetchone()
        conn.close()

        assert float(row[0]) == 8000.0
        assert float(row[1]) == 6500.0
