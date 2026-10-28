"""Xotelo research snapshots. Prices are estimates, never guaranteed tour quotes."""

from datetime import UTC, datetime, timedelta

import httpx

from trip_data.database import identity, minor
from trip_data.providers.base import ProviderFailure
from trip_data.providers.http import get_json

CITIES = {"Сочи": "g298536", "Казань": "g298520", "Дубай": "g295424", "Хургада": "g297549"}
BASE = "https://data.xotelo.com/api"


def checked(data):
    if data.get("error") is not None or not isinstance(data.get("result"), dict):
        raise ProviderFailure("invalid_response")
    return data["result"]


def observed(data):
    raw = data.get("timestamp")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ProviderFailure("invalid_response")
    try:
        at = datetime.fromtimestamp(raw / 1000 if raw > 10**11 else raw, UTC)
    except (ValueError, OverflowError, OSError):
        raise ProviderFailure("invalid_response") from None
    if at > datetime.now(UTC) + timedelta(minutes=5):
        raise ProviderFailure("invalid_response")
    return at


async def refresh_city(database, client, city, check_in, check_out, adults=2):
    if city not in CITIES or check_out <= check_in or not 1 <= adults <= 10:
        raise ValueError("Invalid city, dates or guest count")
    data = await get_json(client, BASE + "/list", params={"location_key": CITIES[city], "limit": 3})
    items = checked(data).get("list")
    seen = observed(data)
    if not isinstance(items, list):
        raise ProviderFailure("invalid_response")
    hotels = []
    for item in items[:3]:
        key, name = item.get("key"), item.get("name")
        if not isinstance(key, str) or not key.startswith(CITIES[city] + "-d") or not name:
            raise ProviderFailure("invalid_response")
        geo, reviews = item.get("geo") or {}, item.get("review_summary") or {}
        hotels.append(
            (
                key,
                city,
                name,
                item.get("url"),
                geo.get("latitude"),
                geo.get("longitude"),
                reviews.get("rating"),
                reviews.get("count"),
                seen.isoformat(),
            )
        )
    # Commit catalog before rate calls: timeouts do not erase usable hotel metadata.
    with database.connect() as db:
        db.executemany(
            "INSERT INTO xotelo_hotels(id,city,name,url,latitude,longitude,"
            "rating,review_count,fetched_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET city=excluded.city, "
            "name=excluded.name,url=excluded.url,latitude=excluded.latitude,"
            "longitude=excluded.longitude, "
            "rating=excluded.rating,review_count=excluded.review_count,fetched_at=excluded.fetched_at",
            hotels,
        )
    results = []
    for hotel in hotels:
        key = hotel[0]
        try:
            raw = await get_json(
                client,
                BASE + "/rates",
                params={
                    "hotel_key": key,
                    "chk_in": check_in.isoformat(),
                    "chk_out": check_out.isoformat(),
                    "adults": adults,
                    "rooms": 1,
                    "currency": "RUB",
                },
            )
            obj, at = checked(raw), observed(raw)
            if (
                obj.get("chk_in") != check_in.isoformat()
                or obj.get("chk_out") != check_out.isoformat()
            ):
                raise ProviderFailure("invalid_response")
            if obj.get("currency") != "RUB" or not isinstance(obj.get("rates"), list):
                raise ProviderFailure("invalid_response")
            rows = []
            for rate in obj["rates"]:
                provider = rate.get("name")
                if not provider or rate.get("rate") is None:
                    continue
                price = minor(rate["rate"])
                row_id = identity([key, str(check_in), str(check_out), adults, provider])
                rows.append(
                    (
                        row_id,
                        key,
                        str(check_in),
                        str(check_out),
                        adults,
                        "[]",
                        1,
                        provider,
                        "RUB",
                        price,
                        0,
                        at.isoformat(),
                        (at + timedelta(hours=6)).isoformat(),
                        0,
                    )
                )
            with database.connect() as db:
                db.execute(
                    "UPDATE xotelo_rates SET valid_until=? WHERE hotel_id=? "
                    "AND check_in=? AND check_out=? AND adults=? AND rooms=1 "
                    "AND children_ages_json='[]' AND currency='RUB' "
                    "AND julianday(fetched_at)<=julianday(?)",
                    (at.isoformat(), key, str(check_in), str(check_out), adults, at.isoformat()),
                )
                db.executemany(
                    "INSERT INTO xotelo_rates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET nightly_minor=excluded.nightly_minor, "
                    "fetched_at=excluded.fetched_at,valid_until=excluded.valid_until "
                    "WHERE julianday(excluded.fetched_at)>=julianday(xotelo_rates.fetched_at)",
                    rows,
                )
            results.append(
                {"hotel_id": key, "status": "ok" if rows else "empty", "rates": len(rows)}
            )
        except (ProviderFailure, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
            results.append({"hotel_id": key, "status": getattr(exc, "status", "invalid_response")})
    return {"city": city, "hotels": len(hotels), "rates": results}


def current_estimates(database, city, limit=20, *, check_in=None, check_out=None, adults=None):
    clauses = ["h.city=?", "julianday(r.valid_until)>julianday('now')"]
    values = [city]
    if check_in is not None:
        clauses.extend(["r.check_in=?", "r.check_out=?"])
        values.extend([str(check_in), str(check_out)])
    if adults is not None:
        clauses.append("r.adults=?")
        values.append(adults)
    with database.connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT h.id,h.city,h.name,h.url,h.rating,h.review_count,r.check_in,r.check_out,"
                "r.adults,r.rooms,r.provider,r.currency,r.nightly_minor,r.fetched_at,r.valid_until,"
                "r.children_ages_json,r.bookable,r.tax_known FROM xotelo_hotels h "
                "JOIN xotelo_rates r ON r.hotel_id=h.id WHERE "
                + " AND ".join(clauses)
                + " ORDER BY r.fetched_at DESC,r.id LIMIT ?",
                [*values, limit],
            )
        ]
