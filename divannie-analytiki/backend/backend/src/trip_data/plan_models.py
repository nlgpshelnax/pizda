from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from trip_data.models import Bundle, Money, SearchOutput, TripRequest


class Plan(BaseModel):
    id: str
    version: int
    request: TripRequest
    search: SearchOutput
    selected_id: str | None = None


class PlanPatch(BaseModel):
    base_version: int = Field(ge=1)
    changes: dict


class Selection(BaseModel):
    base_version: int = Field(ge=1)
    bundle_id: str


class Checkout(BaseModel):
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=100)


class DemoOrder(BaseModel):
    id: str
    plan_id: str
    plan_version: int
    bundle: Bundle
    total: Money
    created_at: datetime
    status: Literal["demo_only"] = "demo_only"


class ServiceInput(BaseModel):
    kind: Literal["early_check_in", "transfer"]
    idempotency_key: str = Field(min_length=8, max_length=100)


class ServiceRequest(BaseModel):
    id: str
    order_id: str
    kind: Literal["early_check_in", "transfer"]
    status: Literal["pending", "confirmed", "unavailable"] = "pending"
    data_mode: Literal["mock"] = "mock"
    note: str = "Demo request; no external supplier confirmation or charge"


class ServiceDecision(BaseModel):
    status: Literal["confirmed", "unavailable"]
