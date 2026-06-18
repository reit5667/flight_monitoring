"""Tests for AviasalesConnector.
Unit tests run without network. Live tests require a real TRAVELPAYOUTS_TOKEN in .env.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from connectors.aviasales import AviasalesConnector
from models.route import Route, SourceMapping

ROUTE = Route(
    route_id=1,
    origin="HAN",
    destination="KUL",
    date_from=date.today() + timedelta(days=30),
    date_to=date.today() + timedelta(days=60),
)
MAPPING = SourceMapping(
    route_id=1,
    source="aviasales",
    source_origin="HAN",
    source_destination="KUL",
)

SAMPLE_RESPONSE = {
    "success": True,
    "data": [
        {
            "origin": "HAN",
            "destination": "KUL",
            "origin_airport": "HAN",
            "destination_airport": "KUL",
            "price": 125,
            "airline": "AK",
            "flight_number": "D7535",
            "departure_at": "2026-07-18T10:00:00+07:00",
            "transfers": 0,
            "duration_to": 200,
            "duration": 200,
        }
    ],
    "currency": "usd",
}


def test_source_name():
    assert AviasalesConnector.source_name == "aviasales"


@pytest.mark.asyncio
async def test_fetch_raw_returns_none_without_token(monkeypatch):
    """fetch_raw returns None gracefully when token is missing."""
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "your_token_here")
    c = AviasalesConnector()
    result = await c.fetch_raw(ROUTE, MAPPING)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_raw_returns_none_on_http_error(monkeypatch):
    """On httpx error fetch_raw returns None without raising."""
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "test_token_123")
    c = AviasalesConnector()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = Exception("connection refused")

    with patch("connectors.aviasales.httpx.AsyncClient", return_value=mock_client):
        result = await c.fetch_raw(ROUTE, MAPPING)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_raw_returns_json_on_success(monkeypatch):
    """fetch_raw returns the parsed JSON body on HTTP 200."""
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "test_token_123")
    c = AviasalesConnector()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    with patch("connectors.aviasales.httpx.AsyncClient", return_value=mock_client):
        result = await c.fetch_raw(ROUTE, MAPPING)

    assert result == SAMPLE_RESPONSE


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_no_raw(monkeypatch):
    """_fetch returns [] when fetch_raw gives None."""
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "your_token_here")
    c = AviasalesConnector()
    flights = await c._fetch(ROUTE, MAPPING)
    assert flights == []


@pytest.mark.asyncio
async def test_fetch_calls_save_raw_and_parser(tmp_path, monkeypatch):
    """_fetch saves raw JSON and calls the parser."""
    import storage.raw as raw_module
    monkeypatch.setattr(raw_module, "RAW_STORAGE_DIR", tmp_path / "raw_storage")
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "test_token_123")

    c = AviasalesConnector()
    with patch.object(c, "fetch_raw", new=AsyncMock(return_value=SAMPLE_RESPONSE)):
        flights = await c._fetch(ROUTE, MAPPING)

    assert len(flights) == 1
    assert flights[0].price.to_eng_string() == "125"
    saved = list((tmp_path / "raw_storage" / "aviasales" / "1").glob("*.json"))
    assert len(saved) == 1


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_raw_live():
    """Live test: requires TRAVELPAYOUTS_TOKEN in .env."""
    c = AviasalesConnector()
    result = await c.fetch_raw(ROUTE, MAPPING)
    assert result is not None, "Expected JSON from Travelpayouts API (check TRAVELPAYOUTS_TOKEN in .env)"
    assert result.get("success") is True
    assert "data" in result
