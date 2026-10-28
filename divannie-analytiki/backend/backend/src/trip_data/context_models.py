from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from trip_data.models import Money


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class WeatherQuery(Coordinates):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def period(self) -> "WeatherQuery":
        if self.end_date < self.start_date:
            raise ValueError("end_date precedes start_date")
        return self


class RouteQuery(BaseModel):
    origin: Coordinates
    destination: Coordinates


class PlacesQuery(Coordinates):
    category: Literal["beach", "museum", "restaurant", "ski"]
    radius_m: int = Field(default=1500, ge=100, le=5000)


class FlightQuery(BaseModel):
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    destination: str = Field(pattern=r"^[A-Z]{3}$")
    departure_date: date
    return_date: date

    @model_validator(mode="after")
    def period(self) -> "FlightQuery":
        if self.return_date <= self.departure_date:
            raise ValueError("Return date must follow departure")
        return self


class WeatherDay(BaseModel):
    date: date
    min_c: float = Field(allow_inf_nan=False)
    max_c: float = Field(allow_inf_nan=False)


class WeatherData(BaseModel):
    kind: Literal["forecast"] = "forecast"
    timezone: str = "UTC"
    days: list[WeatherDay]


class RouteData(BaseModel):
    distance_m: float = Field(ge=0, allow_inf_nan=False)
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    fare: None = None  # OSRM does not quote fares.


class Place(BaseModel):
    id: str
    name: str | None = None
    category: str


class FlightEstimate(BaseModel):
    origin: str
    destination: str
    departure_at: datetime
    return_at: datetime
    expires_at: datetime
    price: Money
    price_basis: Literal["provider_cached_ticket"] = "provider_cached_ticket"
    airline: str | None = None
    bookable: Literal[False] = False


class ContextResult(BaseModel):
    provider: str
    status: Literal[
        "ok",
        "empty",
        "out_of_coverage",
        "not_configured",
        "timeout",
        "unauthorized",
        "rate_limited",
        "unavailable",
        "invalid_response",
        "circuit_open",
    ]
    data_mode: Literal["mock", "live"]
    data: dict | list | None = None
    cache_hit: bool = False
    stale: bool = False
    fallback_reason: str | None = None
    attempts: int = 0
    fetched_at: datetime | None = None
    expires_at: datetime | None = None
    latency_ms: float = 0
    warnings: list[str] = Field(default_factory=list)
