import logging
import os

import psycopg2
from dotenv import load_dotenv
from prefect import flow, task

from models.route import Route
from scheduler.pipeline import PipelineResult, run_pipeline_for_route

load_dotenv()

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "flight_monitor"),
        user=os.getenv("POSTGRES_USER", "flight_user"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def _load_enabled_routes() -> list[Route]:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT route_id, origin, destination, date_from, date_to,
                       max_price, currency, priority, search_interval, enabled, notes
                FROM routes
                WHERE enabled = true
                ORDER BY priority DESC
                """
            )
            rows = cur.fetchall()
    cols = [
        "route_id", "origin", "destination", "date_from", "date_to",
        "max_price", "currency", "priority", "search_interval", "enabled", "notes",
    ]
    return [Route(**dict(zip(cols, row))) for row in rows]


@task(name="pipeline-for-route", retries=1, retry_delay_seconds=30)
async def pipeline_task(route_id: int) -> PipelineResult:
    logger.info("Starting pipeline for route_id=%d", route_id)
    result = await run_pipeline_for_route(route_id)
    logger.info(
        "Pipeline done route_id=%d events=%s errors=%d duration=%.2fs",
        route_id, result.events_count, len(result.errors), result.duration_seconds,
    )
    if result.errors:
        logger.warning("route_id=%d errors: %s", route_id, result.errors)
    return result


@flow(name="run-all-routes", log_prints=True)
async def run_all_routes() -> list[PipelineResult]:
    routes = _load_enabled_routes()
    logger.info("Found %d enabled routes (sorted by priority DESC)", len(routes))

    results = []
    for route in routes:
        logger.info(
            "Dispatching route_id=%d %s->%s priority=%d",
            route.route_id, route.origin, route.destination, route.priority,
        )
        result = await pipeline_task(route.route_id)
        results.append(result)

    total_events = sum(
        sum(r.events_count.values()) for r in results
    )
    total_errors = sum(len(r.errors) for r in results)
    logger.info(
        "All routes done. total_events=%d total_errors=%d",
        total_events, total_errors,
    )
    return results


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_routes())
