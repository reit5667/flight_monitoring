import logging
import os

import httpx
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.flight import Flight
from models.route import Route, SourceMapping
from parser.serpapi import parse_serpapi_flights

load_dotenv()

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://serpapi.com/search"


async def fetch_serpapi_flights(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    currency: str = "USD",
    max_results: int = 10,
) -> list[dict]:
    """Fetch Google Flights results via SerpApi.

    Returns list of raw best_flights/other_flights dicts, or empty list on error.
    departure_date: YYYY-MM-DD
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or api_key == "your_serpapi_key":
        logger.warning("SERPAPI_KEY not set — skipping")
        return []

    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": departure_date,
        "adults": adults,
        "currency": currency,
        "hl": "en",
        "type": "2",  # one-way
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            flights = data.get("best_flights", []) + data.get("other_flights", [])
            return flights[:max_results]
    except Exception:
        logger.exception("SerpApi fetch failed %s→%s %s", origin, destination, departure_date)
        return []


class SerpApiConnector(BaseConnector):
    source_name = "serpapi"

    async def _fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        departure_date = route.date_from.isoformat()
        raw_flights = await fetch_serpapi_flights(
            mapping.source_origin,
            mapping.source_destination,
            departure_date,
            currency=route.currency or "USD",
        )
        return parse_serpapi_flights(raw_flights, route_id=route.route_id or 0)
