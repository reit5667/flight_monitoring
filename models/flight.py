from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class Flight(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    airline: str
    flight_number: str | None = None
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration: int
    stops: int
    price: Decimal
    currency: str
    scraped_at: datetime
    route_id: int

    @field_validator("origin", "destination")
    @classmethod
    def must_be_iata(cls, v: str) -> str:
        if len(v) != 3 or not v.isalpha() or not v.isupper():
            raise ValueError(f"Must be a 3-letter uppercase IATA code, got: {v!r}")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"Price must be positive, got: {v}")
        return v

    @field_validator("departure_time", "arrival_time", "scraped_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return v
