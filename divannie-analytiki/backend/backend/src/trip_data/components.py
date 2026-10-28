"""Normalised component catalog. Price scope is attached to every quote."""

from datetime import datetime
from itertools import product
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from trip_data.models import (
    Bundle,
    Hotel,
    Money,
    Provenance,
    Transfer,
    Transport,
    TripRequest,
)
from trip_data.validation import validate_bundle


class HotelProperty(BaseModel):
    id: str
    name: str
    city: str
    timezone: str
    stars: int = Field(ge=0, le=5)
    rating: float = Field(ge=0, le=10)
    review_count: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_timezone(self) -> "HotelProperty":
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown hotel timezone") from exc
        return self


class HotelQuote(BaseModel):
    id: str
    property_id: str
    scope: TripRequest
    check_in_at: datetime
    check_out_at: datetime
    latest_check_in_at: datetime
    breakfast: bool
    pets_allowed: bool | None
    max_guests: int = Field(ge=1)
    children_allowed: bool | None
    early_check_in_confirmed: bool = False
    price: Money
    price_basis: Literal["stay_all_guests"] = "stay_all_guests"
    mandatory_fees_known: bool
    provenance: Provenance

    @model_validator(mode="after")
    def scoped_times(self) -> "HotelQuote":
        if any(
            value.utcoffset() is None
            for value in (self.check_in_at, self.check_out_at, self.latest_check_in_at)
        ):
            raise ValueError("Hotel quote timestamps require timezone offsets")
        if (
            self.check_in_at.date() != self.scope.check_in
            or self.check_out_at.date() != self.scope.check_out
            or self.check_out_at <= self.check_in_at
            or self.latest_check_in_at < self.check_in_at
        ):
            raise ValueError("Hotel quote times disagree with scope/window")
        return self


class TransportQuote(BaseModel):
    id: str
    scope: TripRequest
    direction: Literal["outbound", "inbound"]
    transport: Transport
    provenance: Provenance


class TransferQuote(BaseModel):
    id: str
    scope: TripRequest
    direction: Literal["outbound", "inbound"]
    hotel_property_id: str
    transfer: Transfer
    provenance: Provenance


def same_scope(left: TripRequest, right: TripRequest) -> bool:
    # Filters may change without changing price scope; all price-sensitive fields must match.
    return all(
        getattr(left, key) == getattr(right, key)
        for key in ("origin", "destination", "check_in", "check_out", "guests")
    )


class ComponentCatalog(BaseModel):
    properties: list[HotelProperty]
    hotels: list[HotelQuote]
    transport: list[TransportQuote]
    transfers: list[TransferQuote]

    @model_validator(mode="after")
    def references(self) -> "ComponentCatalog":
        ids = [p.id for p in self.properties]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate property ID")
        for collection in (self.hotels, self.transport, self.transfers):
            quote_ids = [q.id for q in collection]
            if len(set(quote_ids)) != len(quote_ids):
                raise ValueError("Duplicate quote ID")
        if any(q.property_id not in ids for q in self.hotels):
            raise ValueError("Unknown hotel property")
        if any(q.hotel_property_id not in ids for q in self.transfers):
            raise ValueError("Unknown transfer hotel property")
        return self

    def build(
        self, request: TripRequest, *, limit: int = 100, include_invalid: bool = False
    ) -> list[Bundle]:
        properties = {p.id: p for p in self.properties}
        hotels = [h for h in self.hotels if same_scope(h.scope, request)]
        legs = {
            direction: [
                q
                for q in self.transport
                if q.direction == direction and same_scope(q.scope, request)
            ]
            for direction in ("outbound", "inbound")
        }
        result = []
        for quote in hotels:
            prop = properties[quote.property_id]
            if prop.city != request.destination:
                continue
            transfers = {
                direction: [
                    q
                    for q in self.transfers
                    if q.direction == direction
                    and q.hotel_property_id == prop.id
                    and same_scope(q.scope, request)
                ]
                for direction in ("outbound", "inbound")
            }
            for out, back, pickup, dropoff in product(
                legs["outbound"], legs["inbound"], transfers["outbound"], transfers["inbound"]
            ):
                sources = [
                    quote.provenance,
                    out.provenance,
                    back.provenance,
                    pickup.provenance,
                    dropoff.provenance,
                ]
                # Never silently combine synthetic and real components.
                if len({p.kind == "mock" for p in sources}) != 1:
                    continue
                if min(p.valid_until for p in sources) <= max(p.fetched_at for p in sources):
                    continue
                provenance = Provenance(
                    provider="component-builder",
                    kind="mock" if sources[0].kind == "mock" else "snapshot",
                    fetched_at=max(p.fetched_at for p in sources),
                    valid_until=min(p.valid_until for p in sources),
                )
                hotel = Hotel(
                    id=quote.id,
                    name=prop.name,
                    city=prop.city,
                    location_id=prop.id,
                    timezone=prop.timezone,
                    stars=prop.stars,
                    rating=prop.rating,
                    review_count=prop.review_count,
                    **quote.model_dump(
                        exclude={"id", "property_id", "scope", "mandatory_fees_known"}
                    ),
                )
                bundle = Bundle(
                    id="::".join(q.id for q in (quote, out, back, pickup, dropoff)),
                    request=quote.scope,
                    hotel=hotel,
                    outbound=out.transport.model_copy(update={"provenance": out.provenance}),
                    inbound=back.transport.model_copy(update={"provenance": back.provenance}),
                    outbound_transfer=pickup.transfer.model_copy(
                        update={"provenance": pickup.provenance}
                    ),
                    inbound_transfer=dropoff.transfer.model_copy(
                        update={"provenance": dropoff.provenance}
                    ),
                    provenance=provenance,
                    mandatory_fees_known=quote.mandatory_fees_known,
                )
                if include_invalid or not any(
                    i.severity == "error" for i in validate_bundle(bundle, request)
                ):
                    result.append(bundle)
                if len(result) >= limit:
                    return result
        return result
