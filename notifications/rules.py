import logging
import os

from dotenv import load_dotenv
from pydantic import BaseModel

from models.cdc import CdcEvent
from models.route import Route

load_dotenv()
logger = logging.getLogger(__name__)

# Read as plain percentage, e.g. 15 means 15%
_THRESHOLD_PCT = float(os.getenv("PRICE_DROP_THRESHOLD_PCT", "15"))
_ROLLING_WINDOW_DAYS = 30


class NotificationTrigger(BaseModel):
    rule_type: str          # "SIGNIFICANT_DROP" | "HISTORICAL_MIN"
    flight_key: str
    route_id: int
    source: str
    current_price: float
    baseline_price: float   # rolling avg or historical min
    drop_pct: float         # positive number, e.g. 20.5 means 20.5% below baseline
    message: str            # pre-formatted HTML for Telegram


def _get_rolling_average(conn, route_id: int, source: str) -> float | None:
    """AVG price for route+source over last 30 days from flights_history."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT AVG(price)
            FROM flights_history
            WHERE route_id = %s
              AND provider = %s
              AND valid_from >= NOW() - INTERVAL '30 days'
            """,
            (route_id, source),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _get_historical_min(conn, route_id: int, source: str) -> float | None:
    """All-time MIN price for route+source from flights_history."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(price) FROM flights_history WHERE route_id = %s AND provider = %s",
            (route_id, source),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _format_message(rule_type: str, event: CdcEvent, route: Route, current: float, baseline: float) -> str:
    drop_pct = (baseline - current) / baseline * 100
    route_label = f"{route.origin} → {route.destination}"

    if rule_type == "HISTORICAL_MIN":
        detail = f"📉 Новый минимум! Обычно ~<b>${baseline:.0f}</b> (−{drop_pct:.0f}%)"
    else:
        detail = f"💥 Цена упала на <b>{drop_pct:.0f}%</b> (обычно ~${baseline:.0f})"

    return (
        f"✈️ <b>{route_label}</b>\n"
        f"💰 <b>${current:.0f}</b>  {detail}\n"
        f"📡 {event.source}"
    )


def check_notification_rules(event: CdcEvent, route: Route, conn) -> NotificationTrigger | None:
    """
    Called BEFORE warehouse write so flights_history reflects the previous state.
    Returns the most impactful trigger, or None if nothing significant happened.
    """
    if event.event_type == "DELETE" or event.new_price is None:
        return None

    current = event.new_price
    source = event.source

    # Rule 1 (highest priority): new all-time historical minimum
    hist_min = _get_historical_min(conn, event.route_id, source)
    if hist_min is not None and current < hist_min:
        drop_pct = (hist_min - current) / hist_min * 100
        return NotificationTrigger(
            rule_type="HISTORICAL_MIN",
            flight_key=event.flight_key,
            route_id=event.route_id,
            source=source,
            current_price=current,
            baseline_price=hist_min,
            drop_pct=drop_pct,
            message=_format_message("HISTORICAL_MIN", event, route, current, hist_min),
        )

    # Rule 2: significant drop below 30-day rolling average
    avg = _get_rolling_average(conn, event.route_id, source)
    if avg is not None and avg > 0:
        drop_pct = (avg - current) / avg * 100
        if drop_pct >= _THRESHOLD_PCT:
            return NotificationTrigger(
                rule_type="SIGNIFICANT_DROP",
                flight_key=event.flight_key,
                route_id=event.route_id,
                source=source,
                current_price=current,
                baseline_price=avg,
                drop_pct=drop_pct,
                message=_format_message("SIGNIFICANT_DROP", event, route, current, avg),
            )

    return None
