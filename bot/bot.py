"""
Telegram-бот для поиска авиабилетов.

Команды:
  /start    — приветствие + постоянное меню
  /search   — поиск билетов (пассажиры → маршрут → календарь → результат)
  /history  — история цен по маршруту
  /unwatch  — управление подписками
  /help     — справка

Кнопки меню: «🔍 Поиск», «📊 История цен», «ℹ️ Помощь»
"""
import asyncio
import calendar as cal_module
import logging
import os
from datetime import date, datetime, timezone

import httpx
from decimal import Decimal
from dotenv import load_dotenv
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import get_conn
from bot.airports import route_label, parse_route_input, search_cities, parse_route_with_countries, resolve_country
from connectors.serpapi import fetch_serpapi_flights
from parser.serpapi import parse_serpapi_offers

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_API_URL    = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
_TP_TOKEN   = os.getenv("TRAVELPAYOUTS_TOKEN", "")
_MINIAPP_URL = os.getenv("MINIAPP_URL", "")  # https://your-domain/  (пусто = кнопка скрыта)

# Аэропорты Шенгенской зоны — используются для фильтрации транзитных пересадок
_SCHENGEN_AIRPORTS: frozenset[str] = frozenset({
    # Австрия
    "VIE", "GRZ", "LNZ", "SZG",
    # Бельгия
    "BRU", "CRL", "LGG",
    # Чехия
    "PRG", "BRQ", "OSR",
    # Дания
    "CPH", "AAL", "AAR",
    # Эстония
    "TLL",
    # Финляндия
    "HEL", "TMP", "TKU", "OUL",
    # Франция
    "CDG", "ORY", "NCE", "LYS", "MRS", "BOD", "TLS", "NTE", "SXB",
    # Германия
    "FRA", "MUC", "BER", "HAM", "DUS", "STR", "CGN", "NUE", "LEJ", "HAJ",
    # Греция
    "ATH", "SKG", "HER", "RHO", "CFU", "KGS", "ZTH", "CHQ",
    # Венгрия
    "BUD", "DEB",
    # Исландия
    "KEF",
    # Италия
    "FCO", "MIL", "MXP", "LIN", "BGY", "VCE", "NAP", "BLQ", "CTA", "PSA", "PMO", "BRI", "CAG",
    # Латвия
    "RIX",
    # Литва
    "VNO", "KUN",
    # Люксембург
    "LUX",
    # Мальта
    "MLA",
    # Нидерланды
    "AMS", "EIN", "RTM",
    # Норвегия
    "OSL", "BGO", "TRD", "SVG",
    # Польша
    "WAW", "KRK", "KTW", "GDN", "POZ", "WRO",
    # Португалия
    "LIS", "OPO", "FAO",
    # Словакия
    "BTS", "KSC",
    # Словения
    "LJU",
    # Испания
    "MAD", "BCN", "AGP", "PMI", "ALC", "VLC", "IBZ", "SVQ", "BIO", "TFS", "LPA",
    # Швеция
    "ARN", "GOT", "MMX",
    # Швейцария
    "ZRH", "GVA", "BSL",
    # Румыния (в Шенгене с марта 2024 для авиа)
    "OTP", "CLJ", "TSR",
})

# callback_data prefixes (kept short — Telegram limit 64 bytes)
_CB_PAX     = "pax"   # pax:{adults}
_CB_ROUTE   = "route" # route:{route_id}:{origin}:{dest}:{date_from}:{date_to}:{adults}
_CB_CUSTOM  = "cr"    # cr:{adults}  — free-form route entry
_CB_CAL_DAY = "cd"    # cd:{rid}:{org}:{dst}:{adt}:{step}:{from}:{y}:{m}:{d}
_CB_CAL_NAV = "cn"    # cn:{rid}:{org}:{dst}:{adt}:{step}:{from}:{y}:{m}
_CB_HIST    = "hist"  # hist:{route_id}:{origin}:{dest}
_CB_ONEWAY  = "ow"    # ow:{rid}:{org}:{dst}:{adt}:{from_date}
_CB_WATCH     = "watch"    # watch:{route_id}:{origin}:{dest}:{price_int}
_CB_UNWATCH   = "unwatch"  # unwatch:{sub_id}
_CB_CHEAPEST  = "cheap"    # cheap:{route_id}:{origin}:{dest}:{adults}:{year}:{month}
_CB_CITY_PICK = "cp"       # cp:{adults}:{step}:{iata}  — выбор города из подсказок
_CB_DEL_ROUTE = "dr"       # dr:{route_id}  — удалить маршрут из БД
_CB_DEL_CONF  = "drc"      # drc:{route_id} — подтверждение удаления
_CB_VF_TOGGLE = "vft"      # vft:{visa_free}  — переключатель фильтра visa_free на экране пассажиров
_CB_BACK_ROUTES = "br"    # br:{adults}:{visa_free} — вернуться к списку маршрутов
_CB_FILTER_OPEN = "fo"    # fo  — открыть экран фильтров
_CB_FILTER_TOG  = "ft"    # ft:{key}:{value}  — переключить один фильтр
_CB_FILTER_DONE = "fd"    # fd  — закрыть фильтры, вернуться к маршрутам

_MENU_SEARCH  = "🔍 Поиск"
_MENU_HISTORY = "📊 История цен"
_MENU_HELP    = "ℹ️ Помощь"

_MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[_MENU_SEARCH, _MENU_HISTORY, _MENU_HELP]],
    resize_keyboard=True,
    is_persistent=True,
)

_MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}
_MONTHS_SHORT = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр",
    5: "Май", 6: "Июн", 7: "Июл", 8: "Авг",
    9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}

_SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

# user_data keys
_STATE_AWAITING_ROUTE  = "awaiting_route"   # {"adults": int}
_STATE_AWAITING_DEST   = "awaiting_dest"    # {"adults": int, "origin": str} — origin выбран, ждём dest


# ---------------------------------------------------------------------------
# Calendar widget
# ---------------------------------------------------------------------------

def _build_calendar(
    year: int, month: int,
    step: str,           # "f" = picking from-date, "t" = picking to-date
    rid: str, org: str, dst: str, adt: str,
    from_date: str = "X",  # ISO or "X" when not yet chosen
) -> InlineKeyboardMarkup:
    today = date.today()
    nav_base = f"{rid}:{org}:{dst}:{adt}:{step}:{from_date}"

    prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
    next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)

    title = f"{_MONTHS_RU[month]} {year}"
    if step == "t" and from_date != "X":
        fd = date.fromisoformat(from_date)
        title += f"  (от {fd.strftime('%d.%m')})"

    header = [
        InlineKeyboardButton("◀", callback_data=f"{_CB_CAL_NAV}:{nav_base}:{prev_y}:{prev_m}"),
        InlineKeyboardButton(title, callback_data="noop"),
        InlineKeyboardButton("▶", callback_data=f"{_CB_CAL_NAV}:{nav_base}:{next_y}:{next_m}"),
    ]

    dow_header = [InlineKeyboardButton(d, callback_data="noop")
                  for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]]

    day_base = f"{rid}:{org}:{dst}:{adt}:{step}:{from_date}:{year}:{month}"
    day_rows = []
    for week in cal_module.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
            else:
                d = date(year, month, day)
                if d < today:
                    row.append(InlineKeyboardButton("·", callback_data="noop"))
                elif step == "t" and from_date != "X" and d < date.fromisoformat(from_date):
                    row.append(InlineKeyboardButton("·", callback_data="noop"))
                else:
                    label = f"[{day}]" if step == "t" and from_date != "X" and str(d) == from_date else str(day)
                    row.append(InlineKeyboardButton(label, callback_data=f"{_CB_CAL_DAY}:{day_base}:{day}"))
        day_rows.append(row)

    rows = [header, dow_header] + day_rows
    if step == "f":
        rows.append([InlineKeyboardButton(
            f"📅 Весь {_MONTHS_RU[month].lower()} (самый дешёвый)",
            callback_data=f"{_CB_CHEAPEST}:{rid}:{org}:{dst}:{adt}:{year}:{month}",
        )])
    if step == "t":
        rows.append([InlineKeyboardButton(
            "🚀 Обратный билет не нужен",
            callback_data=f"{_CB_ONEWAY}:{rid}:{org}:{dst}:{adt}:{from_date}",
        )])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_enabled_routes(visa_free_only: bool = True) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_id, origin, destination, date_from, date_to, notes
                FROM routes
                WHERE enabled = true
                  AND (NOT %(visa_free_only)s OR visa_free = true)
                ORDER BY priority DESC, route_id
                """,
                {"visa_free_only": visa_free_only},
            )
            rows = cur.fetchall()
    cols = ["route_id", "origin", "destination", "date_from", "date_to", "notes"]
    return [dict(zip(cols, row)) for row in rows]


def _load_price_history(route_id: int) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DATE(valid_from) AS day, MIN(price::numeric) AS min_price
                FROM flights_history
                WHERE route_id = %s AND valid_from >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(valid_from)
                ORDER BY day
                """,
                (route_id,),
            )
            daily = [{"day": r[0], "price": float(r[1])} for r in cur.fetchall()]

            cur.execute("SELECT MIN(price::numeric) FROM flights_history WHERE route_id = %s", (route_id,))
            row = cur.fetchone()
            all_time_min = float(row[0]) if row and row[0] else None

            cur.execute(
                "SELECT valid_from FROM flights_history WHERE route_id = %s AND price::numeric = %s ORDER BY valid_from DESC LIMIT 1",
                (route_id, all_time_min),
            )
            row = cur.fetchone()
            all_time_min_at = row[0] if row else None

            cur.execute(
                """
                SELECT occurred_at, old_price, new_price FROM cdc_events
                WHERE route_id = %s AND event_type = 'UPDATE'
                  AND old_price IS NOT NULL AND new_price IS NOT NULL
                ORDER BY occurred_at DESC LIMIT 5
                """,
                (route_id,),
            )
            changes = [{"at": r[0], "old": float(r[1]), "new": float(r[2])} for r in cur.fetchall()]

    return {"daily": daily, "all_time_min": all_time_min, "all_time_min_at": all_time_min_at, "changes": changes}


def _ensure_route(origin: str, dest: str) -> int:
    """Return existing route_id or insert a new monitoring route."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT route_id FROM routes WHERE origin = %s AND destination = %s LIMIT 1",
                (origin, dest),
            )
            row = cur.fetchone()
            if row:
                return row[0]
            today = date.today()
            six_months = date(today.year + (today.month + 5) // 12, (today.month + 5) % 12 or 12, 1)
            cur.execute(
                """
                INSERT INTO routes (origin, destination, date_from, date_to, priority, enabled)
                VALUES (%s, %s, %s, %s, 1, true)
                RETURNING route_id
                """,
                (origin, dest, today, six_months),
            )
            route_id = cur.fetchone()[0]
        conn.commit()
    return route_id


# ---------------------------------------------------------------------------
# Subscriptions DB helpers
# ---------------------------------------------------------------------------

def _save_subscription(chat_id: int, route_id: int, origin: str, dest: str, alert_price: float) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscriptions SET is_active = FALSE WHERE chat_id = %s AND route_id = %s",
                (chat_id, route_id),
            )
            cur.execute(
                "INSERT INTO subscriptions (chat_id, route_id, origin, dest, alert_price) VALUES (%s, %s, %s, %s, %s)",
                (chat_id, route_id, origin, dest, alert_price),
            )
        conn.commit()


def _load_user_subscriptions(chat_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.route_id, s.origin, s.dest, s.alert_price, s.created_at, r.notes
                FROM subscriptions s JOIN routes r ON r.route_id = s.route_id
                WHERE s.chat_id = %s AND s.is_active = TRUE
                ORDER BY s.created_at DESC
                """,
                (chat_id,),
            )
            rows = cur.fetchall()
    return [{"id": r[0], "route_id": r[1], "origin": r[2], "dest": r[3],
             "alert_price": float(r[4]), "created_at": r[5], "notes": r[6]} for r in rows]


def _deactivate_subscription(sub_id: int, chat_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE subscriptions SET is_active = FALSE WHERE id = %s AND chat_id = %s",
                (sub_id, chat_id),
            )
            affected = cur.rowcount
        conn.commit()
    return affected > 0


def _load_user_stats(chat_id: int) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Всего подписок (включая неактивные) и активных
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_active)        AS active_subs,
                    COUNT(*)                                   AS total_subs,
                    MIN(created_at)                            AS first_sub_at
                FROM subscriptions WHERE chat_id = %s
                """,
                (chat_id,),
            )
            row = cur.fetchone()
            active_subs, total_subs, first_sub_at = row

            # Лучшая (минимальная) цена которую бот нашёл для маршрутов пользователя
            cur.execute(
                """
                SELECT s.origin, s.dest, MIN(fh.price::numeric) AS min_price
                FROM subscriptions s
                JOIN routes r ON r.route_id = s.route_id
                JOIN flights_history fh ON fh.route_id = s.route_id
                WHERE s.chat_id = %s
                GROUP BY s.origin, s.dest
                ORDER BY min_price
                LIMIT 1
                """,
                (chat_id,),
            )
            best = cur.fetchone()

    return {
        "active_subs": int(active_subs or 0),
        "total_subs": int(total_subs or 0),
        "first_sub_at": first_sub_at,
        "best_origin": best[0] if best else None,
        "best_dest": best[1] if best else None,
        "best_price": float(best[2]) if best else None,
    }


# ---------------------------------------------------------------------------
# Travelpayouts search
# ---------------------------------------------------------------------------

def _remap_iata(code: str) -> str:
    from bot.airports import _IATA_REMAP
    return _IATA_REMAP.get(code.upper(), code.upper())


async def _fetch_flights(origin: str, dest: str, month: str) -> list[dict]:
    origin, dest = _remap_iata(origin), _remap_iata(dest)
    params = {
        "origin": origin, "destination": dest,
        "departure_at": month, "currency": "rub",
        "sorting": "price", "direct": "false", "limit": 30, "token": _TP_TOKEN,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(_API_URL, params=params)
            r.raise_for_status()
            return r.json().get("data") or []
    except Exception:
        logger.exception("Travelpayouts request failed %s→%s %s", origin, dest, month)
        return []


async def _fetch_flights_live(origin: str, dest: str, departure_date: str, adults: int = 1) -> list[dict]:
    """Fetch from Google Flights via SerpApi and return Travelpayouts-compatible dicts."""
    origin, dest = _remap_iata(origin), _remap_iata(dest)
    offers = await fetch_serpapi_flights(origin, dest, departure_date, adults=adults)
    return parse_serpapi_offers(offers)


async def _fetch_best_country_route(
    origins: list[str],
    dests: list[str],
    departure_date: str,
    adults: int,
) -> tuple[list[dict], str, str]:
    """Search all origin×dest combos via SerpApi in parallel, return (best_items, best_org, best_dst)."""
    combos = [(o, d) for o in origins for d in dests]
    results = await asyncio.gather(
        *[_fetch_flights_live(o, d, departure_date, adults) for o, d in combos],
        return_exceptions=True,
    )

    best_items: list[dict] = []
    best_org, best_dst = origins[0], dests[0]
    best_price = float("inf")

    for (o, d), items in zip(combos, results):
        if isinstance(items, Exception) or not items:
            continue
        cheapest = min(items, key=lambda x: x["price"])
        if cheapest["price"] < best_price:
            best_price = cheapest["price"]
            best_items = items
            best_org, best_dst = o, d

    return best_items, best_org, best_dst


def _filter_by_dates(items: list[dict], d_from: date, d_to: date) -> list[dict]:
    result = []
    for item in items:
        try:
            dep = datetime.fromisoformat(item.get("departure_at", "")).date()
            if d_from <= dep <= d_to:
                result.append(item)
        except ValueError:
            pass
    return result


def _has_schengen_transit(item: dict) -> bool:
    """Проверяет, есть ли в маршруте пересадка в Шенгенской зоне.

    Аэропорты маршрута закодированы в параметре t= ссылки в виде SGNPEKWAWBGYBEG.
    """
    link = item.get("link", "")
    # Извлекаем строку аэропортов из параметра t= (формат: ...1505SGNPEKWAWBGYBEG_...)
    import re
    m = re.search(r"[A-Z]{3}(?:[A-Z]{3})+", link)
    if not m:
        return False
    route_str = m.group()
    # Все аэропорты кроме первого и последнего — транзитные
    airports = [route_str[i:i+3] for i in range(0, len(route_str), 3)]
    transit = airports[1:-1]
    return any(a in _SCHENGEN_AIRPORTS for a in transit)


_AVIASALES_MARKER = "741011"


def _aviasales_url(origin: str, dest: str, dep_date: date, adults: int, link: str | None = None) -> str:
    import re
    if link:
        base = link if link.startswith("http") else f"https://www.aviasales.ru{link}"
        # Заменяем число пассажиров в конце пути: /search/SGN1007BEG1 → .../BEG2
        base = re.sub(r'([A-Z]{3}\d{4}[A-Z]{3})\d+', rf'\g<1>{adults}', base)
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}marker={_AVIASALES_MARKER}"
    return f"https://www.aviasales.ru/search/{origin}{dep_date.strftime('%d%m')}{dest}{adults}?marker={_AVIASALES_MARKER}"


def _fmt_duration(minutes: int) -> str:
    if not minutes:
        return "?"
    h, m = divmod(minutes, 60)
    return f"{h}ч{m:02d}м"


def _format_results(items: list[dict], origin: str, dest: str, adults: int, label: str, visa_free: bool = True) -> tuple[str, int | None]:
    if visa_free:
        items = [it for it in items if not _has_schengen_transit(it)]
    if not items:
        return f"По маршруту <b>{label}</b> ничего не найдено.", None

    lines = [f"<b>{label}</b> — топ вариантов ({adults} взр.):\n"]
    for i, item in enumerate(items[:5], 1):
        dep = datetime.fromisoformat(item["departure_at"])
        price = item["price"]
        stops = item.get("transfers", 0)
        airline = item.get("airline", "?")
        duration = item.get("duration_to") or item.get("duration") or 0
        stops_str = "прямой" if stops == 0 else f"{stops} пер."
        url = _aviasales_url(origin, dest, dep.date(), adults, item.get("link"))
        lines.append(
            f"{i}. {dep.strftime('%d.%m %H:%M')}  {_fmt_duration(duration)}  {stops_str}  [{airline}]\n"
            f"   {price:,}₽/чел"
            + (f" · <b>{price * adults:,}₽ итого</b>" if adults > 1 else "")
            + f"\n   <a href=\"{url}\">Aviasales</a>\n"
        )

    best = items[0]
    best_price = best["price"]
    best_url = _aviasales_url(origin, dest, datetime.fromisoformat(best["departure_at"]).date(), adults, best.get("link"))
    lines.append(f"\nЛучшая цена: <b>{best_price:,}₽</b>/чел · <a href=\"{best_url}\">открыть</a>")
    return "\n".join(lines), best_price


# ---------------------------------------------------------------------------
# Sparkline / history helpers
# ---------------------------------------------------------------------------

def _sparkline(prices: list[float]) -> str:
    if not prices:
        return ""
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return _SPARKLINE_CHARS[4] * len(prices)
    return "".join(_SPARKLINE_CHARS[int((p - lo) / (hi - lo) * (len(_SPARKLINE_CHARS) - 1))] for p in prices)


def _format_history(data: dict, label: str) -> str:
    daily = data["daily"]
    if not daily:
        return f"<b>{label}</b>\n\nИстория цен ещё не накоплена."

    prices = [d["price"] for d in daily]
    spark = _sparkline(prices)
    current = prices[-1]
    all_time_min = data["all_time_min"]
    all_time_min_at = data["all_time_min_at"]
    min_str = f"{all_time_min:,.0f}₽" if all_time_min else "—"
    min_date = all_time_min_at.strftime("%d.%m") if all_time_min_at else "—"

    week_trend = ""
    if len(prices) >= 7:
        pct = (current - prices[-7]) / prices[-7] * 100
        week_trend = f"\n{'↗' if pct > 0 else '↘'} {abs(pct):.1f}% за 7 дней"

    lines = [
        f"<b>{label}  📊 История цен</b>", "",
        f"<code>{spark}</code>", f"<i>(последние {len(daily)} дн.)</i>", "",
        f"✅ Сейчас:           <b>{current:,.0f}₽</b>",
        f"🏆 Минимум за всё время: <b>{min_str}</b>  ({min_date})" + week_trend,
    ]
    changes = data["changes"]
    if changes:
        lines += ["", "<b>Последние изменения:</b>"]
        for ch in changes:
            delta = ch["new"] - ch["old"]
            pct = delta / ch["old"] * 100
            dt_str = ch["at"].strftime("%d.%m") if ch["at"] else "—"
            lines.append(f"{'▲' if delta > 0 else '▼'} {ch['old']:,.0f}→{ch['new']:,.0f}₽  ({pct:+.0f}%)   {dt_str}")

    return "\n".join(lines)


def _result_keyboard(rid: str, org: str, dst: str, best_price: int, adults: str = "1", visa_free: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура под результатами поиска: «Следить», «Назад» и опционально «График»."""
    watch_btn = InlineKeyboardButton(
        f"🔔 Следить ({best_price:,}₽)",
        callback_data=f"{_CB_WATCH}:{rid}:{org}:{dst}:{best_price}",
    )
    back_btn = InlineKeyboardButton(
        "← Назад к маршрутам",
        callback_data=f"{_CB_BACK_ROUTES}:{adults}:{int(visa_free)}",
    )
    rows = [[watch_btn], [back_btn]]
    if _MINIAPP_URL:
        url = _MINIAPP_URL.rstrip("/") + f"/?origin={org}&dest={dst}"
        rows.append([InlineKeyboardButton("📊 График цен", web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(rows)


def _progress_bar(step: int, total: int = 5) -> str:
    filled = int(step / total * 10)
    return "█" * filled + "░" * (10 - filled)


# ---------------------------------------------------------------------------
# Search filters
# ---------------------------------------------------------------------------

def _default_filters() -> dict:
    return {
        "visa_free_pref": True,
        "stops": "any",        # "any" | "0" | "1"
        "dep_morning": True,   # вылет 6–12
        "dep_day": True,       # вылет 12–18
        "dep_evening": True,   # вылет 18–24
        "dep_night": True,     # вылет 0–6
        "max_duration": 0,     # 0 = без ограничения, иначе в минутах
        "no_night_layover": False,
    }


def _get_filters(user_data: dict) -> dict:
    base = _default_filters()
    base.update(user_data.get("filters", {}))
    return base


def _filters_active(f: dict) -> bool:
    return any(f.get(k) != v for k, v in _default_filters().items())


def _apply_search_filters(items: list[dict], f: dict) -> list[dict]:
    from datetime import timedelta as _td

    result = items

    stops_val = f.get("stops", "any")
    if stops_val == "0":
        result = [i for i in result if i.get("transfers", 0) == 0]
    elif stops_val == "1":
        result = [i for i in result if i.get("transfers", 0) <= 1]

    dep_slots = [
        ("dep_night",    0,  6),
        ("dep_morning",  6, 12),
        ("dep_day",     12, 18),
        ("dep_evening", 18, 24),
    ]
    if not all(f.get(k, True) for k, _, _ in dep_slots):
        def dep_ok(item: dict) -> bool:
            try:
                h = datetime.fromisoformat(item["departure_at"]).hour
                return any(f.get(k, True) and s <= h < e for k, s, e in dep_slots)
            except Exception:
                return True
        result = [i for i in result if dep_ok(i)]

    max_dur = f.get("max_duration", 0)
    if max_dur:
        result = [i for i in result if (i.get("duration_to") or i.get("duration") or 0) <= max_dur]

    if f.get("no_night_layover"):
        def has_night_lay(item: dict) -> bool:
            if not item.get("transfers", 0):
                return False
            try:
                dep = datetime.fromisoformat(item["departure_at"])
                dur = item.get("duration_to") or item.get("duration") or 0
                mid = dep + _td(minutes=dur // 2)
                return mid.hour >= 22 or mid.hour < 6
            except Exception:
                return False
        result = [i for i in result if not has_night_lay(i)]

    return result


def _build_filter_keyboard(f: dict) -> InlineKeyboardMarkup:
    def chk(cond: bool) -> str:
        return "✓ " if cond else ""

    stops = f.get("stops", "any")
    max_dur = f.get("max_duration", 0)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{chk(f.get('visa_free_pref', True))}Без визы (без Шенгена)",
                callback_data=f"{_CB_FILTER_TOG}:visa_free_pref:{int(not f.get('visa_free_pref', True))}",
            ),
        ],
        [
            InlineKeyboardButton(f"{chk(stops == 'any')}Любые", callback_data=f"{_CB_FILTER_TOG}:stops:any"),
            InlineKeyboardButton(f"{chk(stops == '0')}Прямые", callback_data=f"{_CB_FILTER_TOG}:stops:0"),
            InlineKeyboardButton(f"{chk(stops == '1')}≤1 пер.", callback_data=f"{_CB_FILTER_TOG}:stops:1"),
        ],
        [
            InlineKeyboardButton(f"{chk(f.get('dep_morning', True))}Утро 6–12", callback_data=f"{_CB_FILTER_TOG}:dep_morning:{int(not f.get('dep_morning', True))}"),
            InlineKeyboardButton(f"{chk(f.get('dep_day', True))}День 12–18", callback_data=f"{_CB_FILTER_TOG}:dep_day:{int(not f.get('dep_day', True))}"),
        ],
        [
            InlineKeyboardButton(f"{chk(f.get('dep_evening', True))}Вечер 18–24", callback_data=f"{_CB_FILTER_TOG}:dep_evening:{int(not f.get('dep_evening', True))}"),
            InlineKeyboardButton(f"{chk(f.get('dep_night', True))}Ночь 0–6", callback_data=f"{_CB_FILTER_TOG}:dep_night:{int(not f.get('dep_night', True))}"),
        ],
        [
            InlineKeyboardButton(f"{chk(max_dur == 0)}Любое время в пути", callback_data=f"{_CB_FILTER_TOG}:max_duration:0"),
            InlineKeyboardButton(f"{chk(max_dur == 480)}≤8ч", callback_data=f"{_CB_FILTER_TOG}:max_duration:480"),
            InlineKeyboardButton(f"{chk(max_dur == 900)}≤15ч", callback_data=f"{_CB_FILTER_TOG}:max_duration:900"),
        ],
        [
            InlineKeyboardButton(
                f"{chk(f.get('no_night_layover', False))}Без ночных пересадок ~",
                callback_data=f"{_CB_FILTER_TOG}:no_night_layover:{int(not f.get('no_night_layover', False))}",
            ),
        ],
        [InlineKeyboardButton("← Готово", callback_data=_CB_FILTER_DONE)],
    ])


# ---------------------------------------------------------------------------
# Shared: show calendar for a route
# ---------------------------------------------------------------------------

def _first_available_month() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


async def _show_calendar_from(query, rid: str, org: str, dst: str, adt: str) -> None:
    y, m = _first_available_month()
    kb = _build_calendar(y, m, "f", rid, org, dst, adt)
    await query.edit_message_text(
        f"<b>{org} → {dst}</b>  —  выберите дату вылета (от):",
        reply_markup=kb, parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я помогу найти дешёвые авиабилеты.\n\n"
        "Используй кнопки ниже или команды:\n"
        "/search — поиск билетов\n"
        "/history — история цен\n"
        "/help — справка",
        parse_mode=ParseMode.HTML,
        reply_markup=_MAIN_KEYBOARD,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Как пользоваться:</b>\n\n"
        "1. «🔍 Поиск» → число пассажиров → маршрут → даты в календаре\n"
        "2. «✈️ Другой маршрут» — ввести любой город или страну:\n"
        "   <code>HAN BKK</code>  · <code>Ханой Бангкок</code>  · <code>Вьетнам Сербия</code>\n"
        "   При вводе страны бот сравнит все аэропорты и покажет лучший вариант\n"
        "3. Фильтр «Без визы» — убирает маршруты с шенгенскими пересадками\n"
        "4. «🔔 Следить» — уведомление при изменении цены\n"
        "5. «📊 История цен» — динамика за 30 дней\n"
        "6. /unwatch — управление подписками · /mystats — статистика\n\n"
        "<i>Основные данные: Travelpayouts (Aviasales). "
        "Редкие маршруты ищутся через Google Flights.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_MAIN_KEYBOARD,
    )


def _pax_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("1 чел.", callback_data=f"{_CB_PAX}:1"),
        InlineKeyboardButton("2 чел.", callback_data=f"{_CB_PAX}:2"),
        InlineKeyboardButton("3 чел.", callback_data=f"{_CB_PAX}:3"),
        InlineKeyboardButton("4 чел.", callback_data=f"{_CB_PAX}:4"),
    ]])


async def _show_pax_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Сколько пассажиров?", reply_markup=_pax_keyboard())


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_pax_selection(update, context)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.delete()
    await update.message.chat.send_message(
        "🧹 Чат очищен.\n\nДля нового поиска нажмите кнопку ниже.",
        reply_markup=_MAIN_KEYBOARD,
    )


async def _show_history_routes(update: Update) -> None:
    try:
        routes = _load_enabled_routes()
    except Exception:
        logger.exception("Failed to load routes")
        await update.message.reply_text("Не удалось загрузить маршруты: база данных недоступна.")
        return
    if not routes:
        await update.message.reply_text("В базе нет активных маршрутов.")
        return
    buttons = []
    for r in routes:
        label = r["notes"] or route_label(r['origin'], r['destination'])
        buttons.append([InlineKeyboardButton(label, callback_data=f"{_CB_HIST}:{r['route_id']}:{r['origin']}:{r['destination']}")])
    await update.message.reply_text("Выберите маршрут:", reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_history_routes(update)


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_user.id
    try:
        subs = _load_user_subscriptions(chat_id)
    except Exception:
        await update.message.reply_text("Не удалось загрузить подписки.")
        return
    if not subs:
        await update.message.reply_text("У вас нет активных подписок.")
        return
    buttons = []
    for s in subs:
        label = s["notes"] or route_label(s['origin'], s['dest'])
        buttons.append([InlineKeyboardButton(f"❌ {label} ({s['alert_price']:,.0f}₽)", callback_data=f"{_CB_UNWATCH}:{s['id']}")])
    await update.message.reply_text("Ваши подписки. Нажмите ❌ чтобы отменить:", reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_delroute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT route_id, origin, destination, notes FROM routes ORDER BY route_id")
                rows = cur.fetchall()
    except Exception:
        await update.message.reply_text("Не удалось загрузить маршруты.")
        return
    if not rows:
        await update.message.reply_text("Маршрутов в базе нет.")
        return
    buttons = []
    for route_id, origin, dest, notes in rows:
        label = notes or route_label(origin, dest)
        buttons.append([InlineKeyboardButton(f"🗑 {label}", callback_data=f"{_CB_DEL_ROUTE}:{route_id}")])
    await update.message.reply_text("Выберите маршрут для удаления:", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_del_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    route_id = int(query.data.split(":")[1])
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT origin, destination, notes FROM routes WHERE route_id = %s", (route_id,))
                row = cur.fetchone()
    except Exception:
        await query.edit_message_text("Ошибка при загрузке маршрута.")
        return
    if not row:
        await query.edit_message_text("Маршрут не найден.")
        return
    origin, dest, notes = row
    label = notes or route_label(origin, dest)
    buttons = [[
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"{_CB_DEL_CONF}:{route_id}"),
        InlineKeyboardButton("❌ Отмена", callback_data="noop"),
    ]]
    await query.edit_message_text(
        f"Удалить маршрут <b>{label}</b>?\nВсе подписки и история цен тоже удалятся.",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )


async def cb_del_route_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    route_id = int(query.data.split(":")[1])
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT origin, destination, notes FROM routes WHERE route_id = %s", (route_id,))
                row = cur.fetchone()
                if not row:
                    await query.edit_message_text("Маршрут не найден.")
                    return
                origin, dest, notes = row
                cur.execute("DELETE FROM routes WHERE route_id = %s", (route_id,))
            conn.commit()
    except Exception:
        logger.exception("Failed to delete route %s", route_id)
        await query.edit_message_text("Ошибка при удалении.")
        return
    label = notes or route_label(origin, dest)
    last = context.user_data.get("last_route_list", {})
    adults = last.get("adults", "1")
    visa_free = last.get("visa_free", True)
    try:
        routes = _load_enabled_routes(visa_free_only=visa_free)
    except Exception:
        await query.edit_message_text(f"Маршрут <b>{label}</b> удалён.", parse_mode=ParseMode.HTML)
        return
    visa_label = "без визы" if visa_free else "все маршруты"
    await query.edit_message_text(
        f"Маршрут <b>{label}</b> удалён.\n\nВыберите маршрут ({adults} взр., {visa_label}):",
        reply_markup=_build_route_list_keyboard(routes, adults, context.user_data),
        parse_mode=ParseMode.HTML,
    )


async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_user.id
    try:
        stats = _load_user_stats(chat_id)
    except Exception:
        logger.exception("Failed to load stats for chat_id=%s", chat_id)
        await update.message.reply_text("Не удалось загрузить статистику.")
        return

    if stats["total_subs"] == 0:
        await update.message.reply_text(
            "Статистики пока нет.\n\nНачните с /search — найдите маршрут и нажмите «🔔 Следить»."
        )
        return

    lines = ["<b>📈 Ваша статистика</b>\n"]

    lines.append(f"Активных подписок: <b>{stats['active_subs']}</b>")
    if stats["total_subs"] > stats["active_subs"]:
        lines.append(f"Всего подписок за всё время: {stats['total_subs']}")

    if stats["first_sub_at"]:
        lines.append(f"Первая подписка: {stats['first_sub_at'].strftime('%d.%m.%Y')}")

    if stats["best_price"] is not None:
        label = route_label(stats["best_origin"], stats["best_dest"])
        lines.append(f"\nЛучшая найденная цена:\n<b>{stats['best_price']:,.0f}₽</b> — {label}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == _MENU_SEARCH:
        await _show_pax_selection(update, context)
    elif text == _MENU_HISTORY:
        await _show_history_routes(update)
    elif text == _MENU_HELP:
        await cmd_help(update, context)


def _city_suggest_keyboard(query: str, adults: str, step: str) -> InlineKeyboardMarkup | None:
    """Построить клавиатуру с подсказками городов по частичному вводу."""
    suggestions = search_cities(query)
    if not suggestions:
        return None
    buttons = [
        [InlineKeyboardButton(f"{name} ({iata})", callback_data=f"{_CB_CITY_PICK}:{adults}:{step}:{iata}")]
        for iata, name in suggestions
    ]
    return InlineKeyboardMarkup(buttons)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-form route input with city suggestions."""
    text = update.message.text.strip()

    # Шаг 2: ждём город назначения
    dest_state = context.user_data.get(_STATE_AWAITING_DEST)
    if dest_state:
        from bot.airports import resolve_city
        dest = resolve_city(text)
        if dest:
            origin = dest_state["origin"]
            adults = str(dest_state["adults"])
            context.user_data.pop(_STATE_AWAITING_DEST, None)
            await _open_calendar_for_route(update.message, origin, dest, adults)
        else:
            kb = _city_suggest_keyboard(text, str(dest_state["adults"]), "dest")
            if kb:
                await update.message.reply_text(
                    f"Куда летим? Выберите или уточните:",
                    reply_markup=kb,
                )
            else:
                await update.message.reply_text(
                    "Не распознал город назначения. Попробуйте ещё раз:\n"
                    "<code>BKK</code>  или  <code>Бангкок</code>",
                    parse_mode=ParseMode.HTML,
                )
        return

    # Шаг 1: ждём маршрут (оба города сразу или только первый)
    state = context.user_data.get(_STATE_AWAITING_ROUTE)
    if not state:
        return

    adults = str(state["adults"])

    # Попробовать распознать сразу два города или страны
    extended = parse_route_with_countries(text)
    if extended:
        origins, dests = extended
        context.user_data.pop(_STATE_AWAITING_ROUTE, None)
        display_label = None
        if len(origins) > 1 or len(dests) > 1:
            context.user_data["country_search"] = {"origins": origins, "destinations": dests}
            parts_raw = text.strip().split()
            if len(parts_raw) == 2:
                display_label = f"{parts_raw[0].capitalize()} → {parts_raw[1].capitalize()}  (лучший из {len(origins) * len(dests)} маршрутов)"
        await _open_calendar_for_route(update.message, origins[0], dests[0], adults, display_label)
        return

    # Один токен — возможно пользователь вводит только город отправления
    parts = text.split()
    if len(parts) == 1:
        from bot.airports import resolve_city
        origin = resolve_city(text)
        if origin:
            context.user_data.pop(_STATE_AWAITING_ROUTE, None)
            context.user_data[_STATE_AWAITING_DEST] = {"adults": state["adults"], "origin": origin}
            kb = _city_suggest_keyboard("", adults, "dest")
            await update.message.reply_text(
                f"Откуда: <b>{route_label(origin, '???').split(' →')[0]}</b>\n\nТеперь введите город назначения:",
                parse_mode=ParseMode.HTML,
            )
            return

    # Не распознали — показать подсказки если есть совпадения
    kb = _city_suggest_keyboard(text, adults, "origin")
    if kb:
        await update.message.reply_text("Уточните город отправления:", reply_markup=kb)
    else:
        await update.message.reply_text(
            "Не удалось распознать маршрут.\n\n"
            "Введите два города или страны через пробел:\n\n"
            "<code>HAN BKK</code>  — коды IATA\n"
            "<code>Ханой Бангкок</code>  — по-русски\n"
            "<code>Hanoi Bangkok</code>  — по-английски\n"
            "<code>Вьетнам Сербия</code>  — поиск по всем аэропортам страны",
            parse_mode=ParseMode.HTML,
        )


async def _open_calendar_for_route(message, origin: str, dest: str, adults: str, display_label: str | None = None) -> None:
    """Создать маршрут в БД и открыть календарь."""
    try:
        route_id = str(_ensure_route(origin, dest))
    except Exception:
        logger.exception("Failed to ensure route %s→%s", origin, dest)
        await message.reply_text("Не удалось создать маршрут.")
        return

    label = display_label or route_label(origin, dest)
    y, m = _first_available_month()
    kb = _build_calendar(y, m, "f", route_id, origin, dest, adults)
    await message.reply_text(
        f"<b>{label}</b>  —  выберите дату вылета (от):",
        reply_markup=kb, parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

async def cb_vf_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    visa_free = bool(int(query.data.split(":")[1]))
    context.user_data["visa_free_pref"] = visa_free
    await query.edit_message_text("Сколько пассажиров?", reply_markup=_pax_keyboard(visa_free))


def _build_route_list_keyboard(routes: list[dict], adults: str, user_data: dict | None = None) -> InlineKeyboardMarkup:
    buttons = []
    for r in routes:
        label = r["notes"] or route_label(r['origin'], r['destination'])
        cb = f"{_CB_ROUTE}:{r['route_id']}:{r['origin']}:{r['destination']}:{r['date_from']}:{r['date_to']}:{adults}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=cb),
            InlineKeyboardButton("🗑", callback_data=f"{_CB_DEL_ROUTE}:{r['route_id']}"),
        ])
    buttons.append([InlineKeyboardButton("✈️ Другой маршрут", callback_data=f"{_CB_CUSTOM}:{adults}")])
    f = _get_filters(user_data or {})
    filter_label = "⚙️ Фильтры •" if _filters_active(f) else "⚙️ Фильтры"
    buttons.append([InlineKeyboardButton(filter_label, callback_data=_CB_FILTER_OPEN)])
    return InlineKeyboardMarkup(buttons)


async def cb_pax(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    adults = parts[1]
    visa_free = _get_filters(context.user_data).get("visa_free_pref", True)
    context.user_data["last_route_list"] = {"adults": adults, "visa_free": visa_free}

    try:
        routes = _load_enabled_routes(visa_free_only=visa_free)
    except Exception:
        await query.edit_message_text("Не удалось загрузить маршруты.")
        return

    visa_label = "без визы" if visa_free else "все маршруты"
    await query.edit_message_text(
        f"Выберите маршрут ({adults} взр., {visa_label}):",
        reply_markup=_build_route_list_keyboard(routes, adults, context.user_data),
    )


async def cb_custom_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    adults = int(query.data.split(":")[1])
    context.user_data[_STATE_AWAITING_ROUTE] = {"adults": adults}
    await query.edit_message_text(
        "Введите два города или страны через пробел:\n\n"
        "<code>HAN BKK</code>  — коды IATA\n"
        "<code>Ханой Бангкок</code>  — по-русски\n"
        "<code>Hanoi Bangkok</code>  — по-английски\n"
        "<code>Вьетнам Сербия</code>  — поиск по всем аэропортам страны",
        parse_mode=ParseMode.HTML,
    )


async def cb_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route selected → show calendar for from-date."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 7:
        await query.edit_message_text("Неверный формат запроса.")
        return

    _, rid, org, dst, _df, _dt, adt = parts
    await _show_calendar_from(query, rid, org, dst, adt)


async def cb_cal_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calendar navigation: prev/next month."""
    query = update.callback_query
    await query.answer()

    # cn:{rid}:{org}:{dst}:{adt}:{step}:{from}:{y}:{m}
    parts = query.data.split(":")
    _, rid, org, dst, adt, step, from_date, y, m = parts
    kb = _build_calendar(int(y), int(m), step, rid, org, dst, adt, from_date)

    prompt = (f"<b>{org} → {dst}</b>  —  выберите дату вылета ({'от' if step == 'f' else 'до'}):")
    await query.edit_message_text(prompt, reply_markup=kb, parse_mode=ParseMode.HTML)


async def cb_cal_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Calendar day selected."""
    query = update.callback_query
    await query.answer()

    # cd:{rid}:{org}:{dst}:{adt}:{step}:{from}:{y}:{m}:{d}
    parts = query.data.split(":")
    _, rid, org, dst, adt, step, from_date, y, m, d = parts
    selected = date(int(y), int(m), int(d))

    if step == "f":
        # From-date chosen → show calendar for to-date, same month
        kb = _build_calendar(int(y), int(m), "t", rid, org, dst, adt, str(selected))
        await query.edit_message_text(
            f"<b>{org} → {dst}</b>  от <b>{selected.strftime('%d.%m.%Y')}</b>\n"
            "Выберите дату возвращения (до):",
            reply_markup=kb, parse_mode=ParseMode.HTML,
        )
    else:
        # To-date chosen → search
        d_from = date.fromisoformat(from_date)
        d_to = selected
        adults = int(adt)

        country_search = context.user_data.pop("country_search", None)

        if country_search:
            origins = country_search["origins"]
            destinations = country_search["destinations"]
            await query.edit_message_text(
                f"Ищу лучший рейс по {len(origins) * len(destinations)} маршрутам через Google Flights…"
            )
            filtered, org, dst = await _fetch_best_country_route(
                origins, destinations, d_from.isoformat(), adults
            )
            filtered = _filter_by_dates(filtered, d_from, d_to)
            filtered.sort(key=lambda x: x["price"])
            label = f"{org} → {dst}  {d_from.strftime('%d.%m')}–{d_to.strftime('%d.%m.%Y')}  [Google Flights live]"
        else:
            label = f"{org} → {dst}  {d_from.strftime('%d.%m')}–{d_to.strftime('%d.%m.%Y')}"
            await query.edit_message_text(f"Ищу рейсы {org} → {dst}…")

            months = set()
            cur = d_from.replace(day=1)
            while cur <= d_to:
                months.add(cur.strftime("%Y-%m"))
                cur = cur.replace(month=cur.month + 1) if cur.month < 12 else cur.replace(year=cur.year + 1, month=1)

            all_items: list[dict] = []
            for month in sorted(months):
                all_items.extend(await _fetch_flights(org, dst, month))

            filtered = _filter_by_dates(all_items, d_from, d_to)
            filtered.sort(key=lambda x: x["price"])

            if not filtered:
                await query.edit_message_text(f"Ищу рейсы {org} → {dst} через Google Flights…")
                live_items = await _fetch_flights_live(org, dst, d_from.isoformat(), adults)
                live_filtered = _filter_by_dates(live_items, d_from, d_to)
                live_filtered.sort(key=lambda x: x["price"])
                if live_filtered:
                    filtered = live_filtered
                    label += "  [Google Flights live]"

        filtered = _apply_search_filters(filtered, _get_filters(context.user_data))
        visa_free_pref = context.user_data.get("visa_free_pref", True)
        text, best_price = _format_results(filtered, org, dst, adults, label, visa_free=visa_free_pref)

        last = context.user_data.get("last_route_list", {})
        vf = last.get("visa_free", True)
        if best_price is not None:
            keyboard = _result_keyboard(rid, org, dst, best_price, adults=last.get("adults", adt), visa_free=vf)
        else:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "← К маршрутам", callback_data=f"{_CB_BACK_ROUTES}:{last.get('adults', adt)}:{int(vf)}"
            )]])
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            reply_markup=keyboard,
        )


async def cb_city_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a city suggestion button."""
    query = update.callback_query
    await query.answer()

    # cp:{adults}:{step}:{iata}
    _, adults, step, iata = query.data.split(":")

    if step == "origin":
        # Выбрали город отправления — ждём назначение
        context.user_data.pop(_STATE_AWAITING_ROUTE, None)
        context.user_data[_STATE_AWAITING_DEST] = {"adults": int(adults), "origin": iata}
        city_name = route_label(iata, "???").split(" →")[0]
        await query.edit_message_text(
            f"Откуда: <b>{city_name}</b>\n\nТеперь введите город назначения:",
            parse_mode=ParseMode.HTML,
        )
    else:
        # Выбрали город назначения
        dest_state = context.user_data.get(_STATE_AWAITING_DEST)
        if not dest_state:
            await query.edit_message_text("Сессия устарела, начните поиск заново.")
            return
        origin = dest_state["origin"]
        context.user_data.pop(_STATE_AWAITING_DEST, None)

        try:
            route_id = str(_ensure_route(origin, iata))
        except Exception:
            logger.exception("Failed to ensure route %s→%s", origin, iata)
            await query.edit_message_text("Не удалось создать маршрут.")
            return

        label = route_label(origin, iata)
        y, m = _first_available_month()
        kb = _build_calendar(y, m, "f", route_id, origin, iata, adults)
        await query.edit_message_text(
            f"<b>{label}</b>  —  выберите дату вылета (от):",
            reply_markup=kb, parse_mode=ParseMode.HTML,
        )


async def cb_cheapest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cheapest-in-month search: find top-5 cheapest days for the selected month."""
    query = update.callback_query
    await query.answer()

    # cheap:{rid}:{org}:{dst}:{adt}:{year}:{month}  (visa_free опционально в конце)
    parts = query.data.split(":")
    _, rid, org, dst, adt, y, m = parts[:7]
    show_all = len(parts) > 7 and parts[7] == "all"
    adults = int(adt)
    year, month = int(y), int(m)
    month_str = f"{year}-{month:02d}"
    month_label = f"{_MONTHS_RU[month]} {year}"

    await query.edit_message_text(
        f"Ищу самые дешёвые рейсы {org} → {dst} за {month_label}…",
        parse_mode=ParseMode.HTML,
    )

    items = await _fetch_flights(org, dst, month_str)
    is_live = False
    if not items:
        await query.edit_message_text(
            f"Ищу рейсы {org} → {dst} за {month_label} через Google Flights…",
            parse_mode=ParseMode.HTML,
        )
        import calendar as _cal
        today = date.today()
        last_day = _cal.monthrange(year, month)[1]
        sample_dates = [
            date(year, month, min(d, last_day)).isoformat()
            for d in (1, 8, 15, 22)
            if date(year, month, min(d, last_day)) >= today
        ]
        live_results = await asyncio.gather(
            *[_fetch_flights_live(org, dst, d, adults) for d in sample_dates],
            return_exceptions=True,
        )
        for r in live_results:
            if isinstance(r, list):
                items.extend(r)
        is_live = bool(items)

    if not items:
        last = context.user_data.get("last_route_list", {})
        vf = last.get("visa_free", True)
        await query.edit_message_text(
            f"По маршруту <b>{org} → {dst}</b> за {month_label} ничего не найдено.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "← К маршрутам", callback_data=f"{_CB_BACK_ROUTES}:{adt}:{int(vf)}"
            )]]),
        )
        return

    apply_vf = context.user_data.get("visa_free_pref", True) and not show_all
    if apply_vf:
        filtered = [it for it in items if not _has_schengen_transit(it)]
    else:
        filtered = items
    filtered.sort(key=lambda x: x["price"])
    filtered = _apply_search_filters(filtered, _get_filters(context.user_data))
    top5 = filtered[:5]

    if not top5:
        show_all_cb = f"{_CB_CHEAPEST}:{rid}:{org}:{dst}:{adt}:{y}:{m}:all"
        await query.edit_message_text(
            f"По маршруту <b>{org} → {dst}</b> за {month_label} нет рейсов без Шенген-пересадок.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌍 Показать все (включая Шенген)", callback_data=show_all_cb),
            ]]),
        )
        return

    label = route_label(org, dst) + ("  [Google Flights live]" if is_live else "")
    lines = [f"<b>{label}</b> — топ дешёвых дат за {month_label} ({adults} взр.):\n"]
    for i, item in enumerate(top5, 1):
        dep = datetime.fromisoformat(item["departure_at"])
        price = item["price"]
        stops = item.get("transfers", 0)
        airline = item.get("airline", "?")
        duration = item.get("duration_to") or item.get("duration") or 0
        stops_str = "прямой" if stops == 0 else f"{stops} пер."
        url = _aviasales_url(org, dst, dep.date(), adults, item.get("link"))
        lines.append(
            f"{i}. <b>{dep.strftime('%d %b').lower()}</b>  {_fmt_duration(duration)}  {stops_str}  [{airline}]\n"
            f"   {price:,}₽/чел"
            + (f" · <b>{price * adults:,}₽ итого</b>" if adults > 1 else "")
            + f"\n   <a href=\"{url}\">Aviasales</a>\n"
        )

    best_price = top5[0]["price"]
    lines.append(f"\nЛучшая цена в месяце: <b>{best_price:,}₽</b>/чел")

    last = context.user_data.get("last_route_list", {})
    keyboard_rows = list(_result_keyboard(rid, org, dst, int(best_price), adults=last.get("adults", adt), visa_free=last.get("visa_free", True)).inline_keyboard)
    # кнопка переключения на следующий месяц
    if month < 12:
        next_y, next_m = year, month + 1
    else:
        next_y, next_m = year + 1, 1
    keyboard_rows.append([InlineKeyboardButton(
        f"➡️ {_MONTHS_RU[next_m]} {next_y}",
        callback_data=f"{_CB_CHEAPEST}:{rid}:{org}:{dst}:{adt}:{next_y}:{next_m}",
    )])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def cb_oneway(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-way search: no return date, search the month of from_date."""
    query = update.callback_query
    await query.answer()

    # ow:{rid}:{org}:{dst}:{adt}:{from_date}
    parts = query.data.split(":")
    _, rid, org, dst, adt, from_date = parts
    adults = int(adt)
    d_from = date.fromisoformat(from_date)
    label = f"{org} → {dst}  от {d_from.strftime('%d.%m.%Y')}  (в одну сторону)"

    await query.edit_message_text(f"Ищу рейсы {org} → {dst}…")

    items = await _fetch_flights(org, dst, d_from.strftime("%Y-%m"))
    # Show flights from selected date onward within the month
    items = [i for i in items if datetime.fromisoformat(i.get("departure_at", "")).date() >= d_from]
    items.sort(key=lambda x: x["price"])
    items = _apply_search_filters(items, _get_filters(context.user_data))

    text, best_price = _format_results(items, org, dst, adults, label)

    last = context.user_data.get("last_route_list", {})
    vf = last.get("visa_free", True)
    if best_price is not None:
        keyboard = _result_keyboard(rid, org, dst, best_price, adults=last.get("adults", adt), visa_free=vf)
    else:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К маршрутам", callback_data=f"{_CB_BACK_ROUTES}:{last.get('adults', adt)}:{int(vf)}"
        )]])
    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        reply_markup=keyboard,
    )


async def cb_hist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    _, route_id, origin, dest = parts
    label = f"{origin} → {dest}"

    for step in range(1, 5):
        bar = "█" * int(step / 5 * 10) + "░" * (10 - int(step / 5 * 10))
        await query.edit_message_text(f"Загружаю историю {label}…\n\n<code>{bar}</code>", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.4)

    try:
        data = _load_price_history(int(route_id))
    except Exception:
        logger.exception("Failed to load price history route_id=%s", route_id)
        await query.edit_message_text("Не удалось загрузить историю цен.")
        return

    text = _format_history(data, label)

    keyboard = None
    daily = data.get("daily", [])
    if daily:
        current_price = int(daily[-1]["price"])
        last = context.user_data.get("last_route_list", {})
        keyboard = _result_keyboard(route_id, origin, dest, current_price, adults=last.get("adults", "1"), visa_free=last.get("visa_free", True))

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cb_back_routes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуться к списку маршрутов."""
    query = update.callback_query
    await query.answer()
    _, adults, visa_free_str = query.data.split(":")
    visa_free = bool(int(visa_free_str))
    context.user_data["last_route_list"] = {"adults": adults, "visa_free": visa_free}
    try:
        routes = _load_enabled_routes(visa_free_only=visa_free)
    except Exception:
        await query.edit_message_text("Не удалось загрузить маршруты.")
        return
    visa_label = "без визы" if visa_free else "все маршруты"
    await query.edit_message_text(
        f"Выберите маршрут ({adults} взр., {visa_label}):",
        reply_markup=_build_route_list_keyboard(routes, adults, context.user_data),
    )


async def cb_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    _, route_id, origin, dest, price_str = parts
    chat_id = query.from_user.id
    alert_price = float(price_str)

    try:
        _save_subscription(chat_id, int(route_id), origin, dest, alert_price)
    except Exception:
        logger.exception("Failed to save subscription")
        await query.answer("Не удалось сохранить подписку.", show_alert=True)
        return

    await query.answer(f"Подписка оформлена! Уведомлю при изменении цены {origin} → {dest}.", show_alert=True)
    new_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Следим ({alert_price:,.0f}₽) — /unwatch чтобы отменить", callback_data="noop")
    ]])
    try:
        await query.edit_message_reply_markup(reply_markup=new_kb)
    except Exception:
        pass


async def cb_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    sub_id = int(query.data.split(":")[1])
    ok = _deactivate_subscription(sub_id, query.from_user.id)
    await query.edit_message_text("Подписка отменена." if ok else "Подписка не найдена.")


# ---------------------------------------------------------------------------
# Filter handlers
# ---------------------------------------------------------------------------

async def cb_filter_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    f = _get_filters(context.user_data)
    await query.edit_message_text(
        "⚙️ <b>Фильтры поиска</b>\n\n"
        "<b>Пересадки</b> · <b>Время вылета</b> · <b>Время в пути</b>\n\n"
        "<i>~ — приблизительный фильтр, работает не для всех рейсов</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_build_filter_keyboard(f),
    )


async def cb_filter_tog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, key, raw_value = query.data.split(":", 2)
    f = _get_filters(context.user_data)
    if key in ("stops",):
        f[key] = raw_value
    elif key == "max_duration":
        f[key] = int(raw_value)
    else:
        f[key] = bool(int(raw_value))
    context.user_data["filters"] = f
    if key == "visa_free_pref":
        context.user_data["visa_free_pref"] = f["visa_free_pref"]
        if "last_route_list" in context.user_data:
            context.user_data["last_route_list"]["visa_free"] = f["visa_free_pref"]
    await query.edit_message_reply_markup(reply_markup=_build_filter_keyboard(f))


async def cb_filter_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    last = context.user_data.get("last_route_list", {"adults": "1", "visa_free": True})
    adults = last.get("adults", "1")
    visa_free = last.get("visa_free", True)
    try:
        routes = _load_enabled_routes(visa_free_only=visa_free)
    except Exception:
        await query.edit_message_text("Не удалось загрузить маршруты.")
        return
    visa_label = "без визы" if visa_free else "все маршруты"
    await query.edit_message_text(
        f"Выберите маршрут ({adults} взр., {visa_label}):",
        reply_markup=_build_route_list_keyboard(routes, adults, context.user_data),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("search",   "Поиск билетов"),
        BotCommand("history",  "История цен"),
        BotCommand("mystats",  "Моя статистика"),
        BotCommand("unwatch",  "Мои подписки / отменить алёрт"),
        BotCommand("help",     "Справка"),
    ])


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "your_bot_token_here":
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("unwatch",  cmd_unwatch))
    app.add_handler(CommandHandler("mystats",  cmd_mystats))
    app.add_handler(CommandHandler("delroute", cmd_delroute))
    app.add_handler(CommandHandler("clear",    cmd_clear))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f"^({_MENU_SEARCH}|{_MENU_HISTORY}|{_MENU_HELP})$"),
        handle_menu_button,
    ))
    # Free-form route input — lower priority than menu buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(cb_vf_toggle,    pattern=rf"^{_CB_VF_TOGGLE}:"))
    app.add_handler(CallbackQueryHandler(cb_pax,          pattern=rf"^{_CB_PAX}:"))
    app.add_handler(CallbackQueryHandler(cb_custom_route, pattern=rf"^{_CB_CUSTOM}:"))
    app.add_handler(CallbackQueryHandler(cb_route,        pattern=rf"^{_CB_ROUTE}:"))
    app.add_handler(CallbackQueryHandler(cb_cal_nav,      pattern=rf"^{_CB_CAL_NAV}:"))
    app.add_handler(CallbackQueryHandler(cb_cal_day,      pattern=rf"^{_CB_CAL_DAY}:"))
    app.add_handler(CallbackQueryHandler(cb_city_pick,     pattern=rf"^{_CB_CITY_PICK}:"))
    app.add_handler(CallbackQueryHandler(cb_cheapest,      pattern=rf"^{_CB_CHEAPEST}:"))
    app.add_handler(CallbackQueryHandler(cb_oneway,       pattern=rf"^{_CB_ONEWAY}:"))
    app.add_handler(CallbackQueryHandler(cb_hist,         pattern=rf"^{_CB_HIST}:"))
    app.add_handler(CallbackQueryHandler(cb_watch,            pattern=rf"^{_CB_WATCH}:"))
    app.add_handler(CallbackQueryHandler(cb_unwatch,          pattern=rf"^{_CB_UNWATCH}:"))
    app.add_handler(CallbackQueryHandler(cb_del_route,        pattern=rf"^{_CB_DEL_ROUTE}:"))
    app.add_handler(CallbackQueryHandler(cb_del_route_confirm, pattern=rf"^{_CB_DEL_CONF}:"))
    app.add_handler(CallbackQueryHandler(cb_back_routes,        pattern=rf"^{_CB_BACK_ROUTES}:"))
    app.add_handler(CallbackQueryHandler(cb_filter_open,        pattern=rf"^{_CB_FILTER_OPEN}$"))
    app.add_handler(CallbackQueryHandler(cb_filter_tog,         pattern=rf"^{_CB_FILTER_TOG}:"))
    app.add_handler(CallbackQueryHandler(cb_filter_done,        pattern=rf"^{_CB_FILTER_DONE}$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
