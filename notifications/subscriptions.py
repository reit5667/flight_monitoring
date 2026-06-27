"""
Проверка подписок пользователей и отправка алёртов при изменении цены.

Правила:
  - Подешевело: new_price < alert_price (любое снижение)
  - Подорожало: new_price > alert_price * (1 + SPIKE_PCT), по умолчанию 25%
"""
import logging
import os
from decimal import Decimal

from db import get_conn
from models.cdc import CdcEvent
from notifications.telegram import send_notification

logger = logging.getLogger(__name__)

_SPIKE_PCT = float(os.getenv("SUBSCRIPTION_SPIKE_PCT", "0.25"))
_AVIASALES_BASE = "https://www.aviasales.ru/search"


def _aviasales_url(origin: str, dest: str) -> str:
    return f"{_AVIASALES_BASE}/{origin}0101{dest}1"


def _load_active_subscriptions(route_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chat_id, origin, dest, alert_price
                FROM subscriptions
                WHERE route_id = %s AND is_active = TRUE
                """,
                (route_id,),
            )
            rows = cur.fetchall()
    return [
        {"id": r[0], "chat_id": r[1], "origin": r[2], "dest": r[3], "alert_price": Decimal(str(r[4]))}
        for r in rows
    ]


async def check_subscriptions(events: list[CdcEvent], route_id: int) -> None:
    """Send alerts to subscribers if price dropped or spiked significantly."""
    update_events = [e for e in events if e.event_type == "UPDATE" and e.new_price is not None and e.old_price is not None]
    if not update_events:
        return

    subs = _load_active_subscriptions(route_id)
    if not subs:
        return

    for event in update_events:
        old_price = Decimal(str(event.old_price))
        new_price = Decimal(str(event.new_price))
        pct = float((new_price - old_price) / old_price * 100)

        for sub in subs:
            alert_price = sub["alert_price"]
            origin, dest = sub["origin"], sub["dest"]
            label = f"{origin} → {dest}"
            url = _aviasales_url(origin, dest)

            if new_price < alert_price:
                drop_pct = float((alert_price - new_price) / alert_price * 100)
                msg = (
                    f"🔔 <b>{label} подешевело!</b>\n\n"
                    f"Было: <b>{old_price:,.0f}₽</b> → Стало: <b>{new_price:,.0f}₽</b>  "
                    f"({pct:+.0f}%)\n"
                    f"Ниже цены подписки на <b>{drop_pct:.0f}%</b> "
                    f"(подписка: {alert_price:,.0f}₽)\n\n"
                    f'<a href="{url}">Смотреть на Aviasales</a>'
                )
                ok = await send_notification(msg, chat_id=str(sub["chat_id"]))
                if ok:
                    logger.info("subscription alert sent chat_id=%s route_id=%d (drop)", sub["chat_id"], route_id)

            elif float(new_price) > float(alert_price) * (1 + _SPIKE_PCT):
                rise_pct = float((new_price - alert_price) / alert_price * 100)
                msg = (
                    f"⚠️ <b>{label} резко подорожало</b>\n\n"
                    f"Было: <b>{old_price:,.0f}₽</b> → Стало: <b>{new_price:,.0f}₽</b>  "
                    f"({pct:+.0f}%)\n"
                    f"Выше цены подписки на <b>{rise_pct:.0f}%</b> "
                    f"(подписка: {alert_price:,.0f}₽)\n\n"
                    f'<a href="{url}">Смотреть на Aviasales</a>'
                )
                ok = await send_notification(msg, chat_id=str(sub["chat_id"]))
                if ok:
                    logger.info("subscription alert sent chat_id=%s route_id=%d (spike)", sub["chat_id"], route_id)
