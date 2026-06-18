"""Integration tests for warehouse/current.py — requires running PostgreSQL (docker compose up -d)."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import psycopg2
import pytest

from warehouse.current import apply_cdc_to_current, _get_conn
from cdc.engine import compare_snapshots
from models.flight import Flight

_NOW = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
_DEP = datetime(2026, 6, 25, 8, 0, 0, tzinfo=timezone.utc)
_ARR = datetime(2026, 6, 25, 11, 30, 0, tzinfo=timezone.utc)

# route_id=1 exists from seed migration (SVO→LED)
_ROUTE_ID = 1


def _make_flight(**kwargs) -> Flight:
    defaults = dict(
        provider="aviasales",
        airline="SU",
        flight_number="SU100",
        origin="SVO",
        destination="LED",
        departure_time=_DEP,
        arrival_time=_ARR,
        duration=210,
        stops=0,
        price=Decimal("5000.00"),
        currency="RUB",
        scraped_at=_NOW,
        route_id=_ROUTE_ID,
    )
    defaults.update(kwargs)
    return Flight(**defaults)


def _count_rows(cur, provider: str, flight_number: str, departure_time: datetime) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM flights_current
        WHERE provider = %s AND flight_number = %s AND departure_time = %s
        """,
        (provider, flight_number, departure_time),
    )
    return cur.fetchone()[0]


def _get_price(cur, provider: str, flight_number: str, departure_time: datetime) -> float | None:
    cur.execute(
        """
        SELECT price FROM flights_current
        WHERE provider = %s AND flight_number = %s AND departure_time = %s
        """,
        (provider, flight_number, departure_time),
    )
    row = cur.fetchone()
    return float(row[0]) if row else None


@pytest.fixture(autouse=True)
def cleanup_flights_current():
    """Remove test rows after each test to keep DB clean."""
    yield
    conn = _get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM flights_current WHERE provider = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
    conn.close()


class TestInsertEvent:
    def test_insert_creates_row(self):
        flight = _make_flight()
        events = compare_snapshots([], [flight])
        assert len(events) == 1 and events[0].event_type == "INSERT"

        apply_cdc_to_current(events, [flight])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_rows(cur, "aviasales", "SU100", _DEP) == 1
        conn.close()

    def test_insert_stores_correct_price(self):
        flight = _make_flight(price=Decimal("4750.00"))
        events = compare_snapshots([], [flight])

        apply_cdc_to_current(events, [flight])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _get_price(cur, "aviasales", "SU100", _DEP) == 4750.0
        conn.close()

    def test_insert_conflict_becomes_upsert(self):
        """Повторный INSERT с той же уникальной комбинацией обновляет, не дублирует."""
        flight_v1 = _make_flight(price=Decimal("5000.00"))
        flight_v2 = _make_flight(price=Decimal("4500.00"))

        events_v1 = compare_snapshots([], [flight_v1])
        apply_cdc_to_current(events_v1, [flight_v1])

        events_v2 = compare_snapshots([], [flight_v2])
        apply_cdc_to_current(events_v2, [flight_v2])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_rows(cur, "aviasales", "SU100", _DEP) == 1
            assert _get_price(cur, "aviasales", "SU100", _DEP) == 4500.0
        conn.close()


class TestUpdateEvent:
    def test_update_changes_price(self):
        prev = _make_flight(price=Decimal("6000.00"))
        curr = _make_flight(price=Decimal("5200.00"))

        apply_cdc_to_current(compare_snapshots([], [prev]), [prev])
        events = compare_snapshots([prev], [curr])
        assert events[0].event_type == "UPDATE"

        apply_cdc_to_current(events, [curr])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _get_price(cur, "aviasales", "SU100", _DEP) == 5200.0
        conn.close()

    def test_update_does_not_create_extra_row(self):
        prev = _make_flight(price=Decimal("6000.00"))
        curr = _make_flight(price=Decimal("5200.00"))

        apply_cdc_to_current(compare_snapshots([], [prev]), [prev])
        apply_cdc_to_current(compare_snapshots([prev], [curr]), [curr])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_rows(cur, "aviasales", "SU100", _DEP) == 1
        conn.close()


class TestDeleteEvent:
    def test_delete_removes_row(self):
        flight = _make_flight()
        apply_cdc_to_current(compare_snapshots([], [flight]), [flight])

        events = compare_snapshots([flight], [])
        assert events[0].event_type == "DELETE"
        apply_cdc_to_current(events, [])

        conn = _get_conn()
        with conn.cursor() as cur:
            assert _count_rows(cur, "aviasales", "SU100", _DEP) == 0
        conn.close()

    def test_delete_nonexistent_is_silent(self):
        """DELETE на несуществующую запись не падает."""
        flight = _make_flight()
        events = compare_snapshots([flight], [])
        apply_cdc_to_current(events, [])  # should not raise


class TestBatchTransaction:
    def test_batch_of_ten_all_applied(self):
        flights = [
            _make_flight(flight_number=f"SU{100 + i}", price=Decimal(f"{5000 + i * 100}"))
            for i in range(10)
        ]
        events = compare_snapshots([], flights)
        assert len(events) == 10

        apply_cdc_to_current(events, flights)

        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM flights_current WHERE provider = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
            assert cur.fetchone()[0] == 10
        conn.close()

    def test_error_mid_batch_triggers_rollback(self):
        """Ошибка в середине пакета откатывает все изменения."""
        flight = _make_flight(flight_number="SU999")
        insert_event = compare_snapshots([], [flight])[0]

        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO flights_current (
                        route_id, provider, airline, flight_number,
                        origin, destination, departure_time, arrival_time,
                        duration_minutes, stops, price, currency, scraped_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (_ROUTE_ID, "aviasales", "SU", "SU999",
                     "SVO", "LED", _DEP, _ARR, 210, 0, 5000.0, "RUB", _NOW),
                )
        conn.close()

        # Patch cursor.execute to raise on 2nd call (mid-batch)
        real_connect = psycopg2.connect
        call_count = {"n": 0}

        def patched_execute(self_cur, query, params=None):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise psycopg2.DatabaseError("simulated mid-batch failure")
            return real_cursor_execute(self_cur, query, params)

        with _get_conn() as probe_conn:
            real_cursor_execute = probe_conn.cursor().__class__.execute

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        execute_calls = []
        mock_conn.cursor.return_value.execute = lambda *a: (_ for _ in ()).throw(
            psycopg2.DatabaseError("simulated mid-batch failure")
        ) if len(execute_calls) >= 1 else execute_calls.append(a)

        # Simpler: just verify via real DB that a ValueError stops the batch
        flight_a = _make_flight(flight_number="SU100")
        flight_b = _make_flight(flight_number="SU200")
        events_two = compare_snapshots([], [flight_a, flight_b])

        original_get_conn = __import__("warehouse.current", fromlist=["_get_conn"])._get_conn

        patched_conn = _get_conn()

        class FailingCursor:
            _real_cur = None
            _calls = 0

            def __enter__(self):
                self._real_cur = patched_conn.cursor()
                return self

            def __exit__(self, *args):
                self._real_cur.close()
                return False

            def execute(self, query, params=None):
                self._calls += 1
                if self._calls >= 2:
                    raise psycopg2.DatabaseError("simulated mid-batch failure")
                self._real_cur.execute(query, params)

        class FailingConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type:
                    patched_conn.rollback()
                else:
                    patched_conn.commit()
                return False

            def cursor(self):
                return FailingCursor()

        with patch("warehouse.current._get_conn", return_value=FailingConn()):
            with pytest.raises(psycopg2.DatabaseError, match="simulated mid-batch failure"):
                apply_cdc_to_current(events_two, [flight_a, flight_b])

        # SU100 was inserted before the failure — should be rolled back
        verify_conn = _get_conn()
        with verify_conn.cursor() as cur:
            assert _count_rows(cur, "aviasales", "SU100", _DEP) == 0
        verify_conn.close()
        patched_conn.close()

    def test_empty_events_is_noop(self):
        apply_cdc_to_current([], [])  # should not raise or connect
