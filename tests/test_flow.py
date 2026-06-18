"""Unit tests for scheduler/flow.py.

Tests call .fn() on Prefect-decorated functions to bypass server dependency.
"""
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from models.route import Route
from scheduler.pipeline import PipelineResult
from scheduler.flow import run_all_routes, pipeline_task, _load_enabled_routes

_TODAY = date.today()


def _make_route(route_id: int, priority: int = 50) -> Route:
    return Route(
        route_id=route_id,
        origin="HAN",
        destination="KUL",
        date_from=_TODAY,
        date_to=_TODAY,
        priority=priority,
    )


def _make_result(route_id: int, insert_count: int = 3) -> PipelineResult:
    return PipelineResult(
        route_id=route_id,
        sources_processed=["aviasales"],
        events_count={"INSERT": insert_count, "UPDATE": 0, "DELETE": 0},
        duration_seconds=1.5,
        errors=[],
    )


@pytest.mark.asyncio
async def test_run_all_routes_calls_pipeline_for_each_route():
    """run_all_routes calls pipeline_task for every enabled route."""
    routes = [_make_route(1), _make_route(2), _make_route(3)]
    results = [_make_result(r.route_id) for r in routes]

    with patch("scheduler.flow._load_enabled_routes", return_value=routes):
        with patch("scheduler.flow.pipeline_task", new=AsyncMock(side_effect=results)):
            # .fn() calls the underlying Python function without Prefect server
            output = await run_all_routes.fn()

    assert len(output) == 3
    assert [r.route_id for r in output] == [1, 2, 3]


@pytest.mark.asyncio
async def test_run_all_routes_respects_priority_order():
    """Routes are processed in the order returned by _load_enabled_routes (priority DESC)."""
    routes = [
        _make_route(1, priority=100),
        _make_route(2, priority=50),
        _make_route(3, priority=10),
    ]
    call_order = []

    async def fake_task(route_id):
        call_order.append(route_id)
        return _make_result(route_id)

    with patch("scheduler.flow._load_enabled_routes", return_value=routes):
        with patch("scheduler.flow.pipeline_task", new=AsyncMock(side_effect=fake_task)):
            await run_all_routes.fn()

    assert call_order == [1, 2, 3]


@pytest.mark.asyncio
async def test_run_all_routes_no_routes():
    """No enabled routes → returns empty list."""
    with patch("scheduler.flow._load_enabled_routes", return_value=[]):
        output = await run_all_routes.fn()

    assert output == []


@pytest.mark.asyncio
async def test_pipeline_task_returns_result():
    """pipeline_task.fn() calls run_pipeline_for_route and returns its result."""
    expected = _make_result(1)

    with patch("scheduler.flow.run_pipeline_for_route", new=AsyncMock(return_value=expected)):
        result = await pipeline_task.fn(route_id=1)

    assert result.route_id == 1
    assert result.events_count["INSERT"] == 3


def test_load_enabled_routes_sorted_by_priority():
    """_load_enabled_routes returns routes ordered by priority DESC from DB."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_cursor.fetchall.return_value = [
        (1, "HAN", "KUL", date(2026, 8, 1), date(2026, 8, 31), None, "USD", 100, 60, True, None),
        (2, "SGN", "BKK", date(2026, 8, 1), date(2026, 8, 31), None, "USD", 50,  60, True, None),
    ]

    with patch("scheduler.flow._get_conn", return_value=mock_conn):
        routes = _load_enabled_routes()

    assert len(routes) == 2
    assert routes[0].route_id == 1
    assert routes[0].priority == 100
    assert routes[1].route_id == 2
