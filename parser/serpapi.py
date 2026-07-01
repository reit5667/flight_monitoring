import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from models.flight import Flight

logger = logging.getLogger(__name__)


def parse_serpapi_flights(raw_flights: list[dict], route_id: int) -> list[Flight]:
    """Convert SerpApi Google Flights response items to list[Flight]."""
    scraped_at = datetime.now(tz=timezone.utc)
    result: list[Flight] = []
    for item in raw_flights:
        try:
            flights = _parse_item(item, route_id, scraped_at)
            result.extend(flights)
        except Exception:
            logger.warning("serpapi: skipping item due to parse error: %s", item, exc_info=True)
    logger.info("serpapi parsed %d flights from %d items", len(result), len(raw_flights))
    return result


def parse_serpapi_offers(raw_flights: list[dict]) -> list[dict]:
    """Convert SerpApi response to Travelpayouts-compatible dicts for bot.py."""
    result = []
    for item in raw_flights:
        try:
            parsed = _parse_item_to_dict(item)
            if parsed:
                result.append(parsed)
        except Exception:
            logger.warning("serpapi: skipping item: %s", item, exc_info=True)
    logger.info("serpapi parsed %d/%d offers", len(result), len(raw_flights))
    return result


def _parse_item(item: dict, route_id: int, scraped_at: datetime) -> list[Flight]:
    """One SerpApi item may contain multiple flight legs — we parse the whole itinerary as one Flight."""
    flights_data = item.get("flights", [])
    if not flights_data:
        return []

    price = item.get("price")
    if not price:
        return []

    first_leg = flights_data[0]
    last_leg = flights_data[-1]

    dep_str = first_leg.get("departure_airport", {}).get("time", "")
    arr_str = last_leg.get("arrival_airport", {}).get("time", "")
    if not dep_str or not arr_str:
        return []

    dep_dt = _parse_dt(dep_str)
    arr_dt = _parse_dt(arr_str)
    if dep_dt is None or arr_dt is None:
        return []

    origin = first_leg.get("departure_airport", {}).get("id", "")
    destination = last_leg.get("arrival_airport", {}).get("id", "")
    if not origin or not destination or len(origin) != 3 or len(destination) != 3:
        return []

    duration = item.get("total_duration") or int((arr_dt - dep_dt).total_seconds() / 60)
    airline = first_leg.get("airline", "") or first_leg.get("airline_logo", "").split("/")[-1].split(".")[0]
    flight_number = first_leg.get("flight_number", "")
    stops = len(flights_data) - 1

    return [Flight(
        provider="serpapi",
        airline=airline or "?",
        flight_number=flight_number or None,
        origin=origin.upper(),
        destination=destination.upper(),
        departure_time=dep_dt,
        arrival_time=arr_dt,
        duration=duration,
        stops=stops,
        price=Decimal(str(price)),
        currency="USD",
        scraped_at=scraped_at,
        route_id=route_id,
    )]


def _parse_item_to_dict(item: dict) -> dict | None:
    """Bot-compatible dict format matching Travelpayouts structure."""
    flights_data = item.get("flights", [])
    if not flights_data:
        return None

    price = item.get("price")
    if not price:
        return None

    first_leg = flights_data[0]
    dep_str = first_leg.get("departure_airport", {}).get("time", "")
    if not dep_str:
        return None

    dep_dt = _parse_dt(dep_str)
    if dep_dt is None:
        return None

    duration = item.get("total_duration", 0)
    airline = first_leg.get("airline", "?")
    stops = len(flights_data) - 1

    return {
        "departure_at": dep_dt.isoformat(),
        "price": float(price),
        "airline": airline,
        "transfers": stops,
        "duration_to": duration,
        "link": None,
        "source": "serpapi",
    }


def _parse_dt(s: str) -> datetime | None:
    """Parse SerpApi datetime string like '2026-08-03 06:00' to UTC-aware datetime."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.warning("serpapi: cannot parse datetime %r", s)
    return None
