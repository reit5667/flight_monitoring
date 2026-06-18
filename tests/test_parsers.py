"""Tests for parser/aviasales.py."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from parser.aviasales import parse_aviasales

# Realistic sample matching Travelpayouts v3 format
SAMPLE_RAW = {
    "success": True,
    "data": [
        {
            "origin": "HAN",
            "destination": "KUL",
            "origin_airport": "HAN",
            "destination_airport": "KUL",
            "price": 125,
            "airline": "AK",
            "flight_number": "D7535",
            "departure_at": "2026-07-18T10:00:00+07:00",
            "return_at": None,
            "transfers": 0,
            "duration_to": 200,
            "duration": 200,
            "link": "/search/HAN1807KUL1",
            "found_at": "2026-06-18T01:00:00Z",
        },
        {
            "origin": "HAN",
            "destination": "KUL",
            "origin_airport": "HAN",
            "destination_airport": "KUL",
            "price": 99,
            "airline": "FD",
            "flight_number": None,
            "departure_at": "2026-07-20T08:30:00+07:00",
            "return_at": None,
            "transfers": 1,
            "duration_to": 300,
            "duration": 300,
            "link": "/search/HAN2007KUL1",
            "found_at": "2026-06-18T01:00:00Z",
        },
    ],
    "currency": "usd",
}


def test_parse_aviasales_returns_flights():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    assert len(flights) == 2


def test_parse_aviasales_price_is_decimal():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    assert isinstance(flights[0].price, Decimal)
    assert flights[0].price == Decimal("125")
    assert flights[1].price == Decimal("99")


def test_parse_aviasales_departure_is_timezone_aware():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    for f in flights:
        assert f.departure_time.tzinfo is not None
        assert f.arrival_time.tzinfo is not None
        assert f.scraped_at.tzinfo is not None


def test_parse_aviasales_arrival_time_computed():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    f = flights[0]
    expected_arrival = f.departure_time.timestamp() + 200 * 60
    assert abs(f.arrival_time.timestamp() - expected_arrival) < 1


def test_parse_aviasales_iata_codes_uppercase():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    for f in flights:
        assert f.origin == f.origin.upper()
        assert f.destination == f.destination.upper()


def test_parse_aviasales_optional_flight_number():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    assert flights[0].flight_number == "D7535"
    assert flights[1].flight_number is None  # None is valid


def test_parse_aviasales_stops():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    assert flights[0].stops == 0
    assert flights[1].stops == 1


def test_parse_aviasales_currency_uppercase():
    flights = parse_aviasales(SAMPLE_RAW, route_id=1)
    assert flights[0].currency == "USD"


def test_parse_aviasales_route_id_set():
    flights = parse_aviasales(SAMPLE_RAW, route_id=42)
    for f in flights:
        assert f.route_id == 42


def test_parse_aviasales_success_false_returns_empty():
    raw = {**SAMPLE_RAW, "success": False}
    assert parse_aviasales(raw, route_id=1) == []


def test_parse_aviasales_empty_data_returns_empty():
    raw = {**SAMPLE_RAW, "data": []}
    assert parse_aviasales(raw, route_id=1) == []


def test_parse_aviasales_skips_bad_items_logs_warning():
    bad_item = {"price": -1, "airline": "", "departure_at": "2026-07-18T10:00:00+07:00"}
    raw = {**SAMPLE_RAW, "data": [bad_item, SAMPLE_RAW["data"][0]]}
    flights = parse_aviasales(raw, route_id=1)
    # Bad item skipped, good item parsed
    assert len(flights) == 1


def test_parse_aviasales_missing_price_skips_item():
    bad_item = {k: v for k, v in SAMPLE_RAW["data"][0].items() if k != "price"}
    raw = {**SAMPLE_RAW, "data": [bad_item]}
    flights = parse_aviasales(raw, route_id=1)
    assert flights == []
