from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class CdcEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: Literal["INSERT", "UPDATE", "DELETE"]
    route_id: int
    source: str
    flight_key: str
    old_price: float | None = None
    new_price: float | None = None
    changed_fields: dict[str, dict[str, Any]] = {}
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return v
