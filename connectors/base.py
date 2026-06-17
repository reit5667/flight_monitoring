import logging
from abc import ABC, abstractmethod

from models.flight import Flight
from models.route import Route, SourceMapping

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    source_name: str

    @abstractmethod
    async def _fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        """Implement the actual scraping logic. Called by fetch()."""

    async def fetch(self, route: Route, mapping: SourceMapping) -> list[Flight]:
        logger.info(
            "connector=%s route=%s->%s start",
            self.source_name,
            mapping.source_origin,
            mapping.source_destination,
        )
        try:
            flights = await self._fetch(route, mapping)
            logger.info(
                "connector=%s route=%s->%s found=%d",
                self.source_name,
                mapping.source_origin,
                mapping.source_destination,
                len(flights),
            )
            return flights
        except Exception:
            logger.exception(
                "connector=%s route=%s->%s failed",
                self.source_name,
                mapping.source_origin,
                mapping.source_destination,
            )
            return []
