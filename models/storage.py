from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class RawSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    source: str
    route_id: int
    file_path: str
    records_count: int
    scraped_at: datetime

    @field_validator("scraped_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("scraped_at must be timezone-aware")
        return v
