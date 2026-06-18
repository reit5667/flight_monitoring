import logging
import os
from datetime import datetime, timedelta, timezone

from models.cdc import CdcEvent

logger = logging.getLogger(__name__)

# (route_id, flight_key, rule_type) → datetime of last notification sent
_sent_cache: dict[tuple, datetime] = {}


def should_send(event: CdcEvent, rule_type: str) -> bool:
    """
    Return True if this (route_id, flight_key, rule_type) hasn't been notified
    within DEDUP_WINDOW_HOURS. Marks the entry as sent when returning True.
    """
    window_hours = float(os.getenv("DEDUP_WINDOW_HOURS", "4"))
    key = (event.route_id, event.flight_key, rule_type)
    now = datetime.now(timezone.utc)

    last_sent = _sent_cache.get(key)
    if last_sent is not None and (now - last_sent) < timedelta(hours=window_hours):
        logger.debug(
            "Dedup: skip %s for %s (last sent %.1fh ago)",
            rule_type,
            event.flight_key,
            (now - last_sent).total_seconds() / 3600,
        )
        return False

    _sent_cache[key] = now
    return True


def clear_cache() -> None:
    """Reset dedup state. Intended for tests and worker restarts."""
    _sent_cache.clear()
