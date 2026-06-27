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
from bot.airports import route_label, parse_route_input

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
_TP_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN", "")

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

# user_data key for free-form route input state
_STATE_AWAITING_ROUTE = "awaiting_route"


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

def _load_enabled_routes() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_id, origin, destination, date_from, date_to, notes
                FROM routes
                WHERE enabled = true
                ORDER BY priority DESC, route_id
                """
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


# ---------------------------------------------------------------------------
# Travelpayouts search
# ---------------------------------------------------------------------------

async def _fetch_flights(origin: str, dest: str, month: str) -> list[dict]:
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


def _aviasales_url(origin: str, dest: str, dep_date: date, adults: int) -> str:
    return f"https://www.aviasales.ru/search/{origin}{dep_date.strftime('%d%m')}{dest}{adults}"


def _fmt_duration(minutes: int) -> str:
    if not minutes:
        return "?"
    h, m = divmod(minutes, 60)
    return f"{h}ч{m:02d}м"


def _format_results(items: list[dict], origin: str, dest: str, adults: int, label: str) -> tuple[str, int | None]:
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
        url = _aviasales_url(origin, dest, dep.date(), adults)
        lines.append(
            f"{i}. {dep.strftime('%d.%m %H:%M')}  {_fmt_duration(duration)}  {stops_str}  [{airline}]\n"
            f"   {price:,}₽/чел"
            + (f" · <b>{price * adults:,}₽ итого</b>" if adults > 1 else "")
            + f"\n   <a href=\"{url}\">Aviasales</a>\n"
        )

    best = items[0]
    best_price = best["price"]
    best_url = _aviasales_url(origin, dest, datetime.fromisoformat(best["departure_at"]).date(), adults)
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


def _progress_bar(step: int, total: int = 5) -> str:
    filled = int(step / total * 10)
    return "█" * filled + "░" * (10 - filled)


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
        "2. Можно выбрать свой маршрут кнопкой «✈️ Любой маршрут»\n"
        "3. «📊 История цен» — динамика за 30 дней\n"
        "4. «🔔 Следить» — алёрт при изменении цены\n"
        "5. /unwatch — управление подписками\n\n"
        "<i>Данные берутся из Aviasales через Travelpayouts API.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_MAIN_KEYBOARD,
    )


async def _show_pax_selection(update: Update) -> None:
    buttons = [[
        InlineKeyboardButton("1 чел.", callback_data=f"{_CB_PAX}:1"),
        InlineKeyboardButton("2 чел.", callback_data=f"{_CB_PAX}:2"),
        InlineKeyboardButton("3 чел.", callback_data=f"{_CB_PAX}:3"),
        InlineKeyboardButton("4 чел.", callback_data=f"{_CB_PAX}:4"),
    ]]
    await update.message.reply_text("Сколько пассажиров?", reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_pax_selection(update)


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


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == _MENU_SEARCH:
        await _show_pax_selection(update)
    elif text == _MENU_HISTORY:
        await _show_history_routes(update)
    elif text == _MENU_HELP:
        await cmd_help(update, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-form route input: IATA codes or city names, e.g. 'HAN BKK' or 'Ханой Бангкок'."""
    state = context.user_data.get(_STATE_AWAITING_ROUTE)
    if not state:
        return

    parsed = parse_route_input(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "Не удалось распознать маршрут.\n\n"
            "Введите два города через пробел:\n"
            "<code>HAN BKK</code>  или  <code>Ханой Бангкок</code>  или  <code>Hanoi Bangkok</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    origin, dest = parsed
    adults = str(state["adults"])
    context.user_data.pop(_STATE_AWAITING_ROUTE, None)

    try:
        route_id = str(_ensure_route(origin, dest))
    except Exception:
        logger.exception("Failed to ensure route %s→%s", origin, dest)
        await update.message.reply_text("Не удалось создать маршрут.")
        return

    label = route_label(origin, dest)
    y, m = _first_available_month()
    kb = _build_calendar(y, m, "f", route_id, origin, dest, adults)
    await update.message.reply_text(
        f"<b>{label}</b>  —  выберите дату вылета (от):",
        reply_markup=kb, parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------

async def cb_pax(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    adults = query.data.split(":")[1]

    try:
        routes = _load_enabled_routes()
    except Exception:
        await query.edit_message_text("Не удалось загрузить маршруты.")
        return

    buttons = []
    for r in routes:
        label = r["notes"] or route_label(r['origin'], r['destination'])
        cb = f"{_CB_ROUTE}:{r['route_id']}:{r['origin']}:{r['destination']}:{r['date_from']}:{r['date_to']}:{adults}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    buttons.append([InlineKeyboardButton("✈️ Любой маршрут", callback_data=f"{_CB_CUSTOM}:{adults}")])

    await query.edit_message_text(f"Выберите маршрут ({adults} взр.):", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_custom_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    adults = int(query.data.split(":")[1])
    context.user_data[_STATE_AWAITING_ROUTE] = {"adults": adults}
    await query.edit_message_text(
        "Введите два города через пробел:\n\n"
        "<code>HAN BKK</code>  — коды IATA\n"
        "<code>Ханой Бангкок</code>  — по-русски\n"
        "<code>Hanoi Bangkok</code>  — по-английски",
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
        label = f"{org} → {dst}  {d_from.strftime('%d.%m')}–{d_to.strftime('%d.%m.%Y')}"

        await query.edit_message_text(f"Ищу рейсы {org} → {dst}…")

        # Collect months in range
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

        text, best_price = _format_results(filtered, org, dst, adults, label)

        keyboard = None
        if best_price is not None:
            cb = f"{_CB_WATCH}:{rid}:{org}:{dst}:{best_price}"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔔 Следить ({best_price:,}₽)", callback_data=cb)]])

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            reply_markup=keyboard,
        )


async def cb_cheapest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cheapest-in-month search: find top-3 cheapest days for the selected month."""
    query = update.callback_query
    await query.answer()

    # cheap:{rid}:{org}:{dst}:{adt}:{year}:{month}
    _, rid, org, dst, adt, y, m = query.data.split(":")
    adults = int(adt)
    year, month = int(y), int(m)
    month_str = f"{year}-{month:02d}"
    month_label = f"{_MONTHS_RU[month]} {year}"

    await query.edit_message_text(
        f"Ищу самые дешёвые рейсы {org} → {dst} за {month_label}…",
        parse_mode=ParseMode.HTML,
    )

    items = await _fetch_flights(org, dst, month_str)
    if not items:
        await query.edit_message_text(
            f"По маршруту <b>{org} → {dst}</b> за {month_label} ничего не найдено.",
            parse_mode=ParseMode.HTML,
        )
        return

    items.sort(key=lambda x: x["price"])
    top3 = items[:3]

    label = route_label(org, dst)
    lines = [f"<b>{label}</b> — топ дешёвых дат за {month_label} ({adults} взр.):\n"]
    for i, item in enumerate(top3, 1):
        dep = datetime.fromisoformat(item["departure_at"])
        price = item["price"]
        stops = item.get("transfers", 0)
        airline = item.get("airline", "?")
        duration = item.get("duration_to") or item.get("duration") or 0
        stops_str = "прямой" if stops == 0 else f"{stops} пер."
        url = _aviasales_url(org, dst, dep.date(), adults)
        lines.append(
            f"{i}. <b>{dep.strftime('%d %b').lower()}</b>  {_fmt_duration(duration)}  {stops_str}  [{airline}]\n"
            f"   {price:,}₽/чел"
            + (f" · <b>{price * adults:,}₽ итого</b>" if adults > 1 else "")
            + f"\n   <a href=\"{url}\">Aviasales</a>\n"
        )

    best_price = top3[0]["price"]
    lines.append(f"\nЛучшая цена в месяце: <b>{best_price:,}₽</b>/чел")

    keyboard_rows = []
    cb_watch = f"{_CB_WATCH}:{rid}:{org}:{dst}:{best_price}"
    keyboard_rows.append([InlineKeyboardButton(f"🔔 Следить ({best_price:,}₽)", callback_data=cb_watch)])
    # allow switching to another month
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

    text, best_price = _format_results(items, org, dst, adults, label)

    keyboard = None
    if best_price is not None:
        cb = f"{_CB_WATCH}:{rid}:{org}:{dst}:{best_price}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔔 Следить ({best_price:,}₽)", callback_data=cb)]])

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
        cb = f"{_CB_WATCH}:{route_id}:{origin}:{dest}:{current_price}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"🔔 Следить ({current_price:,}₽)", callback_data=cb)]])

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


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
# Entry point
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("search", "Поиск билетов"),
        BotCommand("history", "История цен"),
        BotCommand("unwatch", "Мои подписки / отменить алёрт"),
        BotCommand("help", "Справка"),
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
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f"^({_MENU_SEARCH}|{_MENU_HISTORY}|{_MENU_HELP})$"),
        handle_menu_button,
    ))
    # Free-form route input — lower priority than menu buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(cb_pax,          pattern=rf"^{_CB_PAX}:"))
    app.add_handler(CallbackQueryHandler(cb_custom_route, pattern=rf"^{_CB_CUSTOM}:"))
    app.add_handler(CallbackQueryHandler(cb_route,        pattern=rf"^{_CB_ROUTE}:"))
    app.add_handler(CallbackQueryHandler(cb_cal_nav,      pattern=rf"^{_CB_CAL_NAV}:"))
    app.add_handler(CallbackQueryHandler(cb_cal_day,      pattern=rf"^{_CB_CAL_DAY}:"))
    app.add_handler(CallbackQueryHandler(cb_cheapest,     pattern=rf"^{_CB_CHEAPEST}:"))
    app.add_handler(CallbackQueryHandler(cb_oneway,       pattern=rf"^{_CB_ONEWAY}:"))
    app.add_handler(CallbackQueryHandler(cb_hist,         pattern=rf"^{_CB_HIST}:"))
    app.add_handler(CallbackQueryHandler(cb_watch,        pattern=rf"^{_CB_WATCH}:"))
    app.add_handler(CallbackQueryHandler(cb_unwatch,      pattern=rf"^{_CB_UNWATCH}:"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r"^noop$"))

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
