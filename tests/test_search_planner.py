"""Unit tests for planner/search_planner.py — no DB, no network."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from models.flight import Flight
from models.route import Route, SourceMapping
from planner.search_planner import run_search_for_route

_TODAY = date.today()

_ROUTE = Route(
    route_id=1,
    origin="HAN",
    destination="KUL",
    date_from=_TODAY + timedelta(days=30),
    date_to=_TODAY + timedelta(days=60),
)

_MAPPINGS = [
    SourceMapping(id=1, route_id=1, source="aviasales", source_origin="HAN", source_destination="KUL"),
    SourceMapping(id=2, route_id=1, source="trip", source_origin="HAN", source_destination="KUL"),
]


def _make_flight(provider: str) -> Flight:
    from datetime import datetime, timezone
    dep = datetime(_TODAY.year, _TODAY.month, _TODAY.day, 10, 0, 0, tzinfo=timezone.utc)
    return Flight(
        provider=provider,
        airline="AK",
        flight_number="AK123",
        origin="HAN",
        destination="KUL",
        departure_time=dep,
        arrival_time=dep,
        duration=200,
        stops=0,
        price=Decimal("125"),
        currency="USD",
        scraped_at=dep,
        route_id=1,
    )


def _patch_db(route=_ROUTE, mappings=_MAPPINGS):
    """Return a context manager that patches _get_conn, _load_route, _load_enabled_mappings."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    conn_patcher = patch("planner.search_planner._get_conn", return_value=mock_conn)
    route_patcher = patch("planner.search_planner._load_route", return_value=route)
    mappings_patcher = patch("planner.search_planner._load_enabled_mappings", return_value=mappings)
    return conn_patcher, route_patcher, mappings_patcher


@pytest.mark.asyncio
async def test_returns_dict_with_all_sources():
    """When all mappings are enabled, result has keys for all sources."""
    avi_flight = _make_flight("aviasales")
    trip_flight = _make_flight("trip")

    conn_p, route_p, map_p = _patch_db()
    with conn_p, route_p, map_p:
        with patch("planner.search_planner._CONNECTOR_REGISTRY", {
            "aviasales": MagicMock(fetch=AsyncMock(return_value=[avi_flight])),
            "trip": MagicMock(fetch=AsyncMock(return_value=[trip_flight])),
        }):
            result = await run_search_for_route(1)

    assert set(result.keys()) == {"aviasales", "trip"}
    assert result["aviasales"] == [avi_flight]
    assert result["trip"] == [trip_flight]


@pytest.mark.asyncio
async def test_skips_source_without_mapping():
    """When only one mapping is enabled, result has only one key."""
    one_mapping = [
        SourceMapping(id=1, route_id=1, source="aviasales", source_origin="HAN", source_destination="KUL"),
    ]
    avi_flight = _make_flight("aviasales")

    conn_p, route_p, map_p = _patch_db(mappings=one_mapping)
    with conn_p, route_p, map_p:
        with patch("planner.search_planner._CONNECTOR_REGISTRY", {
            "aviasales": MagicMock(fetch=AsyncMock(return_value=[avi_flight])),
            "trip": MagicMock(fetch=AsyncMock(return_value=[])),
        }):
            result = await run_search_for_route(1)

    assert set(result.keys()) == {"aviasales"}
    assert "trip" not in result


@pytest.mark.asyncio
async def test_skips_unknown_source_with_log(caplog):
    """Unknown source in mapping is skipped with INFO log."""
    unknown_mapping = [
        SourceMapping(id=99, route_id=1, source="unknown_source", source_origin="HAN", source_destination="KUL"),
    ]

    conn_p, route_p, map_p = _patch_db(mappings=unknown_mapping)
    with conn_p, route_p, map_p:
        with patch("planner.search_planner._CONNECTOR_REGISTRY", {
            "aviasales": MagicMock(fetch=AsyncMock(return_value=[])),
        }):
            import logging
            with caplog.at_level(logging.INFO, logger="planner.search_planner"):
                result = await run_search_for_route(1)

    assert result == {}
    assert any("no connector registered" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_mappings_returns_empty_dict():
    """No enabled mappings → empty result."""
    conn_p, route_p, map_p = _patch_db(mappings=[])
    with conn_p, route_p, map_p:
        with patch("planner.search_planner._CONNECTOR_REGISTRY", {
            "aviasales": MagicMock(fetch=AsyncMock(return_value=[])),
        }):
            result = await run_search_for_route(1)

    assert result == {}


@pytest.mark.asyncio
async def test_connector_returns_empty_list_on_failure():
    """If connector returns [] (e.g., scraping failed), result key still present with empty list."""
    conn_p, route_p, map_p = _patch_db(mappings=[
        SourceMapping(id=1, route_id=1, source="aviasales", source_origin="HAN", source_destination="KUL"),
    ])
    with conn_p, route_p, map_p:
        with patch("planner.search_planner._CONNECTOR_REGISTRY", {
            "aviasales": MagicMock(fetch=AsyncMock(return_value=[])),
        }):
            result = await run_search_for_route(1)

    assert result == {"aviasales": []}


@pytest.mark.asyncio
async def test_route_not_found_raises():
    """ValueError is raised if route_id doesn't exist in DB."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("planner.search_planner._get_conn", return_value=mock_conn):
        with patch("planner.search_planner._load_route", side_effect=ValueError("Route 999 not found")):
            with pytest.raises(ValueError, match="Route 999 not found"):
                await run_search_for_route(999)
