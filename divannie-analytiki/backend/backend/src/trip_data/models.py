from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class SlotStatus(StrEnum):
    YES = "YES"
    VAGUE = "Vague"
    NO = "NO"


class Slot(BaseModel):
    status: SlotStatus
    value: str | int | bool | list[int] | None = None
    evidence: str | None = None


class Guests(BaseModel):
    adults: int = Field(ge=1, le=10)
    children_ages: list[int] = Field(default_factory=list, max_length=10)
    pets: int = Field(default=0, ge=0, le=5)

    @field_validator("children_ages")
    @classmethod
    def validate_ages(cls, ages: list[int]) -> list[int]:
        if any(age < 0 or age > 17 for age in ages):
            raise ValueError("Children must be 0–17 years old")
        return ages


class Money(BaseModel):
    amount: Decimal = Field(ge=0, decimal_places=2, allow_inf_nan=False)
    currency: Literal["RUB"] = "RUB"


class TripRequest(BaseModel):
    origin: str
    destination: str
    check_in: date
    check_out: date
    guests: Guests
    budget: Money | None = None  # Whole trip, all guests; AI must resolve ambiguity first.
    breakfast_required: bool = False
    min_stars: int = Field(default=0, ge=0, le=5)
    child_seats_required: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def validate_dates(self) -> "TripRequest":
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class Provenance(BaseModel):
    provider: str
    kind: Literal["live", "snapshot", "mock"]
    fetched_at: datetime
    valid_until: datetime
    source_url: str | None = None

    @model_validator(mode="after")
    def validate_times(self) -> "Provenance":
        if self.fetched_at.utcoffset() is None or self.valid_until.utcoffset() is None:
            raise ValueError("Provenance timestamps need timezone offsets")
        if self.valid_until <= self.fetched_at:
            raise ValueError("valid_until must be after fetched_at")
        return self


class Segment(BaseModel):
    origin: str  # Airport/station ID, not a city label.
    destination: str
    departure_at: datetime
    arrival_at: datetime
    departure_timezone: str
    arrival_timezone: str
    carrier: str | None = None

    @model_validator(mode="after")
    def timezones(self) -> "Segment":
        for value, name in (
            (self.departure_at, self.departure_timezone),
            (self.arrival_at, self.arrival_timezone),
        ):
            try:
                zone = ZoneInfo(name)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("Unknown IANA timezone") from exc
            if value.utcoffset() is None or value.astimezone(zone).utcoffset() != value.utcoffset():
                raise ValueError("Timestamp offset disagrees with IANA timezone")
        return self


class Connection(BaseModel):
    origin: str
    destination: str
    duration_minutes: int = Field(gt=0)
    confirmed: bool = False


class Hotel(BaseModel):
    id: str
    name: str
    city: str
    check_in_at: datetime
    check_out_at: datetime
    latest_check_in_at: datetime
    stars: int = Field(ge=0, le=5)
    rating: float = Field(ge=0, le=10)
    review_count: int = Field(ge=0)
    breakfast: bool
    pets_allowed: bool | None
    early_check_in_confirmed: bool = False
    location_id: str | None = None
    timezone: str | None = None
    max_guests: int | None = Field(default=None, ge=1)
    children_allowed: bool | None = None
    price_basis: Literal["stay_all_guests"] = "stay_all_guests"
    provenance: Provenance | None = None
    price: Money  # Total stay for the exact occupancy, including known mandatory fees.


class Transport(BaseModel):
    id: str
    mode: Literal["flight", "train"]
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    international: bool = False
    departure_location: str | None = None
    arrival_location: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    arrival_buffer_minutes: int | None = Field(default=None, ge=0)
    departure_buffer_minutes: int | None = Field(default=None, ge=0)
    price_basis: Literal["leg_all_guests"] = "leg_all_guests"
    provenance: Provenance | None = None
    price: Money  # All guests; one direction.


class Transfer(BaseModel):
    id: str
    origin: str | None = None
    destination: str | None = None
    available_from: datetime | None = None
    available_until: datetime | None = None
    child_seats: int | None = Field(default=None, ge=0)
    duration_minutes: int = Field(gt=0)
    capacity: int = Field(gt=0)
    pets_allowed: bool | None
    price_basis: Literal["vehicle_one_way"] = "vehicle_one_way"
    provenance: Provenance | None = None
    price: Money  # Per vehicle, one direction; routing duration is not a fare.

    @model_validator(mode="after")
    def window(self) -> "Transfer":
        for value in (self.available_from, self.available_until):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Transfer windows require timezone offsets")
        if (
            self.available_from
            and self.available_until
            and self.available_until < self.available_from
        ):
            raise ValueError("Invalid transfer pickup window")
        return self


class Bundle(BaseModel):
    id: str
    request: TripRequest
    hotel: Hotel
    outbound: Transport
    inbound: Transport
    transfer: Transfer | None = Field(default=None, json_schema_extra={"deprecated": True})
    outbound_transfer: Transfer | None = None
    inbound_transfer: Transfer | None = None
    provenance: Provenance
    mandatory_fees_known: bool = True

    @model_validator(mode="after")
    def aware_times(self) -> "Bundle":
        if not self.transfer and not (self.outbound_transfer and self.inbound_transfer):
            raise ValueError("Provide both transfers, or the legacy symmetric transfer")
        times = [
            self.hotel.check_in_at,
            self.hotel.check_out_at,
            self.hotel.latest_check_in_at,
            self.outbound.departure_at,
            self.outbound.arrival_at,
            self.inbound.departure_at,
            self.inbound.arrival_at,
        ]
        if any(t.utcoffset() is None for t in times):
            raise ValueError("All journey times need timezone offsets")
        return self

    def transfers(self) -> tuple[Transfer, Transfer]:
        outward = self.outbound_transfer or self.transfer
        inward = self.inbound_transfer or self.transfer
        if outward is None or inward is None:
            raise ValueError("Both transfers are required")
        return outward, inward


class Issue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str


class BundleResult(BaseModel):
    bundle: Bundle
    total: Money
    issues: list[Issue]
    reasons: list[str]


class SearchInput(BaseModel):
    request: TripRequest
    plan_version: int = Field(ge=1)


class SearchOutput(BaseModel):
    plan_version: int
    data_mode: Literal["mock"] = "mock"
    options: list[BundleResult]
    rejected: dict[str, list[Issue]]
    limitations: list[str]
    provider_reports: list["ProviderReport"] = Field(default_factory=list)


class ProviderReport(BaseModel):
    provider: str
    status: Literal[
        "ok", "empty", "timeout", "unauthorized", "rate_limited", "unavailable", "invalid_response"
    ]
    cache_hit: bool = False
    latency_ms: float = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)


class RequoteInput(SearchInput):
    previous_bundle_id: str


class RequoteOutput(BaseModel):
    previous_bundle_id: str
    previous_total: Money
    new_total: Money | None
    price_delta: Decimal | None
    invalidated_components: list[str]
    search: SearchOutput
