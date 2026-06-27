import logging
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel

from cdc.engine import compare_snapshots
from db import get_conn as _get_conn
from metrics.prometheus import (
    cdc_events_total,
    connector_flights_found,
    connector_requests_total,
    pipeline_duration_seconds,
)
from models.flight import Flight
from models.route import Route
from notifications.dedup import should_send
from notifications.rules import check_notification_rules
from notifications.subscriptions import check_subscriptions
from notifications.telegram import send_notification
from planner.search_planner import run_search_for_route
from warehouse.current import apply_cdc_to_current
from warehouse.events import save_cdc_events
from warehouse.history import append_history

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    route_id: int
    sources_processed: list[str]
    events_count: dict[str, int]
    duration_seconds: float
    errors: list[str]


def _load_route(route_id: int) -> Route:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_id, origin, destination, date_from, date_to,
                       max_price, currency, priority, search_interval, enabled, notes
                FROM routes WHERE route_id = %s
                """,
                (route_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"Route {route_id} not found")
    cols = ["route_id", "origin", "destination", "date_from", "date_to",
            "max_price", "currency", "priority", "search_interval", "enabled", "notes"]
    return Route(**dict(zip(cols, row)))


def _load_current_flights(route_id: int, source: str) -> list[Flight]:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, airline, flight_number, origin, destination,
                       departure_time, arrival_time, duration_minutes, stops,
                       price, currency, scraped_at, route_id
                FROM flights_current
                WHERE route_id = %s AND provider = %s
                """,
                (route_id, source),
            )
            rows = cur.fetchall()

    flights = []
    for row in rows:
        (provider, airline, flight_number, origin, destination,
         departure_time, arrival_time, duration_minutes, stops,
         price, currency, scraped_at, rid) = row
        flights.append(Flight(
            provider=provider,
            airline=airline,
            flight_number=flight_number,
            origin=origin,
            destination=destination,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration=duration_minutes,
            stops=stops,
            price=Decimal(str(price)),
            currency=currency,
            scraped_at=scraped_at,
            route_id=rid,
        ))
    return flights


async def run_pipeline_for_route(route_id: int) -> PipelineResult:
    started_at = datetime.now(timezone.utc)
    events_count: dict[str, int] = {"INSERT": 0, "UPDATE": 0, "DELETE": 0}
    sources_processed: list[str] = []
    errors: list[str] = []

    logger.info("pipeline: route_id=%d start", route_id)

    route = _load_route(route_id)

    logger.info("pipeline: route_id=%d search_planner start", route_id)
    search_results = await run_search_for_route(route_id)
    logger.info(
        "pipeline: route_id=%d search_planner done sources=%s",
        route_id, list(search_results.keys()),
    )

    for source, new_flights in search_results.items():
        source_start = datetime.now(timezone.utc)
        logger.info("pipeline: route_id=%d source=%s flights_fetched=%d", route_id, source, len(new_flights))

        try:
            connector_flights_found.labels(source=source).set(len(new_flights))

            previous_flights = _load_current_flights(route_id, source)
            logger.info(
                "pipeline: route_id=%d source=%s previous_snapshot_size=%d",
                route_id, source, len(previous_flights),
            )

            events = compare_snapshots(previous_flights, new_flights)
            logger.info(
                "pipeline: route_id=%d source=%s cdc_events=%d",
                route_id, source, len(events),
            )

            if events:
                # Check notification rules BEFORE warehouse write (history must reflect previous state)
                with _get_conn() as conn:
                    for event in events:
                        trigger = check_notification_rules(event, route, conn)
                        if trigger and should_send(event, trigger.rule_type):
                            await send_notification(trigger.message)

                # Check per-user subscriptions for price alerts
                await check_subscriptions(events, route_id)

                apply_cdc_to_current(events, new_flights)
                logger.info("pipeline: route_id=%d source=%s apply_cdc_to_current done", route_id, source)

                append_history(events, new_flights)
                logger.info("pipeline: route_id=%d source=%s append_history done", route_id, source)

                save_cdc_events(events)
                logger.info("pipeline: route_id=%d source=%s save_cdc_events done", route_id, source)

            for event in events:
                events_count[event.event_type] = events_count.get(event.event_type, 0) + 1
                cdc_events_total.labels(event_type=event.event_type).inc()

            connector_requests_total.labels(source=source, status="success").inc()
            sources_processed.append(source)
            elapsed = (datetime.now(timezone.utc) - source_start).total_seconds()
            logger.info(
                "pipeline: route_id=%d source=%s done elapsed=%.2fs",
                route_id, source, elapsed,
            )

        except Exception as exc:
            msg = f"source={source}: {exc!r}"
            logger.exception("pipeline: route_id=%d %s", route_id, msg)
            errors.append(msg)
            connector_requests_total.labels(source=source, status="error").inc()

    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    pipeline_duration_seconds.labels(route_id=str(route_id)).observe(duration)
    result = PipelineResult(
        route_id=route_id,
        sources_processed=sources_processed,
        events_count=events_count,
        duration_seconds=duration,
        errors=errors,
    )
    logger.info(
        "pipeline: route_id=%d finished duration=%.2fs events=%s errors=%d",
        route_id, duration, events_count, len(errors),
    )
    return result
