"""Unit tests for scheduler/pipeline.py — no DB, no network."""
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from models.cdc import CdcEvent
from models.flight import Flight
from models.route import Route
from scheduler.pipeline import PipelineResult, run_pipeline_for_route

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
_DEP = datetime(2026, 6, 25, 8, 0, tzinfo=timezone.utc)
_ARR = datetime(2026, 6, 25, 11, 30, tzinfo=timezone.utc)


def _make_flight(provider: str = "aviasales", price: str = "125") -> Flight:
    return Flight(
        provider=provider,
        airline="AK",
        flight_number="AK123",
        origin="HAN",
        destination="KUL",
        departure_time=_DEP,
        arrival_time=_ARR,
        duration=200,
        stops=0,
        price=Decimal(price),
        currency="USD",
        scraped_at=_NOW,
        route_id=1,
    )


def _make_route() -> Route:
    return Route(
        route_id=1,
        origin="HAN",
        destination="KUL",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 12, 31),
    )


def _make_event(event_type: str, source: str = "aviasales") -> CdcEvent:
    return CdcEvent(
        event_type=event_type,
        route_id=1,
        source=source,
        flight_key=f"aviasales|AK123|{_DEP.isoformat()}|1",
        new_price=125.0,
        occurred_at=_NOW,
    )


def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


@pytest.mark.asyncio
async def test_pipeline_first_run_all_inserts():
    """On first run (empty flights_current) all fetched flights become INSERT events."""
    flight = _make_flight()
    insert_event = _make_event("INSERT")

    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value={"aviasales": [flight]})):
            with patch("scheduler.pipeline._load_current_flights", return_value=[]):
                with patch("scheduler.pipeline.compare_snapshots", return_value=[insert_event]):
                    with patch("scheduler.pipeline._get_conn", return_value=_mock_conn()):
                        with patch("scheduler.pipeline.check_notification_rules", return_value=None):
                            with patch("scheduler.pipeline.apply_cdc_to_current") as mock_apply:
                                with patch("scheduler.pipeline.append_history") as mock_history:
                                    with patch("scheduler.pipeline.save_cdc_events") as mock_save:
                                        result = await run_pipeline_for_route(1)

    assert isinstance(result, PipelineResult)
    assert result.route_id == 1
    assert result.sources_processed == ["aviasales"]
    assert result.events_count["INSERT"] == 1
    assert result.events_count["UPDATE"] == 0
    assert result.events_count["DELETE"] == 0
    assert result.errors == []
    assert result.duration_seconds >= 0
    mock_apply.assert_called_once()
    mock_history.assert_called_once()
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_no_change_skips_warehouse():
    """When CDC produces no events, warehouse functions are not called."""
    flight = _make_flight()

    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value={"aviasales": [flight]})):
            with patch("scheduler.pipeline._load_current_flights", return_value=[flight]):
                with patch("scheduler.pipeline.compare_snapshots", return_value=[]):
                    with patch("scheduler.pipeline.apply_cdc_to_current") as mock_apply:
                        with patch("scheduler.pipeline.append_history") as mock_history:
                            with patch("scheduler.pipeline.save_cdc_events") as mock_save:
                                result = await run_pipeline_for_route(1)

    assert result.events_count == {"INSERT": 0, "UPDATE": 0, "DELETE": 0}
    mock_apply.assert_not_called()
    mock_history.assert_not_called()
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_multiple_sources():
    """Pipeline processes all sources returned by search planner."""
    avi = _make_flight("aviasales")
    trip = _make_flight("trip")

    search_result = {"aviasales": [avi], "trip": [trip]}

    def fake_cdc(previous, current):
        if not current:
            return []
        src = current[0].provider
        return [_make_event("INSERT", src)]

    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value=search_result)):
            with patch("scheduler.pipeline._load_current_flights", return_value=[]):
                with patch("scheduler.pipeline.compare_snapshots", side_effect=fake_cdc):
                    with patch("scheduler.pipeline._get_conn", return_value=_mock_conn()):
                        with patch("scheduler.pipeline.check_notification_rules", return_value=None):
                            with patch("scheduler.pipeline.apply_cdc_to_current"):
                                with patch("scheduler.pipeline.append_history"):
                                    with patch("scheduler.pipeline.save_cdc_events"):
                                        result = await run_pipeline_for_route(1)

    assert set(result.sources_processed) == {"aviasales", "trip"}
    assert result.events_count["INSERT"] == 2


@pytest.mark.asyncio
async def test_pipeline_error_captured_in_result():
    """Exception in one source is captured in errors, other sources continue."""
    avi = _make_flight("aviasales")
    trip = _make_flight("trip")
    search_result = {"aviasales": [avi], "trip": [trip]}

    call_count = 0

    def load_side_effect(route_id, source):
        nonlocal call_count
        call_count += 1
        if source == "aviasales":
            raise RuntimeError("DB connection lost")
        return []

    def fake_cdc(prev, curr):
        return [_make_event("INSERT", curr[0].provider)] if curr else []

    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value=search_result)):
            with patch("scheduler.pipeline._load_current_flights", side_effect=load_side_effect):
                with patch("scheduler.pipeline.compare_snapshots", side_effect=fake_cdc):
                    with patch("scheduler.pipeline._get_conn", return_value=_mock_conn()):
                        with patch("scheduler.pipeline.check_notification_rules", return_value=None):
                            with patch("scheduler.pipeline.apply_cdc_to_current"):
                                with patch("scheduler.pipeline.append_history"):
                                    with patch("scheduler.pipeline.save_cdc_events"):
                                        result = await run_pipeline_for_route(1)

    assert len(result.errors) == 1
    assert "aviasales" in result.errors[0]
    assert "trip" in result.sources_processed


@pytest.mark.asyncio
async def test_pipeline_empty_search_results():
    """No sources returned by search planner → empty result, no errors."""
    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value={})):
            result = await run_pipeline_for_route(1)

    assert result.route_id == 1
    assert result.sources_processed == []
    assert result.events_count == {"INSERT": 0, "UPDATE": 0, "DELETE": 0}
    assert result.errors == []


@pytest.mark.asyncio
async def test_pipeline_result_has_duration():
    """PipelineResult.duration_seconds is a non-negative float."""
    with patch("scheduler.pipeline._load_route", return_value=_make_route()):
        with patch("scheduler.pipeline.run_search_for_route", new=AsyncMock(return_value={})):
            result = await run_pipeline_for_route(1)

    assert isinstance(result.duration_seconds, float)
    assert result.duration_seconds >= 0
