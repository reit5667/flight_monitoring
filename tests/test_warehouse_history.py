"""Integration tests for warehouse/history.py — requires running PostgreSQL (docker compose up -d)."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from warehouse.current import _get_conn, apply_cdc_to_current
from warehouse.history import append_history
from cdc.engine import compare_snapshots
from models.flight import Flight

_NOW = datetime(2026, 6, 18, 14, 0, 0, tzinfo=timezone.utc)
_DEP = datetime(2026, 6, 26, 9, 0, 0, tzinfo=timezone.utc)
_ARR = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
_ROUTE_ID = 1


def _make_flight(**kwargs) -> Flight:
    defaults = dict(
        provider="aviasales",
        airline="SU",
        flight_number="SU500",
        origin="SVO",
        destination="LED",
        departure_time=_DEP,
        arrival_time=_ARR,
        duration=180,
        stops=0,
        price=Decimal("7000.00"),
        currency="RUB",
        scraped_at=_NOW,
        route_id=_ROUTE_ID,
    )
    defaults.update(kwargs)
    return Flight(**defaults)


def _history_rows(cur, flight_number: str = "SU500") -> list[dict]:
    cur.execute(
        """
        SELECT provider, flight_number, price, is_current, valid_to
        FROM flights_history
        WHERE provider = 'aviasales' AND flight_number = %s AND route_id = %s
        ORDER BY id
        """,
        (flight_number, _ROUTE_ID),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@pytest.fixture(autouse=True)
def cleanup():
    yield
    conn = _get_conn()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM flights_history WHERE provider = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
            cur.execute(
                "DELETE FROM flights_current WHERE provider = 'aviasales' AND route_id = %s",
                (_ROUTE_ID,),
            )
    conn.close()


class TestInsertHistory:
    def test_insert_creates_one_history_row(self):
        flight = _make_flight()
        events = compare_snapshots([], [flight])
        append_history(events, [flight])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        assert len(rows) == 1
        assert rows[0]["is_current"] is True
        assert rows[0]["valid_to"] is None

    def test_insert_stores_correct_price(self):
        flight = _make_flight(price=Decimal("6500.00"))
        append_history(compare_snapshots([], [flight]), [flight])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        assert float(rows[0]["price"]) == 6500.0


class TestUpdateHistory:
    def test_update_produces_two_rows(self):
        prev = _make_flight(price=Decimal("7000.00"))
        curr = _make_flight(price=Decimal("6000.00"))

        append_history(compare_snapshots([], [prev]), [prev])
        append_history(compare_snapshots([prev], [curr]), [curr])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        assert len(rows) == 2

    def test_update_old_row_is_closed(self):
        prev = _make_flight(price=Decimal("7000.00"))
        curr = _make_flight(price=Decimal("6000.00"))

        append_history(compare_snapshots([], [prev]), [prev])
        append_history(compare_snapshots([prev], [curr]), [curr])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        old_row = rows[0]
        assert old_row["is_current"] is False
        assert old_row["valid_to"] is not None

    def test_update_new_row_is_current(self):
        prev = _make_flight(price=Decimal("7000.00"))
        curr = _make_flight(price=Decimal("6000.00"))

        append_history(compare_snapshots([], [prev]), [prev])
        append_history(compare_snapshots([prev], [curr]), [curr])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        new_row = rows[1]
        assert new_row["is_current"] is True
        assert new_row["valid_to"] is None
        assert float(new_row["price"]) == 6000.0


class TestDeleteHistory:
    def test_delete_closes_row(self):
        flight = _make_flight()
        append_history(compare_snapshots([], [flight]), [flight])
        append_history(compare_snapshots([flight], []), [])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        assert len(rows) == 1
        assert rows[0]["is_current"] is False
        assert rows[0]["valid_to"] is not None

    def test_history_never_deletes_rows(self):
        """После INSERT + UPDATE + DELETE в истории должно быть 2 строки, обе закрыты."""
        f1 = _make_flight(price=Decimal("7000"))
        f2 = _make_flight(price=Decimal("6000"))

        append_history(compare_snapshots([], [f1]), [f1])
        append_history(compare_snapshots([f1], [f2]), [f2])
        append_history(compare_snapshots([f2], []), [])

        conn = _get_conn()
        with conn.cursor() as cur:
            rows = _history_rows(cur)
        conn.close()

        assert len(rows) == 2
        assert all(r["is_current"] is False for r in rows)


class TestHistoryMirrorsCurrentForIsCurrentRows:
    def test_is_current_history_matches_current_table(self):
        """
        Шаг 4 из test_steps: flights_history WHERE is_current=true
        должен совпадать с flights_current по ключевым полям рейса.
        """
        f1 = _make_flight(flight_number="SU500", price=Decimal("7000"))
        f2 = _make_flight(flight_number="SU600", price=Decimal("5000"))
        f3 = _make_flight(flight_number="SU700", price=Decimal("4000"))

        # INSERT все три
        events_insert = compare_snapshots([], [f1, f2, f3])
        apply_cdc_to_current(events_insert, [f1, f2, f3])
        append_history(events_insert, [f1, f2, f3])

        # UPDATE f1, DELETE f2 — f3 без изменений
        f1_updated = _make_flight(flight_number="SU500", price=Decimal("6000"))
        events_next = compare_snapshots([f1, f2, f3], [f1_updated, f3])
        apply_cdc_to_current(events_next, [f1_updated, f3])
        append_history(events_next, [f1_updated, f3])

        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT flight_number, price
                FROM flights_history
                WHERE provider = 'aviasales' AND route_id = %s AND is_current = true
                ORDER BY flight_number
                """,
                (_ROUTE_ID,),
            )
            history_current = {row[0]: float(row[1]) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT flight_number, price
                FROM flights_current
                WHERE provider = 'aviasales' AND route_id = %s
                ORDER BY flight_number
                """,
                (_ROUTE_ID,),
            )
            current = {row[0]: float(row[1]) for row in cur.fetchall()}
        conn.close()

        assert history_current == current
