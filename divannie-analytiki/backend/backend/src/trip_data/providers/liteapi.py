"""Optional Nuitee/LiteAPI v3 rate lookup. Search only; no prebook/payment methods."""

from datetime import date
from typing import Literal

import httpx
from pydantic import BaseModel, Field, SecretStr, model_validator

from trip_data.models import Guests, Money
from trip_data.providers.base import ProviderFailure


class HotelRateQuery(BaseModel):
    hotel_ids: list[str] = Field(min_length=1, max_length=5)
    check_in: date
    check_out: date
    guests: Guests
    guest_nationality: str = Field(pattern=r"^[A-Z]{2}$")

    @model_validator(mode="after")
    def scope(self):
        if self.check_out <= self.check_in:
            raise ValueError("Invalid stay dates")
        if any(not h or len(h) > 100 or h.startswith("osm:") for h in self.hotel_ids):
            raise ValueError("Use LiteAPI hotel IDs; OSM IDs require verified mapping")
        return self


class HotelRate(BaseModel):
    hotel_id: str
    offer_id: str | None
    rate_id: str | None
    scope: HotelRateQuery
    price: Money
    board_name: str | None = None
    pets_allowed: None = None
    mandatory_fees_known: Literal[False] = False
    requires_recheck: Literal[True] = True
    bookable: Literal[False] = False


async def search_rates(
    client: httpx.AsyncClient,
    query: HotelRateQuery,
    key: SecretStr | None,
    environment: Literal["sandbox", "production"] = "sandbox",
):
    if key is None or not key.get_secret_value():
        return {
            "provider": "liteapi",
            "status": "not_configured",
            "environment": environment,
            "rates": [],
        }
    # Reuse the same HTTP/error normalisation; only this POST is a read-only rate search.
    from trip_data.providers.http import post_json

    data = await post_json(
        client,
        "https://api.liteapi.travel/v3.0/hotels/rates",
        headers={"X-API-Key": key.get_secret_value()},
        data={
            "hotelIds": query.hotel_ids,
            "checkin": query.check_in.isoformat(),
            "checkout": query.check_out.isoformat(),
            "currency": "RUB",
            "guestNationality": query.guest_nationality,
            "occupancies": [
                {"rooms": 1, "adults": query.guests.adults, "children": query.guests.children_ages}
            ],
            "timeout": 4,
        },
    )
    if "data" not in data or not isinstance(data["data"], list):
        raise ProviderFailure("invalid_response")
    rates = []
    for hotel in data["data"]:
        if hotel["hotelId"] not in query.hotel_ids:
            raise ProviderFailure("invalid_response")
        for room in hotel["roomTypes"]:
            # This implementation supports exactly one requested room/occupancy.
            offered = room.get("rates", [])
            if len(offered) != 1:
                continue
            rate = offered[0]
            if rate.get("adultCount") != query.guests.adults or sorted(
                rate.get("childrenAges", [])
            ) != sorted(query.guests.children_ages):
                continue
            totals = rate.get("retailRate", {}).get("total", [])
            rub = [p for p in totals if p.get("currency") == "RUB"]
            if len(rub) != 1:
                raise ProviderFailure("invalid_response")
            rates.append(
                HotelRate(
                    hotel_id=hotel["hotelId"],
                    offer_id=room.get("offerId"),
                    rate_id=rate.get("rateId"),
                    scope=query,
                    price=Money(amount=rub[0]["amount"]),
                    board_name=rate.get("boardName"),
                ).model_dump(mode="json")
            )
    actual = "sandbox" if data.get("sandbox") is True else environment
    return {
        "provider": "liteapi",
        "status": "ok" if rates else "empty",
        "environment": actual,
        "rates": rates,
        "warnings": [
            "Taxes, pets and cancellation require offer verification",
            "No prebooking, availability guarantee or payment is performed",
        ],
    }


class HotelLookup(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    limit: int = Field(default=10, ge=1, le=20)


async def lookup_hotels(client, query: HotelLookup, key: SecretStr | None):
    if key is None or not key.get_secret_value():
        return {"provider": "liteapi", "status": "not_configured", "hotels": []}
    from trip_data.providers.http import get_json

    data = await get_json(
        client,
        "https://api.liteapi.travel/v3.0/data/hotels",
        params={"cityName": query.city, "countryCode": query.country, "limit": query.limit},
        headers={"X-API-Key": key.get_secret_value()},
    )
    if not isinstance(data.get("data"), list):
        raise ProviderFailure("invalid_response")
    return {
        "provider": "liteapi",
        "status": "ok" if data["data"] else "empty",
        "hotels": [
            {
                k: h.get(k)
                for k in ("id", "name", "city", "country", "latitude", "longitude", "stars")
            }
            for h in data["data"]
        ],
        "warnings": ["Provider hotel IDs are not interchangeable with OSM object IDs"],
    }
