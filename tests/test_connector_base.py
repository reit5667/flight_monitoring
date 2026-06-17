import pytest

from connectors.base import BaseConnector
from models.flight import Flight
from models.route import Route, SourceMapping


def test_cannot_instantiate_base():
    with pytest.raises(TypeError):
        BaseConnector()


def test_cannot_instantiate_without_fetch():
    class NoFetch(BaseConnector):
        source_name = "test"

    with pytest.raises(TypeError):
        NoFetch()


@pytest.mark.asyncio
async def test_fetch_returns_flights():
    from datetime import date, datetime, timezone
    from decimal import Decimal

    NOW = datetime.now(tz=timezone.utc)

    class OkConnector(BaseConnector):
        source_name = "test"

        async def _fetch(self, route, mapping):
            return [
                Flight(
                    provider="test",
                    airline="TestAir",
                    origin="BKK",
                    destination="HAN",
                    departure_time=NOW,
                    arrival_time=NOW,
                    duration=80,
                    stops=0,
                    price=Decimal("100"),
                    currency="USD",
                    scraped_at=NOW,
                    route_id=1,
                )
            ]

    connector = OkConnector()
    route = Route(
        route_id=1, origin="BKK", destination="HAN",
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31),
    )
    mapping = SourceMapping(route_id=1, source="test", source_origin="BKK", source_destination="HAN")
    flights = await connector.fetch(route, mapping)
    assert len(flights) == 1
    assert flights[0].airline == "TestAir"


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_exception(caplog):
    import logging

    class BrokenConnector(BaseConnector):
        source_name = "broken"

        async def _fetch(self, route, mapping):
            raise RuntimeError("source down")

    from datetime import date

    connector = BrokenConnector()
    route = Route(
        route_id=1, origin="BKK", destination="HAN",
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31),
    )
    mapping = SourceMapping(route_id=1, source="broken", source_origin="BKK", source_destination="HAN")

    with caplog.at_level(logging.ERROR):
        flights = await connector.fetch(route, mapping)

    assert flights == []
    assert "failed" in caplog.text
