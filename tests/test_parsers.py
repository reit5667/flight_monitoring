"""Tests for parser/aviasales.py and parser/trip.py."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from parser.aviasales import parse_aviasales
from parser.trip import parse_trip

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


# ---------------------------------------------------------------------------
# Trip.com parser tests
# ---------------------------------------------------------------------------

TRIP_SAMPLE_RAW = {
    "data": {
        "flightItineraryList": [
            {
                "priceList": [{"adultPrice": 89.0, "currency": "USD"}],
                "flightSegments": [
                    {
                        "departureAirportInfo": {"airportCode": "KUL", "cityName": "Kuala Lumpur"},
                        "arrivalAirportInfo": {"airportCode": "CMB", "cityName": "Colombo"},
                        "departureDateTime": "2026-08-03 06:30:00",
                        "arrivalDateTime": "2026-08-03 08:00:00",
                        "airlineInfo": {"airlineCode": "AK", "airlineName": "AirAsia"},
                        "flightNumber": "1234",
                        "duration": 90,
                        "stopCount": 0,
                    }
                ],
            },
            {
                "priceList": [{"adultPrice": 120.0, "currency": "USD"}],
                "flightSegments": [
                    {
                        "departureAirportInfo": {"airportCode": "KUL", "cityName": "Kuala Lumpur"},
                        "arrivalAirportInfo": {"airportCode": "CMB", "cityName": "Colombo"},
                        "departureDateTime": "2026-08-03 14:00:00",
                        "arrivalDateTime": "2026-08-03 16:10:00",
                        "airlineInfo": {"airlineCode": "UL", "airlineName": "SriLankan Airlines"},
                        "flightNumber": None,
                        "duration": 130,
                        "stopCount": 1,
                    }
                ],
            },
        ]
    }
}


def test_trip_returns_flights():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert len(flights) == 2


def test_trip_provider_is_trip():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert all(f.provider == "trip" for f in flights)


def test_trip_price_is_decimal():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert isinstance(flights[0].price, Decimal)
    assert flights[0].price == Decimal("89.0")


def test_trip_currency_uppercase():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert flights[0].currency == "USD"


def test_trip_iata_codes_uppercase():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    for f in flights:
        assert f.origin == f.origin.upper()
        assert f.destination == f.destination.upper()


def test_trip_datetime_is_timezone_aware():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    for f in flights:
        assert f.departure_time.tzinfo is not None
        assert f.arrival_time.tzinfo is not None
        assert f.scraped_at.tzinfo is not None


def test_trip_stops_and_duration():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert flights[0].stops == 0
    assert flights[0].duration == 90
    assert flights[1].stops == 1
    assert flights[1].duration == 130


def test_trip_flight_number_optional():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert flights[0].flight_number == "1234"
    assert flights[1].flight_number is None


def test_trip_route_id_set():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=42)
    assert all(f.route_id == 42 for f in flights)


def test_trip_missing_data_returns_empty():
    assert parse_trip({}, route_id=2) == []
    assert parse_trip({"data": {}}, route_id=2) == []
    assert parse_trip({"data": {"flightItineraryList": []}}, route_id=2) == []


def test_trip_skips_bad_itinerary_keeps_good():
    bad = {"priceList": [], "flightSegments": []}  # empty priceList → IndexError
    raw = {
        "data": {
            "flightItineraryList": [bad, TRIP_SAMPLE_RAW["data"]["flightItineraryList"][0]]
        }
    }
    flights = parse_trip(raw, route_id=2)
    assert len(flights) == 1


def test_trip_airline_name_preferred_over_code():
    flights = parse_trip(TRIP_SAMPLE_RAW, route_id=2)
    assert flights[0].airline == "AirAsia"
    assert flights[1].airline == "SriLankan Airlines"


# ---------------------------------------------------------------------------
# Agoda parser tests
# ---------------------------------------------------------------------------

from parser.agoda import parse_agoda

AGODA_SAMPLE_RAW = {
    "data": {
        "flights": [
            {
                "fareAmount": 310.0,
                "currency": "USD",
                "legs": [
                    {
                        "departureAirport": "CMB",
                        "arrivalAirport": "MOW",
                        "departureTime": "2026-08-03T08:00:00",
                        "arrivalTime": "2026-08-03T15:30:00",
                        "carrier": {"code": "SU", "name": "Aeroflot"},
                        "flightNumber": "SU290",
                        "durationMinutes": 450,
                        "stopCount": 0,
                    }
                ],
            },
            {
                "fareAmount": 210.0,
                "currency": "USD",
                "legs": [
                    {
                        "departureAirport": "CMB",
                        "arrivalAirport": "MOW",
                        "departureTime": "2026-08-03T21:00:00",
                        "arrivalTime": "2026-08-04T10:00:00",
                        "carrier": {"code": "EK", "name": "Emirates"},
                        "flightNumber": None,
                        "durationMinutes": 780,
                        "stopCount": 1,
                    }
                ],
            },
        ]
    }
}


def test_agoda_returns_flights():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert len(flights) == 2


def test_agoda_provider_is_agoda():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert all(f.provider == "agoda" for f in flights)


def test_agoda_price_is_decimal():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert isinstance(flights[0].price, Decimal)
    assert flights[0].price == Decimal("310.0")
    assert flights[1].price == Decimal("210.0")


def test_agoda_currency_uppercase():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert all(f.currency == "USD" for f in flights)


def test_agoda_iata_codes_uppercase():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    for f in flights:
        assert f.origin == f.origin.upper()
        assert f.destination == f.destination.upper()


def test_agoda_datetime_is_timezone_aware():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    for f in flights:
        assert f.departure_time.tzinfo is not None
        assert f.arrival_time.tzinfo is not None
        assert f.scraped_at.tzinfo is not None


def test_agoda_stops_and_duration():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert flights[0].stops == 0
    assert flights[0].duration == 450
    assert flights[1].stops == 1
    assert flights[1].duration == 780


def test_agoda_flight_number_optional():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert flights[0].flight_number == "SU290"
    assert flights[1].flight_number is None


def test_agoda_route_id_set():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=99)
    assert all(f.route_id == 99 for f in flights)


def test_agoda_missing_data_returns_empty():
    assert parse_agoda({}, route_id=3) == []
    assert parse_agoda({"data": {}}, route_id=3) == []
    assert parse_agoda({"data": {"flights": []}}, route_id=3) == []


def test_agoda_skips_bad_item_keeps_good():
    bad = {"fareAmount": 100.0, "currency": "USD", "legs": []}  # empty legs → IndexError
    raw = {"data": {"flights": [bad, AGODA_SAMPLE_RAW["data"]["flights"][0]]}}
    flights = parse_agoda(raw, route_id=3)
    assert len(flights) == 1


def test_agoda_carrier_name_preferred_over_code():
    flights = parse_agoda(AGODA_SAMPLE_RAW, route_id=3)
    assert flights[0].airline == "Aeroflot"
    assert flights[1].airline == "Emirates"
