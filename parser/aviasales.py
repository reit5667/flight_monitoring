import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from models.flight import Flight

logger = logging.getLogger(__name__)


def parse_aviasales(raw: dict, route_id: int) -> list[Flight]:
    """Parse Travelpayouts v3 API response into Flight objects.

    Expected raw format:
        {"success": true, "data": [...], "currency": "usd"}
    """
    if not raw.get("success"):
        logger.warning("aviasales response success=false, skipping")
        return []

    items = raw.get("data")
    if not items:
        logger.warning("aviasales response has no data items")
        return []

    currency = raw.get("currency", "usd").upper()
    scraped_at = datetime.now(tz=timezone.utc)
    flights: list[Flight] = []

    for item in items:
        try:
            flight = _parse_item(item, route_id, currency, scraped_at)
            flights.append(flight)
        except Exception:
            logger.warning("aviasales: skipping item due to parse error: %s", item, exc_info=True)

    logger.info("aviasales parsed %d/%d flights", len(flights), len(items))
    return flights


def _parse_item(
    item: dict,
    route_id: int,
    currency: str,
    scraped_at: datetime,
) -> Flight:
    departure_time = _parse_dt(item["departure_at"])
    duration_minutes: int = item.get("duration_to") or item.get("duration") or 0
    arrival_time = departure_time + timedelta(minutes=duration_minutes)

    # Travelpayouts uses IATA airline codes — store as-is; full name not available from this endpoint
    airline = item.get("airline") or ""
    if not airline:
        raise ValueError("missing airline code")

    origin = (item.get("origin_airport") or item.get("origin") or "").upper()
    destination = (item.get("destination_airport") or item.get("destination") or "").upper()

    return Flight(
        provider="aviasales",
        airline=airline,
        flight_number=item.get("flight_number") or None,
        origin=origin,
        destination=destination,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration=duration_minutes,
        stops=item.get("transfers", 0),
        price=Decimal(str(item["price"])),
        currency=currency,
        scraped_at=scraped_at,
        route_id=route_id,
    )


def _parse_dt(value: str) -> datetime:
    """Parse ISO-8601 string from Travelpayouts into timezone-aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
