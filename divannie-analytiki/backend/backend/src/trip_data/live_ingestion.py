"""Bounded refresh of public APIs into the relational catalog; no bookings or payments."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from trip_data.cache import SQLiteCache
from trip_data.context_models import (
    FlightEstimate,
    FlightQuery,
    RouteData,
    RouteQuery,
    WeatherData,
    WeatherQuery,
)
from trip_data.database import identity, minor, stamp
from trip_data.providers.external import OSRM, OpenMeteo, Travelpayouts
from trip_data.resilience import ContextRunner


def weather_rows(database, db, payload, source):
    data = WeatherData.model_validate(payload["data"])
    for day in data.days:
        database.dates(db, day.date, day.date)
        database.upsert(
            db,
            "weather",
            dict(
                id=identity([payload["city_id"], str(day.date), "forecast"]),
                city_id=payload["city_id"],
                date=day.date.isoformat(),
                kind="forecast",
                min_c=day.min_c,
                max_c=day.max_c,
                source_mode="live",
                source_id=source,
                fetched_at=payload["fetched_at"],
                valid_until=payload["expires_at"],
                payload_json=day.model_dump_json(),
            ),
        )
    return len(data.days)


def route_rows(database, db, payload, source):
    data = RouteData.model_validate(payload["data"])
    query = RouteQuery.model_validate(payload["query"])
    database.upsert(
        db,
        "routes",
        dict(
            id=identity([payload["city_id"], payload["hotel_id"], payload["query"]]),
            city_id=payload["city_id"],
            hotel_id=payload["hotel_id"],
            origin_lat=query.origin.latitude,
            origin_lon=query.origin.longitude,
            destination_lat=query.destination.latitude,
            destination_lon=query.destination.longitude,
            distance_m=data.distance_m,
            duration_seconds=data.duration_seconds,
            fare_minor=None,
            source_mode="live",
            source_id=source,
            fetched_at=payload["fetched_at"],
            valid_until=payload["expires_at"],
            payload_json=data.model_dump_json(),
        ),
    )
    return 1


def flight_rows(database, db, payload, source):
    estimates = [FlightEstimate.model_validate(v) for v in payload["data"]]
    for quote in estimates:
        database.upsert(
            db,
            "transport_estimates",
            dict(
                id=identity(
                    [
                        quote.origin,
                        quote.destination,
                        quote.departure_at.isoformat(),
                        quote.return_at.isoformat(),
                        quote.airline,
                    ]
                ),
                city_id=payload["city_id"],
                origin=quote.origin,
                destination=quote.destination,
                departure_at=quote.departure_at.isoformat(),
                return_at=quote.return_at.isoformat(),
                airline=quote.airline,
                currency=quote.price.currency,
                amount_minor=minor(quote.price.amount),
                price_basis=quote.price_basis,
                bookable=0,
                source_mode="snapshot",
                source_id=source,
                fetched_at=payload["fetched_at"],
                valid_until=quote.expires_at.isoformat(),
                payload_json=quote.model_dump_json(),
            ),
        )
    return len(estimates)


async def refresh_live(database, settings):
    runner = ContextRunner(SQLiteCache(settings.database_path), deadline=15)
    today = datetime.now(UTC).date()
    with database.connect() as db:
        cities = [dict(r) for r in db.execute("SELECT * FROM destinations ORDER BY id")]
        hotels = {
            city["id"]: db.execute(
                "SELECT id,latitude,longitude FROM hotels "
                "WHERE city_id=? AND source_mode=? AND active=1 "
                "ORDER BY id LIMIT 1",
                (city["id"], "snapshot"),
            ).fetchone()
            for city in cities
        }
    codes = {"sochi": "AER", "kazan": "KZN", "dubai": "DXB", "hurghada": "HRG"}
    semaphore = asyncio.Semaphore(2)
    async with httpx.AsyncClient() as client:

        async def load(provider, query, city, importer, hotel_id=None):
            async with semaphore:
                result = await runner.run(provider, query, client)
            source = provider.name + ":" + city["id"]
            if result.status not in ("ok", "empty"):
                database.log(source, result.status, stamp(), 0, result.status)
                return {"source": source, "status": result.status, "rows": 0}
            if result.status == "empty":
                database.log(source, "empty", stamp(), 0)
                return {"source": source, "status": "empty", "rows": 0}
            payload = dict(
                city_id=city["id"],
                hotel_id=hotel_id,
                query=query.model_dump(mode="json"),
                data=result.data,
                fetched_at=result.fetched_at.isoformat(),
                expires_at=result.expires_at.isoformat(),
            )
            return database.ingest(source, payload, lambda db, p, s: importer(database, db, p, s))

        jobs = []
        for city in cities:
            jobs.append(
                load(
                    OpenMeteo(),
                    WeatherQuery(
                        latitude=city["latitude"],
                        longitude=city["longitude"],
                        start_date=today,
                        end_date=today + timedelta(days=2),
                    ),
                    city,
                    weather_rows,
                )
            )
            if city["id"] in codes:
                jobs.append(
                    load(
                        Travelpayouts(settings.travelpayouts_token),
                        FlightQuery(
                            origin="MOW",
                            destination=codes[city["id"]],
                            departure_date=today + timedelta(days=21),
                            return_date=today + timedelta(days=26),
                        ),
                        city,
                        flight_rows,
                    )
                )
            hotel = hotels[city["id"]]
            if hotel:
                jobs.append(
                    load(
                        OSRM(),
                        RouteQuery(
                            origin=dict(latitude=city["latitude"], longitude=city["longitude"]),
                            destination=dict(
                                latitude=hotel["latitude"], longitude=hotel["longitude"]
                            ),
                        ),
                        city,
                        route_rows,
                        hotel["id"],
                    )
                )
        return await asyncio.gather(*jobs)
