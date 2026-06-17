from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from models.cdc import CdcEvent
from models.flight import Flight
from models.route import Route, SourceMapping
from models.storage import RawSnapshot

NOW = datetime.now(tz=timezone.utc)

VALID_FLIGHT = dict(
    provider="aviasales",
    airline="AirAsia",
    flight_number="FD-123",
    origin="BKK",
    destination="HAN",
    departure_time=NOW,
    arrival_time=NOW,
    duration=80,
    stops=0,
    price=Decimal("105.00"),
    currency="USD",
    scraped_at=NOW,
    route_id=1,
)


def test_flight_valid():
    f = Flight(**VALID_FLIGHT)
    assert f.price == Decimal("105.00")
    assert f.origin == "BKK"


def test_flight_negative_price():
    with pytest.raises(ValidationError, match="positive"):
        Flight(**{**VALID_FLIGHT, "price": Decimal("-10")})


def test_flight_zero_price():
    with pytest.raises(ValidationError, match="positive"):
        Flight(**{**VALID_FLIGHT, "price": Decimal("0")})


def test_flight_invalid_iata_lowercase():
    with pytest.raises(ValidationError, match="IATA"):
        Flight(**{**VALID_FLIGHT, "origin": "hanoi"})


def test_flight_invalid_iata_digits():
    with pytest.raises(ValidationError, match="IATA"):
        Flight(**{**VALID_FLIGHT, "destination": "BK1"})


def test_flight_invalid_iata_wrong_length():
    with pytest.raises(ValidationError, match="IATA"):
        Flight(**{**VALID_FLIGHT, "origin": "BKKK"})


def test_flight_naive_datetime_rejected():
    naive = datetime(2026, 6, 18, 10, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        Flight(**{**VALID_FLIGHT, "departure_time": naive})


def test_flight_no_flight_number():
    f = Flight(**{**VALID_FLIGHT, "flight_number": None})
    assert f.flight_number is None


def test_route_valid():
    r = Route(
        route_id=1,
        origin="BKK",
        destination="HAN",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )
    assert r.currency == "USD"
    assert r.enabled is True


def test_source_mapping_valid():
    sm = SourceMapping(
        route_id=1,
        source="aviasales",
        source_origin="BKK",
        source_destination="HAN",
    )
    assert sm.enabled is True


def test_models_have_from_attributes():
    assert Flight.model_config.get("from_attributes") is True
    assert Route.model_config.get("from_attributes") is True
    assert SourceMapping.model_config.get("from_attributes") is True


# --- CdcEvent ---

VALID_CDC = dict(
    event_type="UPDATE",
    route_id=1,
    source="aviasales",
    flight_key="aviasales:FD-123:2026-07-10T10:00:00+00:00",
    old_price=120.0,
    new_price=105.0,
    changed_fields={"price": {"old": 120.0, "new": 105.0}},
    occurred_at=NOW,
)


def test_cdc_event_valid():
    e = CdcEvent(**VALID_CDC)
    assert e.event_type == "UPDATE"
    assert e.changed_fields["price"]["new"] == 105.0


def test_cdc_event_invalid_type():
    with pytest.raises(ValidationError):
        CdcEvent(**{**VALID_CDC, "event_type": "INVALID"})


def test_cdc_event_insert_no_prices():
    e = CdcEvent(**{**VALID_CDC, "event_type": "INSERT", "old_price": None, "new_price": None})
    assert e.old_price is None


def test_cdc_event_naive_datetime():
    naive = datetime(2026, 6, 18, 10, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        CdcEvent(**{**VALID_CDC, "occurred_at": naive})


def test_cdc_event_from_attributes():
    assert CdcEvent.model_config.get("from_attributes") is True


# --- RawSnapshot ---

def test_raw_snapshot_valid():
    s = RawSnapshot(
        source="aviasales",
        route_id=1,
        file_path="/raw/2026-06-18/aviasales_1.json",
        records_count=42,
        scraped_at=NOW,
    )
    assert s.records_count == 42


def test_raw_snapshot_naive_datetime():
    naive = datetime(2026, 6, 18, 10, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        RawSnapshot(
            source="aviasales",
            route_id=1,
            file_path="/raw/test.json",
            records_count=1,
            scraped_at=naive,
        )


def test_raw_snapshot_from_attributes():
    assert RawSnapshot.model_config.get("from_attributes") is True
