"""Read-only, fixed-host adapters. No user-controlled endpoint URLs."""

from datetime import UTC, date, datetime

import httpx
from pydantic import SecretStr

from trip_data.context_models import (
    FlightEstimate,
    FlightQuery,
    Place,
    PlacesQuery,
    RouteData,
    RouteQuery,
    WeatherData,
    WeatherDay,
    WeatherQuery,
)
from trip_data.models import Money
from trip_data.providers.base import ProviderFailure
from trip_data.providers.http import get_json


class OpenMeteo:
    name = "open-meteo"
    ttl = 3600

    async def fetch(self, client: httpx.AsyncClient, query: WeatherQuery):
        today = datetime.now(UTC).date()
        # Conservative 7-day coverage. Never pretend climatology is a forecast.
        if query.start_date < today or (query.end_date - today).days > 6:
            return "out_of_coverage", None
        data = await get_json(
            client,
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": query.latitude,
                "longitude": query.longitude,
                "start_date": query.start_date.isoformat(),
                "end_date": query.end_date.isoformat(),
                "daily": "temperature_2m_min,temperature_2m_max",
                "timezone": "UTC",
            },
        )
        daily = data["daily"]
        days = [
            WeatherDay(date=date.fromisoformat(day), min_c=low, max_c=high)
            for day, low, high in zip(
                daily["time"], daily["temperature_2m_min"], daily["temperature_2m_max"], strict=True
            )
        ]
        expected = (query.end_date - query.start_date).days + 1
        if len(days) != expected or any(
            (day.date - query.start_date).days != index for index, day in enumerate(days)
        ):
            raise ProviderFailure("invalid_response")
        return "ok", WeatherData(days=days).model_dump(mode="json")


class OSRM:
    name = "osrm"
    ttl = 86400

    async def fetch(self, client: httpx.AsyncClient, query: RouteQuery):
        start, end = query.origin, query.destination
        coordinates = f"{start.longitude},{start.latitude};{end.longitude},{end.latitude}"
        data = await get_json(
            client,
            f"https://router.project-osrm.org/route/v1/driving/{coordinates}",
            params={"overview": "false"},
        )
        if data.get("code") == "NoRoute":
            return "empty", None
        if data.get("code") != "Ok":
            raise ProviderFailure("invalid_response")
        route = data["routes"][0]
        return "ok", RouteData(
            distance_m=route["distance"], duration_seconds=route["duration"]
        ).model_dump(mode="json")


class Overpass:
    name = "overpass"
    ttl = 86400
    tags = {
        "beach": '"natural"="beach"',
        "museum": '"tourism"="museum"',
        "restaurant": '"amenity"="restaurant"',
        "ski": '"piste:type"="downhill"',
    }

    async def fetch(self, client: httpx.AsyncClient, query: PlacesQuery):
        tag = self.tags[query.category]
        around = f"{query.radius_m},{query.latitude},{query.longitude}"
        q = f"[out:json][timeout:5];nwr(around:{around})[{tag}];out tags 30;"
        data = await get_json(client, "https://overpass-api.de/api/interpreter", params={"data": q})
        if data.get("remark"):
            raise ProviderFailure("unavailable")
        places = [
            Place(
                id=f"{e['type']}/{e['id']}",
                category=query.category,
                name=e.get("tags", {}).get("name"),
            ).model_dump(mode="json")
            for e in data["elements"]
        ]
        return "ok" if places else "empty", places


class Travelpayouts:
    name = "travelpayouts-data"
    ttl = 900

    def __init__(self, token: SecretStr | None):
        self.token = token

    async def fetch(self, client: httpx.AsyncClient, query: FlightQuery):
        if self.token is None or not self.token.get_secret_value():
            return "not_configured", None
        # Request-scoped headers; do not mutate a shared AsyncClient's credentials.
        data = await get_json(
            client,
            "https://api.travelpayouts.com/v1/prices/cheap",
            params={
                "origin": query.origin,
                "destination": query.destination,
                "depart_date": query.departure_date.isoformat(),
                "return_date": query.return_date.isoformat(),
                "currency": "rub",
            },
            headers={"X-Access-Token": self.token.get_secret_value()},
        )
        if data.get("success") is not True:
            raise ProviderFailure("invalid_response")
        quotes = []
        now = datetime.now(UTC)
        for destination, variants in data["data"].items():
            for item in variants.values():
                quote = FlightEstimate(
                    origin=query.origin,
                    destination=destination,
                    departure_at=item["departure_at"],
                    return_at=item["return_at"],
                    expires_at=item["expires_at"],
                    price=Money(amount=item["price"]),
                    airline=item.get("airline"),
                )
                if any(
                    t.utcoffset() is None
                    for t in (quote.departure_at, quote.return_at, quote.expires_at)
                ):
                    raise ProviderFailure("invalid_response")
                if (
                    quote.expires_at > now
                    and quote.destination == query.destination
                    and quote.departure_at.date() == query.departure_date
                    and quote.return_at.date() == query.return_date
                ):
                    quotes.append(quote.model_dump(mode="json"))
        return "ok" if quotes else "empty", quotes
