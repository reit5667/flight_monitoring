from datetime import datetime, timezone
from decimal import Decimal

import pytest

from cdc.engine import compare_snapshots
from models.cdc import CdcEvent
from models.flight import Flight

_NOW = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
_DEP = datetime(2026, 6, 20, 8, 0, 0, tzinfo=timezone.utc)
_ARR = datetime(2026, 6, 20, 11, 30, 0, tzinfo=timezone.utc)


def _make_flight(**kwargs) -> Flight:
    defaults = dict(
        provider="aviasales",
        airline="SU",
        flight_number="SU100",
        origin="SVO",
        destination="LED",
        departure_time=_DEP,
        arrival_time=_ARR,
        duration=90,
        stops=0,
        price=Decimal("5000.00"),
        currency="RUB",
        scraped_at=_NOW,
        route_id=1,
    )
    defaults.update(kwargs)
    return Flight(**defaults)


@pytest.fixture
def base_flight() -> Flight:
    return _make_flight()


class TestCompareSnapshotsBasicCases:
    def test_empty_both(self):
        assert compare_snapshots([], []) == []

    def test_insert_single(self):
        curr = _make_flight()
        events = compare_snapshots([], [curr])
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "INSERT"
        assert e.new_price == 5000.0
        assert e.old_price is None
        assert e.changed_fields == {}

    def test_delete_single(self):
        prev = _make_flight()
        events = compare_snapshots([prev], [])
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "DELETE"
        assert e.old_price == 5000.0
        assert e.new_price is None
        assert e.changed_fields == {}

    def test_no_change(self):
        flight = _make_flight()
        events = compare_snapshots([flight], [flight])
        assert events == []

    def test_update_price(self):
        prev = _make_flight(price=Decimal("5000.00"))
        curr = _make_flight(price=Decimal("4500.00"))
        events = compare_snapshots([prev], [curr])
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "UPDATE"
        assert e.old_price == 5000.0
        assert e.new_price == 4500.0
        assert "price" in e.changed_fields
        assert e.changed_fields["price"]["old"] == Decimal("5000.00")
        assert e.changed_fields["price"]["new"] == Decimal("4500.00")


class TestCompareSnapshotsThreeEvents:
    """Main scenario from test_steps: 1 INSERT, 1 UPDATE, 1 DELETE."""

    def setup_method(self):
        self.unchanged = _make_flight(flight_number="SU100", price=Decimal("5000"))
        self.to_update = _make_flight(flight_number="SU200", price=Decimal("6000"))
        self.to_delete = _make_flight(flight_number="SU300", price=Decimal("7000"))
        self.new_flight = _make_flight(flight_number="SU400", price=Decimal("3000"))
        self.updated = _make_flight(flight_number="SU200", price=Decimal("5500"))

        self.previous = [self.unchanged, self.to_update, self.to_delete]
        self.current = [self.unchanged, self.updated, self.new_flight]

    def test_exactly_three_events(self):
        events = compare_snapshots(self.previous, self.current)
        assert len(events) == 3

    def test_event_types(self):
        events = compare_snapshots(self.previous, self.current)
        types = {e.event_type for e in events}
        assert types == {"INSERT", "UPDATE", "DELETE"}

    def test_insert_flight(self):
        events = compare_snapshots(self.previous, self.current)
        insert = next(e for e in events if e.event_type == "INSERT")
        assert "SU400" in insert.flight_key
        assert insert.new_price == 3000.0

    def test_update_changed_fields(self):
        events = compare_snapshots(self.previous, self.current)
        update = next(e for e in events if e.event_type == "UPDATE")
        assert "price" in update.changed_fields
        assert update.changed_fields["price"]["old"] == Decimal("6000")
        assert update.changed_fields["price"]["new"] == Decimal("5500")

    def test_delete_flight(self):
        events = compare_snapshots(self.previous, self.current)
        delete = next(e for e in events if e.event_type == "DELETE")
        assert "SU300" in delete.flight_key
        assert delete.old_price == 7000.0


class TestCompareSnapshotsFieldDetails:
    def test_route_id_and_source_set(self):
        curr = _make_flight(route_id=42, provider="trip")
        events = compare_snapshots([], [curr])
        e = events[0]
        assert e.route_id == 42
        assert e.source == "trip"

    def test_update_multiple_fields(self):
        prev = _make_flight(price=Decimal("5000"), stops=0, duration=90)
        curr = _make_flight(price=Decimal("4000"), stops=1, duration=120)
        events = compare_snapshots([prev], [curr])
        assert len(events) == 1
        cf = events[0].changed_fields
        assert set(cf.keys()) == {"price", "stops", "duration"}

    def test_scraped_at_change_not_detected(self):
        """scraped_at обновляется каждый раз — не должно вызывать UPDATE."""
        prev = _make_flight(scraped_at=datetime(2026, 6, 18, 10, 0, tzinfo=timezone.utc))
        curr = _make_flight(scraped_at=datetime(2026, 6, 18, 11, 0, tzinfo=timezone.utc))
        events = compare_snapshots([prev], [curr])
        assert events == []

    def test_key_includes_route_id(self):
        """Один и тот же рейс на разных маршрутах — разные ключи, оба INSERT."""
        f1 = _make_flight(flight_number="SU100", route_id=1)
        f2 = _make_flight(flight_number="SU100", route_id=2)
        events = compare_snapshots([], [f1, f2])
        assert len(events) == 2
        assert all(e.event_type == "INSERT" for e in events)

    def test_pure_function_no_side_effects(self):
        """Повторный вызов с теми же аргументами возвращает идентичный результат."""
        prev = [_make_flight(flight_number="SU100")]
        curr = [_make_flight(flight_number="SU200")]
        events1 = compare_snapshots(prev, curr)
        events2 = compare_snapshots(prev, curr)
        assert len(events1) == len(events2) == 2
        assert {e.event_type for e in events1} == {e.event_type for e in events2}

    def test_occurred_at_is_timezone_aware(self):
        curr = _make_flight()
        events = compare_snapshots([], [curr])
        assert events[0].occurred_at.tzinfo is not None

    def test_update_airline(self):
        prev = _make_flight(airline="SU")
        curr = _make_flight(airline="S7")
        events = compare_snapshots([prev], [curr])
        assert len(events) == 1
        assert events[0].changed_fields["airline"]["old"] == "SU"
        assert events[0].changed_fields["airline"]["new"] == "S7"
