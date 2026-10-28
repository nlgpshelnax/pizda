"""Undated Tutu schedules published via Travelpayouts, for research only."""

import json
from datetime import UTC, datetime, timedelta

from trip_data.database import identity
from trip_data.providers.base import ProviderFailure
from trip_data.providers.http import get_json

CODES = {"Москва": "2000000", "Казань": "2060615"}
DOC_URL = "https://support.travelpayouts.com/hc/ru/articles/360020147791"


async def refresh_schedule(database, client, origin, destination):
    if origin not in CODES or destination not in CODES or origin == destination:
        raise ValueError("Unsupported route")
    data = await get_json(
        client,
        "https://suggest.travelpayouts.com/search",
        params={
            "service": "tutu_trains",
            "term": CODES[origin],
            "term2": CODES[destination],
        },
    )
    trips = data.get("trips")
    if not isinstance(trips, list) or len(trips) > 500:
        raise ProviderFailure("invalid_response")
    now = datetime.now(UTC)
    rows = []
    for trip in trips:
        if not isinstance(trip, dict):
            raise ProviderFailure("invalid_response")
        try:
            number = trip["trainNumber"]
            depart, arrive = trip["departureTime"], trip["arrivalTime"]
            datetime.strptime(depart, "%H:%M:%S")
            datetime.strptime(arrive, "%H:%M:%S")
            duration = int(trip["travelTimeInSeconds"])
            if not isinstance(number, str) or not number or not 0 < duration <= 14 * 86400:
                raise ValueError
            categories = trip.get("categories", [])
            if not isinstance(categories, list):
                raise ValueError
            clean = []
            for category in categories:
                price = category.get("price")
                kind = category.get("type")
                if (
                    not isinstance(kind, str)
                    or isinstance(price, bool)
                    or not isinstance(price, int)
                    or price < 0
                ):
                    raise ValueError
                clean.append({"type": kind, "price_rub": price})
        except (KeyError, TypeError, ValueError):
            raise ProviderFailure("invalid_response") from None
        rows.append(
            {
                "id": identity([origin, destination, number, depart, arrive]),
                "origin": origin,
                "destination": destination,
                "origin_code": CODES[origin],
                "destination_code": CODES[destination],
                "train_number": number,
                "departure_time": depart,
                "arrival_time": arrive,
                "duration_seconds": duration,
                "categories_json": json.dumps(clean, ensure_ascii=False),
                "bookable": 0,
            }
        )
    source = f"tutu:{CODES[origin]}:{CODES[destination]}"
    payload = {
        "rows": rows,
        "fetched_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=6)).isoformat(),
    }

    def importer(db, payload, source_id):
        db.execute("DELETE FROM rail_schedule_estimates WHERE source_id=?", (source_id,))
        for row in payload["rows"]:
            database.upsert(
                db,
                "rail_schedule_estimates",
                {
                    **row,
                    "source_id": source_id,
                    "fetched_at": payload["fetched_at"],
                    "valid_until": payload["valid_until"],
                },
            )
        return len(payload["rows"])

    return database.ingest(source, payload, importer)


def read_schedule(database, origin, destination):
    with database.connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM rail_schedule_estimates WHERE origin=? AND destination=? "
                "AND julianday(valid_until)>julianday('now') "
                "ORDER BY departure_time,train_number LIMIT 100",
                (origin, destination),
            )
        ]
    for row in rows:
        row["categories"] = json.loads(row.pop("categories_json"))
    return rows
