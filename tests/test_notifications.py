from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import notifications.dedup as dedup_module
from models.cdc import CdcEvent
from models.route import Route
from notifications.dedup import clear_cache, should_send
from notifications.rules import NotificationTrigger, check_notification_rules
from notifications.telegram import send_notification


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_route(**kwargs) -> Route:
    defaults = dict(
        route_id=1,
        origin="HAN",
        destination="KUL",
        date_from="2026-08-01",
        date_to="2026-08-31",
    )
    return Route(**(defaults | kwargs))


def _make_event(event_type="UPDATE", new_price=100.0, old_price=200.0) -> CdcEvent:
    return CdcEvent(
        event_type=event_type,
        route_id=1,
        source="aviasales",
        flight_key="aviasales|VJ123|2026-08-15T09:30:00+00:00|1",
        old_price=old_price,
        new_price=new_price,
        occurred_at=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),
    )


def _mock_conn(rolling_avg: float | None, hist_min: float | None) -> MagicMock:
    """Build a mock psycopg2 connection that returns given values for the two queries."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    # First call → hist_min query, second call → rolling_avg query
    cursor.fetchone.side_effect = [
        (hist_min,) if hist_min is not None else (None,),
        (rolling_avg,) if rolling_avg is not None else (None,),
    ]
    return conn


@pytest.mark.asyncio
async def test_send_notification_returns_false_for_empty_message():
    result = await send_notification("")
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_returns_false_when_token_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = await send_notification("test")
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_returns_false_when_chat_id_missing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "some_token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = await send_notification("test")
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")

    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)

    with patch("notifications.telegram.Bot", return_value=mock_bot):
        result = await send_notification("Тест: pipeline запущен")

    assert result is True
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "456"
    assert "Тест" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_send_notification_returns_false_on_telegram_error(monkeypatch):
    from telegram.error import TelegramError

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "invalid_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")

    mock_bot = AsyncMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=False)
    mock_bot.send_message.side_effect = TelegramError("Unauthorized")

    with patch("notifications.telegram.Bot", return_value=mock_bot):
        result = await send_notification("test message")

    assert result is False


# ── check_notification_rules ──────────────────────────────────────────────────

def test_delete_event_returns_none():
    conn = _mock_conn(rolling_avg=200.0, hist_min=180.0)
    event = _make_event(event_type="DELETE", new_price=None)
    assert check_notification_rules(event, _make_route(), conn) is None


def test_no_new_price_returns_none():
    conn = _mock_conn(rolling_avg=200.0, hist_min=180.0)
    event = _make_event(event_type="UPDATE", new_price=None)
    assert check_notification_rules(event, _make_route(), conn) is None


def test_historical_min_rule_triggers():
    # current_price=130 < hist_min=150 → HISTORICAL_MIN
    conn = _mock_conn(rolling_avg=190.0, hist_min=150.0)
    event = _make_event(new_price=130.0)
    trigger = check_notification_rules(event, _make_route(), conn)
    assert trigger is not None
    assert trigger.rule_type == "HISTORICAL_MIN"
    assert trigger.current_price == 130.0
    assert trigger.baseline_price == 150.0
    assert trigger.drop_pct > 0


def test_historical_min_takes_priority_over_significant_drop():
    # Both rules could trigger, but HISTORICAL_MIN should win
    conn = _mock_conn(rolling_avg=200.0, hist_min=150.0)
    event = _make_event(new_price=100.0)  # 50% below avg AND new min
    trigger = check_notification_rules(event, _make_route(), conn)
    assert trigger is not None
    assert trigger.rule_type == "HISTORICAL_MIN"


def test_significant_drop_rule_triggers(monkeypatch):
    monkeypatch.setenv("PRICE_DROP_THRESHOLD_PCT", "15")
    # current=160, avg=200 → drop=20% >= 15% threshold
    # hist_min=155 → current NOT below hist_min, so SIGNIFICANT_DROP fires
    conn = _mock_conn(rolling_avg=200.0, hist_min=155.0)
    event = _make_event(new_price=160.0)
    trigger = check_notification_rules(event, _make_route(), conn)
    assert trigger is not None
    assert trigger.rule_type == "SIGNIFICANT_DROP"
    assert abs(trigger.drop_pct - 20.0) < 0.1


def test_no_trigger_when_price_change_is_small(monkeypatch):
    monkeypatch.setenv("PRICE_DROP_THRESHOLD_PCT", "15")
    # current=190, avg=200 → drop=5% < 15%, no hist_min beat
    conn = _mock_conn(rolling_avg=200.0, hist_min=185.0)
    event = _make_event(new_price=190.0)
    assert check_notification_rules(event, _make_route(), conn) is None


def test_no_trigger_when_no_history():
    # First run: no data in flights_history yet
    conn = _mock_conn(rolling_avg=None, hist_min=None)
    event = _make_event(event_type="INSERT", new_price=150.0, old_price=None)
    assert check_notification_rules(event, _make_route(), conn) is None


def test_trigger_message_contains_route_and_price():
    conn = _mock_conn(rolling_avg=200.0, hist_min=130.0)
    event = _make_event(new_price=100.0)
    trigger = check_notification_rules(event, _make_route(), conn)
    assert "HAN" in trigger.message
    assert "KUL" in trigger.message
    assert "100" in trigger.message


# ── should_send (dedup) ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_dedup_cache():
    clear_cache()
    yield
    clear_cache()


def test_should_send_returns_true_for_new_event():
    event = _make_event()
    assert should_send(event, "SIGNIFICANT_DROP") is True


def test_should_send_returns_false_on_repeat_within_window(monkeypatch):
    monkeypatch.setenv("DEDUP_WINDOW_HOURS", "4")
    event = _make_event()
    assert should_send(event, "SIGNIFICANT_DROP") is True
    assert should_send(event, "SIGNIFICANT_DROP") is False


def test_should_send_returns_true_after_window_expires(monkeypatch):
    monkeypatch.setenv("DEDUP_WINDOW_HOURS", "4")
    event = _make_event()
    should_send(event, "SIGNIFICANT_DROP")  # marks as sent now

    # Simulate 5 hours having passed by backdating the cache entry
    key = (event.route_id, event.flight_key, "SIGNIFICANT_DROP")
    dedup_module._sent_cache[key] = datetime.now(timezone.utc) - timedelta(hours=5)

    assert should_send(event, "SIGNIFICANT_DROP") is True


def test_should_send_different_rule_types_are_independent():
    event = _make_event()
    assert should_send(event, "SIGNIFICANT_DROP") is True
    assert should_send(event, "HISTORICAL_MIN") is True  # different rule_type → allowed


def test_should_send_different_flight_keys_are_independent():
    event_a = _make_event()
    event_b = _make_event()
    event_b = event_b.model_copy(update={"flight_key": "aviasales|VJ999|2026-08-16T10:00:00+00:00|1"})
    assert should_send(event_a, "SIGNIFICANT_DROP") is True
    assert should_send(event_b, "SIGNIFICANT_DROP") is True  # different flight → allowed
