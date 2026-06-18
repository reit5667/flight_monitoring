import logging
from datetime import datetime, timezone
from decimal import Decimal

from models.flight import Flight

logger = logging.getLogger(__name__)


def parse_trip(raw: dict, route_id: int) -> list[Flight]:
    """Parse Trip.com XHR response into Flight objects.

    Expected raw format (captured via Playwright XHR interception):
        {
          "data": {
            "flightItineraryList": [
              {
                "priceList": [{"adultPrice": 150.0, "currency": "USD"}],
                "flightSegments": [
                  {
                    "departureAirportInfo": {"airportCode": "KUL"},
                    "arrivalAirportInfo":   {"airportCode": "CMB"},
                    "departureDateTime":    "2026-08-03 06:30:00",
                    "arrivalDateTime":      "2026-08-03 07:30:00",
                    "airlineInfo":          {"airlineCode": "AK", "airlineName": "AirAsia"},
                    "flightNumber":         "1234",
                    "duration":             60,
                    "stopCount":            0
                  }
                ]
              }
            ]
          }
        }
    """
    try:
        itineraries = raw["data"]["flightItineraryList"]
    except (KeyError, TypeError):
        logger.warning("trip: unexpected response structure, missing data.flightItineraryList")
        return []

    if not itineraries:
        logger.warning("trip: flightItineraryList is empty")
        return []

    scraped_at = datetime.now(tz=timezone.utc)
    flights: list[Flight] = []

    for itinerary in itineraries:
        try:
            flight = _parse_itinerary(itinerary, route_id, scraped_at)
            flights.append(flight)
        except Exception:
            logger.warning("trip: skipping itinerary due to parse error: %s",
                           itinerary, exc_info=True)

    logger.info("trip: parsed %d/%d flights", len(flights), len(itineraries))
    return flights


def _parse_itinerary(itinerary: dict, route_id: int, scraped_at: datetime) -> Flight:
    # Take the first (cheapest) price
    price_entry = itinerary["priceList"][0]
    price = Decimal(str(price_entry["adultPrice"]))
    currency = price_entry.get("currency", "USD").upper()

    # Take the first segment (direct or first leg of connection)
    seg = itinerary["flightSegments"][0]

    origin = seg["departureAirportInfo"]["airportCode"].upper()
    destination = seg["arrivalAirportInfo"]["airportCode"].upper()
    departure_time = _parse_dt(seg["departureDateTime"])
    arrival_time = _parse_dt(seg["arrivalDateTime"])
    duration = int(seg.get("duration", 0))
    stops = int(seg.get("stopCount", 0))

    airline_info = seg.get("airlineInfo", {})
    airline = airline_info.get("airlineName") or airline_info.get("airlineCode") or ""
    if not airline:
        raise ValueError("missing airline info")

    flight_number = seg.get("flightNumber") or None

    return Flight(
        provider="trip",
        airline=airline,
        flight_number=flight_number,
        origin=origin,
        destination=destination,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration=duration,
        stops=stops,
        price=price,
        currency=currency,
        scraped_at=scraped_at,
        route_id=route_id,
    )


def _parse_dt(value: str) -> datetime:
    """Parse Trip.com datetime string (space-separated, no tz) as UTC."""
    # Trip.com returns local time without timezone — treat as UTC for consistency
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)
