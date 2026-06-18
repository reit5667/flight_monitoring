import logging
from datetime import datetime, timezone
from decimal import Decimal

from models.flight import Flight

logger = logging.getLogger(__name__)


def parse_agoda(raw: dict, route_id: int) -> list[Flight]:
    """Parse Agoda XHR response into Flight objects.

    Expected raw format (captured via Playwright XHR interception):
        {
          "data": {
            "flights": [
              {
                "fareAmount": 250.0,
                "currency": "USD",
                "legs": [
                  {
                    "departureAirport": "CMB",
                    "arrivalAirport":   "MOW",
                    "departureTime":    "2026-08-03T08:00:00",
                    "arrivalTime":      "2026-08-03T15:30:00",
                    "carrier":          {"code": "SU", "name": "Aeroflot"},
                    "flightNumber":     "SU290",
                    "durationMinutes":  450,
                    "stopCount":        0
                  }
                ]
              }
            ]
          }
        }
    """
    try:
        flight_list = raw["data"]["flights"]
    except (KeyError, TypeError):
        logger.warning("agoda: unexpected response structure, missing data.flights")
        return []

    if not flight_list:
        logger.warning("agoda: flights list is empty")
        return []

    scraped_at = datetime.now(tz=timezone.utc)
    flights: list[Flight] = []

    for item in flight_list:
        try:
            flights.append(_parse_flight(item, route_id, scraped_at))
        except Exception:
            logger.warning("agoda: skipping flight due to parse error: %s",
                           item, exc_info=True)

    logger.info("agoda: parsed %d/%d flights", len(flights), len(flight_list))
    return flights


def _parse_flight(item: dict, route_id: int, scraped_at: datetime) -> Flight:
    price = Decimal(str(item["fareAmount"]))
    currency = item.get("currency", "USD").upper()

    leg = item["legs"][0]

    origin = leg["departureAirport"].upper()
    destination = leg["arrivalAirport"].upper()
    departure_time = _parse_dt(leg["departureTime"])
    arrival_time = _parse_dt(leg["arrivalTime"])
    duration = int(leg.get("durationMinutes", 0))
    stops = int(leg.get("stopCount", 0))

    carrier = leg.get("carrier", {})
    airline = carrier.get("name") or carrier.get("code") or ""
    if not airline:
        raise ValueError("missing carrier info")

    flight_number = leg.get("flightNumber") or None

    return Flight(
        provider="agoda",
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
    """Parse Agoda ISO datetime string (no tz) as UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
