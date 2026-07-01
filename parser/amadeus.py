import logging
from datetime import datetime, timezone
from decimal import Decimal

from models.flight import Flight

logger = logging.getLogger(__name__)


def parse_amadeus_offers(offers: list[dict]) -> list[dict]:
    """Convert Amadeus flight-offers API response to Travelpayouts-compatible dicts.

    Output dict keys used by bot.py:
        departure_at, price, airline, transfers, duration_to, link
    """
    result = []
    for offer in offers:
        try:
            item = _parse_offer(offer)
            if item:
                result.append(item)
        except Exception:
            logger.warning("amadeus: skipping offer due to parse error: %s", offer, exc_info=True)
    logger.info("amadeus parsed %d/%d offers", len(result), len(offers))
    return result


def _parse_offer(offer: dict) -> dict | None:
    price_str = offer.get("price", {}).get("grandTotal") or offer.get("price", {}).get("total")
    if not price_str:
        return None
    price = float(price_str)

    itineraries = offer.get("itineraries", [])
    if not itineraries:
        return None
    # Take first itinerary (outbound leg)
    itinerary = itineraries[0]
    segments = itinerary.get("segments", [])
    if not segments:
        return None

    first_seg = segments[0]
    departure_at = first_seg.get("departure", {}).get("at", "")
    if not departure_at:
        return None

    # Normalize to UTC-aware ISO string matching Travelpayouts format
    try:
        dt = datetime.fromisoformat(departure_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        departure_at_iso = dt.isoformat()
    except ValueError:
        departure_at_iso = departure_at

    # Duration from ISO 8601 duration string e.g. "PT14H30M"
    duration_str = itinerary.get("duration", "")
    duration_minutes = _parse_duration(duration_str)

    # Primary airline from first segment carrier
    airline = first_seg.get("carrierCode") or first_seg.get("operating", {}).get("carrierCode", "?")

    transfers = len(segments) - 1

    return {
        "departure_at": departure_at_iso,
        "price": price,
        "airline": airline,
        "transfers": transfers,
        "duration_to": duration_minutes,
        "link": None,
        "source": "amadeus",
    }


def parse_amadeus_flights(offers: list[dict], route_id: int) -> list[Flight]:
    """Convert Amadeus flight-offers API response to list[Flight] for BaseConnector pipeline."""
    scraped_at = datetime.now(tz=timezone.utc)
    result: list[Flight] = []
    for offer in offers:
        try:
            flight = _parse_offer_to_flight(offer, route_id, scraped_at)
            if flight:
                result.append(flight)
        except Exception:
            logger.warning("amadeus: skipping offer due to parse error: %s", offer, exc_info=True)
    logger.info("amadeus parsed %d/%d flights", len(result), len(offers))
    return result


def _parse_offer_to_flight(offer: dict, route_id: int, scraped_at: datetime) -> Flight | None:
    price_str = offer.get("price", {}).get("grandTotal") or offer.get("price", {}).get("total")
    if not price_str:
        return None

    itineraries = offer.get("itineraries", [])
    if not itineraries:
        return None
    itinerary = itineraries[0]
    segments = itinerary.get("segments", [])
    if not segments:
        return None

    first_seg = segments[0]
    last_seg = segments[-1]

    dep_str = first_seg.get("departure", {}).get("at", "")
    arr_str = last_seg.get("arrival", {}).get("at", "")
    if not dep_str or not arr_str:
        return None

    dep_dt = datetime.fromisoformat(dep_str)
    if dep_dt.tzinfo is None:
        dep_dt = dep_dt.replace(tzinfo=timezone.utc)
    arr_dt = datetime.fromisoformat(arr_str)
    if arr_dt.tzinfo is None:
        arr_dt = arr_dt.replace(tzinfo=timezone.utc)

    origin = first_seg.get("departure", {}).get("iataCode", "")
    destination = last_seg.get("arrival", {}).get("iataCode", "")
    if not origin or not destination:
        return None

    duration_str = itinerary.get("duration", "")
    duration_minutes = _parse_duration(duration_str)
    airline = first_seg.get("carrierCode") or first_seg.get("operating", {}).get("carrierCode", "?")
    flight_number = airline + (first_seg.get("number") or "")
    currency = offer.get("price", {}).get("currency", "USD")

    return Flight(
        provider="amadeus",
        airline=airline,
        flight_number=flight_number,
        origin=origin.upper(),
        destination=destination.upper(),
        departure_time=dep_dt,
        arrival_time=arr_dt,
        duration=duration_minutes,
        stops=len(segments) - 1,
        price=Decimal(str(price_str)),
        currency=currency,
        scraped_at=scraped_at,
        route_id=route_id,
    )


def _parse_duration(duration: str) -> int:
    """Parse ISO 8601 duration like PT14H30M into total minutes."""
    if not duration.startswith("PT"):
        return 0
    s = duration[2:]
    hours = 0
    minutes = 0
    if "H" in s:
        h_part, s = s.split("H", 1)
        hours = int(h_part)
    if "M" in s:
        m_part = s.replace("M", "")
        minutes = int(m_part) if m_part else 0
    return hours * 60 + minutes
