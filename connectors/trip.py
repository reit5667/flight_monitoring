import logging

from playwright.async_api import async_playwright, Response

from connectors.base import BaseConnector
from models.flight import Flight
from models.route import Route, SourceMapping
from parser.trip import parse_trip
from storage.raw import save_raw

logger = logging.getLogger(__name__)

_SEARCH_BASE = "https://www.trip.com/flights/list"
# Trip.com sends flight data via XHR to this path fragment
_API_PATH = "/flights/api/"
_PAGE_TIMEOUT_MS = 30_000


class TripConnector(BaseConnector):
    source_name = "trip"

    async def fetch_raw(self, route: Route, mapping: SourceMapping) -> dict | None:
        captured: dict | None = None

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()

            async def on_response(response: Response) -> None:
                nonlocal captured
                if captured is not None:
                    return
                if _API_PATH not in response.url:
                    return
                if "json" not in response.headers.get("content-type", ""):
                    return
                try:
                    body = await response.json()
                    if _has_flights(body):
                        captured = body
                except Exception:
                    pass

            page.on("response", on_response)

            url = _search_url(mapping, route)
            try:
                await page.goto(url, timeout=_PAGE_TIMEOUT_MS, wait_until="networkidle")
            except Exception:
                # networkidle timeout is expected on heavy pages — data may already be captured
                logger.warning("trip: page load timeout for %s->%s, captured=%s",
                               mapping.source_origin, mapping.source_destination,
                               captured is not None)
            finally:
                await browser.close()

        return captured

    async def _fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        raw = await self.fetch_raw(route, mapping)
        if raw is None:
            logger.warning("trip: no XHR data captured for %s->%s",
                           mapping.source_origin, mapping.source_destination)
            return []
        save_raw(raw, self.source_name, route.route_id or 0)
        return parse_trip(raw, route.route_id or 0)


def _search_url(mapping: SourceMapping, route: Route) -> str:
    dep = route.date_from.strftime("%Y%m%d")
    return (
        f"{_SEARCH_BASE}?flightWay=Oneway&classType=Economy"
        f"&from={mapping.source_origin}&to={mapping.source_destination}"
        f"&fromDate={dep}"
    )


def _has_flights(body: dict) -> bool:
    """Check that the response actually contains flight itinerary data."""
    try:
        return bool(body.get("data", {}).get("flightItineraryList"))
    except Exception:
        return False
