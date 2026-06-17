from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class Route(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    route_id: int | None = None
    origin: str
    destination: str
    date_from: date
    date_to: date
    max_price: Decimal | None = None
    currency: str = "USD"
    priority: int = 100
    search_interval: int = 60
    enabled: bool = True
    notes: str | None = None


class SourceMapping(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    route_id: int
    source: str
    source_origin: str
    source_destination: str
    enabled: bool = True
