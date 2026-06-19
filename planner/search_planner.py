import logging

from connectors.aviasales import AviasalesConnector
from connectors.base import BaseConnector
from connectors.trip import TripConnector
from db import get_conn as _get_conn
from models.flight import Flight
from models.route import Route, SourceMapping

logger = logging.getLogger(__name__)

_CONNECTOR_REGISTRY: dict[str, BaseConnector] = {
    "aviasales": AviasalesConnector(),
    "trip": TripConnector(),
}


def _load_route(conn, route_id: int) -> Route:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT route_id, origin, destination, date_from, date_to,
                   max_price, currency, priority, search_interval, enabled, notes
            FROM routes WHERE route_id = %s
            """,
            (route_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Route {route_id} not found")
    cols = [
        "route_id", "origin", "destination", "date_from", "date_to",
        "max_price", "currency", "priority", "search_interval", "enabled", "notes",
    ]
    return Route(**dict(zip(cols, row)))


def _load_enabled_mappings(conn, route_id: int) -> list[SourceMapping]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, route_id, source, source_origin, source_destination, enabled
            FROM source_route_mappings
            WHERE route_id = %s AND enabled = true
            """,
            (route_id,),
        )
        rows = cur.fetchall()
    cols = ["id", "route_id", "source", "source_origin", "source_destination", "enabled"]
    return [SourceMapping(**dict(zip(cols, row))) for row in rows]


async def run_search_for_route(route_id: int) -> dict[str, list[Flight]]:
    with _get_conn() as conn:
        route = _load_route(conn, route_id)
        mappings = _load_enabled_mappings(conn, route_id)

    results: dict[str, list[Flight]] = {}

    for mapping in mappings:
        connector = _CONNECTOR_REGISTRY.get(mapping.source)
        if connector is None:
            logger.info("planner: no connector registered for source=%s, skipping", mapping.source)
            continue
        flights = await connector.fetch(route, mapping)
        results[mapping.source] = flights

    known_sources = set(_CONNECTOR_REGISTRY.keys())
    mapped_sources = {m.source for m in mappings}
    for source in known_sources - mapped_sources:
        logger.info("planner: no enabled mapping for source=%s route_id=%d, skipping", source, route_id)

    return results
