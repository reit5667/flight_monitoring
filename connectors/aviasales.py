import logging
import os
from datetime import date

import httpx
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.flight import Flight
from models.route import Route, SourceMapping
from parser.aviasales import parse_aviasales
from storage.raw import save_raw

load_dotenv()

logger = logging.getLogger(__name__)

_API_BASE = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


class AviasalesConnector(BaseConnector):
    source_name = "aviasales"

    async def fetch_raw(
        self,
        route: Route,
        mapping: SourceMapping,
        search_date: date | None = None,
    ) -> dict | None:
        """Call Travelpayouts API and return raw JSON response."""
        token = os.getenv("TRAVELPAYOUTS_TOKEN")
        if not token or token == "your_token_here":
            logger.warning("TRAVELPAYOUTS_TOKEN not set — skipping aviasales fetch")
            return None

        if search_date is None:
            search_date = route.date_from

        params = {
            "origin": mapping.source_origin,
            "destination": mapping.source_destination,
            "departure_at": search_date.strftime("%Y-%m-%d"),
            "currency": route.currency.lower(),
            "sorting": "price",
            "direct": "false",
            "limit": 50,
            "token": token,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(_API_BASE, params=params)
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.exception(
                "aviasales fetch_raw failed route=%s->%s date=%s",
                mapping.source_origin,
                mapping.source_destination,
                search_date,
            )
            return None

    async def _fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        raw = await self.fetch_raw(route, mapping)
        if raw is None:
            return []

        save_raw(raw, self.source_name, route.route_id or 0)
        return parse_aviasales(raw, route.route_id or 0)
