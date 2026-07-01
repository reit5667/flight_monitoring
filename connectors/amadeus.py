import logging
import os
import time

import httpx
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.flight import Flight
from models.route import Route, SourceMapping
from parser.amadeus import parse_amadeus_flights

load_dotenv()

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
_OFFERS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"

# Cached token: (access_token, expires_at)
_token_cache: tuple[str, float] | None = None


async def _get_token(client: httpx.AsyncClient) -> str | None:
    global _token_cache

    client_id = os.getenv("AMADEUS_CLIENT_ID")
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.warning("AMADEUS_CLIENT_ID/SECRET not set — skipping")
        return None

    if _token_cache and time.time() < _token_cache[1]:
        return _token_cache[0]

    try:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 1799))
        _token_cache = (token, time.time() + expires_in - 60)
        return token
    except Exception:
        logger.exception("Amadeus token request failed")
        return None


async def fetch_amadeus_flights(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    currency: str = "RUB",
    max_results: int = 10,
) -> list[dict]:
    """Fetch live flight offers from Amadeus API.

    Returns list of raw offer dicts, or empty list on error/missing credentials.
    departure_date: YYYY-MM-DD
    """
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _get_token(client)
        if not token:
            return []

        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "currencyCode": currency,
            "max": max_results,
            "nonStop": "false",
        }
        try:
            resp = await client.get(
                _OFFERS_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception:
            logger.exception(
                "Amadeus flight-offers failed %s→%s %s", origin, destination, departure_date
            )
            return []


class AmadeusConnector(BaseConnector):
    source_name = "amadeus"

    async def _fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        departure_date = route.date_from.isoformat()
        currency = route.currency or "USD"
        offers = await fetch_amadeus_flights(
            mapping.source_origin,
            mapping.source_destination,
            departure_date,
            currency=currency,
        )
        return parse_amadeus_flights(offers, route_id=route.route_id)
