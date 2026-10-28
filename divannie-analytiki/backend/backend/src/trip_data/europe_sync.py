"""Bounded real-source European catalog refresh. Unknown commercial data stays unknown."""

import asyncio
import json
import math
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from trip_data.context_models import FlightEstimate, RouteQuery
from trip_data.database import identity, minor, stamp
from trip_data.hotels import OSM_ATTRIBUTION, OSM_LICENSE, safe_website
from trip_data.live_ingestion import route_rows
from trip_data.providers.base import ProviderFailure
from trip_data.providers.external import OSRM
from trip_data.providers.http import get_json
from trip_data.providers.passport_index import refresh_passport_index

CATALOG = Path("data/knowledge/europe-sync.json")
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_SWISS = "https://overpass.osm.ch/api/interpreter"
AIRPORTS = "https://api.travelpayouts.com/data/en/airports.json"


def geocode_result(data, country, query):
    matches = [r for r in data.get("results", []) if r.get("country_code") == country]

    def normal(value):
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return "".join(ch for ch in decomposed if ch.isalnum() and not unicodedata.combining(ch))

    exact = [r for r in matches if normal(r.get("name", "")) == normal(query)]
    if not exact:
        return None
    item = exact[0]
    try:
        lat, lon = float(item["latitude"]), float(item["longitude"])
        if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
            return None
        ZoneInfo(item["timezone"])
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError):
        return None
    return item


def city_payload(spec, result):
    country, label, query, airport = spec
    return {
        "id": "eu-" + identity([country, label])[:16],
        "city": label,
        "country": country,
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "timezone": result["timezone"],
        "vibes": [],
        "months": [],
        "seasonality_kind": "unknown",
        "seasonality_verified": False,
        "climatology": None,
        "geocoding_name": result["name"],
        "geonames_id": result.get("id"),
        "source_url": GEOCODER,
        "airport_candidate_iata": airport,
        "airport_candidate_verified_nearest": False,
        "query": query,
    }


def ensure_unknown_visa(database, country):
    # No passport dataset contract has been verified. A placeholder is not a visa decision.
    value = {
        "passport_country": "RU",
        "destination_country": country,
        "passport_type": "ordinary",
        "purpose": "tourism",
        "visa_status": "unknown",
    }
    with database.connect() as db:
        database.upsert(
            db,
            "visa_rules",
            {
                "id": identity(value),
                **value,
                "source_mode": "unknown",
                "payload_json": json.dumps(value),
                "notes": "Unverified; consult official destination and transit authorities",
            },
        )


def import_current(database, db, payload, source):
    city = database.city_id(db, payload["city"])
    current = payload["current"]
    temp, snow, rain = (
        current.get("temperature_2m"),
        current.get("snow_depth"),
        current.get("precipitation"),
    )
    avg = payload.get("daily_mean_c")
    for v in (temp, snow, rain, avg):
        if v is not None and (
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        ):
            raise ValueError("Invalid weather values")
    database.upsert(
        db,
        "weather",
        {
            "id": identity([city, "current"]),
            "city_id": city,
            "date": current["time"][:10],
            "kind": "current",
            "min_c": None,
            "max_c": None,
            "avg_c": avg,
            "sea_temp_c": None,
            "snow_depth_cm": snow * 100 if snow is not None else None,
            "source_mode": "live",
            "source_id": source,
            "fetched_at": payload["fetched_at"],
            "valid_until": payload["valid_until"],
            "payload_json": json.dumps(
                {
                    **current,
                    "daily_mean_c": avg,
                    "daily_mean_kind": "forecast" if avg is not None else None,
                }
            ),
        },
    )
    return 1


COASTAL = {
    "Ницца",
    "Биарриц",
    "Марсель",
    "Палермо",
    "Венеция",
    "Амальфи",
    "Барселона",
    "Малага",
    "Сан-Себастьян",
    "Тенерифе",
    "Рюген",
    "Гамбург",
    "Брайтон",
    "Корнуолл",
    "Фару",
    "Лиссабон",
    "Порту",
    "Фуншал",
    "Ханья",
    "Афины",
    "Санторини",
    "Гаага",
    "Роттердам",
    "Брюгге",
    "Осло",
    "Берген",
    "Тромсё",
    "Стокгольм",
    "Гётеборг",
    "Будва",
    "Котор",
    "Монте-Карло",
    "Валлетта",
}


def import_marine(database, db, payload, source):
    city = database.city_id(db, payload["city"])
    current = payload["current"]
    value = current.get("sea_surface_temperature")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid sea temperature")
    database.upsert(
        db,
        "weather",
        {
            "id": identity([city, "marine_current"]),
            "city_id": city,
            "date": current["time"][:10],
            "kind": "marine_current",
            "min_c": None,
            "max_c": None,
            "avg_c": None,
            "sea_temp_c": value,
            "snow_depth_cm": None,
            "source_mode": "live",
            "source_id": source,
            "fetched_at": payload["fetched_at"],
            "valid_until": payload["valid_until"],
            "payload_json": json.dumps(payload),
        },
    )
    return 1


def distance_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(h)))


def category(tags):
    if tags.get("natural") == "beach" or tags.get("leisure") == "beach":
        return "beach"
    if tags.get("natural") == "coastline":
        return "coastline"
    if tags.get("piste:type") or tags.get("aerialway"):
        return "ski"
    if (
        tags.get("tourism") == "museum"
        or tags.get("historic") == "monument"
        or tags.get("amenity") == "theatre"
    ):
        return "culture"
    if tags.get("leisure") == "spa" or tags.get("amenity") == "public_bath":
        return "spa"
    if tags.get("natural") == "peak" or tags.get("route") == "hiking":
        return "nature"
    return None


def import_osm(database, db, payload, source):
    city = database.city_id(db, payload["city"])
    for table in ("hotels", "activities"):
        db.execute(f"UPDATE {table} SET active=0 WHERE source_id=?", (source,))
    count = 0
    for e in payload["elements"]:
        kind, obj_id = e.get("type"), e.get("id")
        if kind not in ("node", "way", "relation") or not isinstance(obj_id, int):
            continue
        loc = e.get("center") or e
        lat, lon = loc.get("lat"), loc.get("lon")
        if (
            not isinstance(lat, (float, int))
            or not isinstance(lon, (float, int))
            or not math.isfinite(lat)
            or not math.isfinite(lon)
            or abs(lat) > 90
            or abs(lon) > 180
        ):
            continue
        tags = e.get("tags") or {}
        name = tags.get("name")
        url = f"https://www.openstreetmap.org/{kind}/{obj_id}"
        row_id = "euosm:" + identity([city, kind, obj_id])[:32]
        common = {
            "id": row_id,
            "city_id": city,
            "source_mode": "snapshot",
            "source_id": source,
            "source_url": url,
            "fetched_at": payload["fetched_at"],
            "active": 1,
        }
        if (
            tags.get("tourism") in ("hotel", "guest_house", "hostel")
            and isinstance(name, str)
            and name
        ):
            stars = (
                int(tags["stars"])
                if str(tags.get("stars", "")).isdigit() and 0 <= int(tags["stars"]) <= 5
                else None
            )
            pets = {"yes": 1, "allowed": 1, "no": 0}.get(tags.get("pets", "").lower())
            data = {
                "id": row_id,
                "name": name,
                "city": payload["city"],
                "country": payload["country"],
                "category": tags["tourism"],
                "latitude": lat,
                "longitude": lon,
                "coordinate_kind": "mapped_point" if kind == "node" else "geometry_centroid",
                "address": tags.get("addr:street"),
                "website": safe_website(tags.get("website")),
                "stars": stars,
                "pets_allowed": None if pets is None else bool(pets),
                "source_url": url,
                "fetched_at": payload["fetched_at"],
                "attribution": OSM_ATTRIBUTION,
                "license_url": OSM_LICENSE,
            }
            database.upsert(
                db,
                "hotels",
                {
                    **common,
                    "name": name,
                    "category": tags["tourism"],
                    "latitude": lat,
                    "longitude": lon,
                    "stars": stars,
                    "rating": None,
                    "review_count": None,
                    "website": data["website"],
                    "address": data["address"],
                    "pets_allowed": pets,
                    "payload_json": json.dumps(data, ensure_ascii=False),
                },
            )
            count += 1
        activity = category(tags)
        if activity:
            database.upsert(
                db,
                "activities",
                {
                    **common,
                    "name": name,
                    "category": activity,
                    "latitude": lat,
                    "longitude": lon,
                    "payload_json": json.dumps(
                        {"tags": tags, "attribution": OSM_ATTRIBUTION, "license_url": OSM_LICENSE},
                        ensure_ascii=False,
                    ),
                },
            )
            count += 1
    return count


def import_flights(database, db, payload, source):
    city_id = database.city_id(db, payload["city"])
    for item in payload["quotes"]:
        quote = FlightEstimate.model_validate(item)
        database.upsert(
            db,
            "transport_estimates",
            {
                "id": identity(
                    [
                        city_id,
                        quote.origin,
                        quote.destination,
                        quote.departure_at.isoformat(),
                        quote.return_at.isoformat(),
                        quote.airline,
                    ]
                ),
                "city_id": city_id,
                "origin": quote.origin,
                "destination": quote.destination,
                "departure_at": quote.departure_at.isoformat(),
                "return_at": quote.return_at.isoformat(),
                "airline": quote.airline,
                "currency": "RUB",
                "amount_minor": minor(quote.price.amount),
                "price_basis": quote.price_basis,
                "bookable": 0,
                "source_mode": "snapshot",
                "source_id": source,
                "fetched_at": payload["fetched_at"],
                "valid_until": quote.expires_at.isoformat(),
                "payload_json": quote.model_dump_json(),
            },
        )
    return len(payload["quotes"])


async def airports(client):
    # Travelpayouts public airport directory; no guessed coordinates.
    response = await client.get(AIRPORTS, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Invalid airport directory")
    out = {}
    for row in data:
        try:
            code = row.get("code", "")
            lat = float(row["coordinates"]["lat"])
            lon = float(row["coordinates"]["lon"])
            if (
                len(code) == 3
                and code.isalpha()
                and math.isfinite(lat)
                and math.isfinite(lon)
                and abs(lat) <= 90
                and abs(lon) <= 180
            ):
                out[code] = (lat, lon)
        except (ValueError, TypeError, KeyError):
            continue
    return out


async def sync(database, settings, specs, delay=1.0, weather_only=False):
    stats = {
        "mode": "weather_only" if weather_only else "full",
        "requested": len(specs),
        "geocoded": 0,
        "geocode_cache_hits": 0,
        "weather": 0,
        "marine": 0,
        "osm": 0,
        "flights": 0,
        "routes": 0,
        "passport_reference": 0,
        "failures": {},
        "overpass_state": "available",
    }
    async with httpx.AsyncClient(
        headers={"User-Agent": "OdinTripPrototype/0.5 (+https://github.com/nlgpshelnax/xyinya)"}
    ) as client:
        locations = []
        for spec in specs:
            source = "eu:geo:" + identity(spec[:2])[:12]
            try:
                with database.connect() as db:
                    cached = db.execute(
                        "SELECT d.payload_json FROM destinations d JOIN ingest_sources s "
                        "ON d.source_id=s.id WHERE d.source_id=? "
                        "AND julianday(s.last_success_at)>julianday(?)",
                        (source, (datetime.now(UTC) - timedelta(days=7)).isoformat()),
                    ).fetchone()
                cached_payload = json.loads(cached[0]) if cached else None
                if (
                    cached_payload
                    and cached_payload.get("query") == spec[2]
                    and cached_payload.get("airport_candidate_iata") == spec[3]
                ):
                    ensure_unknown_visa(database, spec[0])
                    locations.append((spec, cached_payload))
                    stats["geocoded"] += 1
                    stats["geocode_cache_hits"] += 1
                    continue
                result = geocode_result(
                    await get_json(
                        client,
                        GEOCODER,
                        params={
                            "name": spec[2],
                            "count": 10,
                            "language": "en",
                            "countryCode": spec[0],
                        },
                    ),
                    spec[0],
                    spec[2],
                )
                if result is None:
                    database.log(source, "empty", stamp(), 0)
                    stats["failures"][spec[1]] = "geocoding_empty"
                else:
                    payload = city_payload(spec, result)
                    database.ingest(source, [payload], database.import_destinations)
                    ensure_unknown_visa(database, spec[0])
                    locations.append((spec, payload))
                    stats["geocoded"] += 1
            except (ProviderFailure, ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                code = getattr(exc, "status", "invalid_response")
                database.log(source, code, stamp(), 0, code)
                stats["failures"][spec[1]] = "geocoding_" + code
            await asyncio.sleep(delay)
        airport_map = {}
        if not weather_only:
            try:
                result = await refresh_passport_index(database, client, [spec[0] for spec in specs])
                stats["passport_reference"] = result["rows"]
            except (ProviderFailure, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                code = getattr(exc, "status", "invalid_response")
                database.log("passport_index_reference", code, stamp(), 0, code)
                stats["failures"]["passport_index_reference"] = code
            try:
                airport_map = await airports(client)
            except (httpx.HTTPError, ValueError):
                airport_map = {}
                stats["failures"]["airports"] = "unavailable"
        osm_errors = {OVERPASS: 0, OVERPASS_SWISS: 0}
        for spec, city in locations:
            key = city["id"]
            now = datetime.now(UTC)
            src = "eu:weather:" + key
            try:
                raw = await get_json(
                    client,
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": city["latitude"],
                        "longitude": city["longitude"],
                        "current": "temperature_2m,snow_depth,precipitation",
                        "daily": "temperature_2m_mean",
                        "forecast_days": 1,
                        "timezone": "UTC",
                    },
                )
                if not isinstance(raw.get("current"), dict):
                    raise ValueError("No current weather")
                daily = raw.get("daily") or {}
                dates, means = daily.get("time") or [], daily.get("temperature_2m_mean") or []
                daily_mean = (
                    means[0]
                    if len(dates) == len(means) == 1 and dates[0] == raw["current"]["time"][:10]
                    else None
                )
                payload = {
                    "city": city["city"],
                    "current": raw["current"],
                    "daily_mean_c": daily_mean,
                    "fetched_at": now.isoformat(),
                    "valid_until": (now + timedelta(hours=2)).isoformat(),
                }
                database.ingest(src, payload, lambda db, p, s: import_current(database, db, p, s))
                stats["weather"] += 1
            except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
                code = getattr(exc, "status", "invalid_response")
                database.log(src, code, stamp(), 0, code)
                stats["failures"][city["city"] + ":weather"] = code
            await asyncio.sleep(delay)
            if weather_only:
                continue
            if city["city"] in COASTAL:
                src = "eu:marine:" + key
                try:
                    raw = await get_json(
                        client,
                        "https://marine-api.open-meteo.com/v1/marine",
                        params={
                            "latitude": city["latitude"],
                            "longitude": city["longitude"],
                            "current": "sea_surface_temperature",
                            "timezone": "UTC",
                        },
                    )
                    lat, lon = float(raw["latitude"]), float(raw["longitude"])
                    if (
                        not math.isfinite(lat)
                        or not math.isfinite(lon)
                        or distance_km(city["latitude"], city["longitude"], lat, lon) > 35
                    ):
                        raise ValueError("Marine grid too far from destination")
                    payload = {
                        "city": city["city"],
                        "current": raw["current"],
                        "grid_latitude": lat,
                        "grid_longitude": lon,
                        "fetched_at": now.isoformat(),
                        "valid_until": (now + timedelta(hours=2)).isoformat(),
                    }
                    database.ingest(
                        src, payload, lambda db, p, s: import_marine(database, db, p, s)
                    )
                    stats["marine"] += 1
                except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
                    code = getattr(exc, "status", "invalid_response")
                    database.log(src, code, stamp(), 0, code)
                    stats["failures"][city["city"] + ":marine"] = code
                await asyncio.sleep(delay)
            src = "eu:osm:" + key
            osm_endpoint = OVERPASS_SWISS if spec[0] == "CH" else OVERPASS
            if osm_errors[osm_endpoint] < 3:
                try:
                    lat, lon = city["latitude"], city["longitude"]
                    selector = f"(around:3000,{lat},{lon})"
                    filters = [
                        '["tourism"~"^(hotel|guest_house|hostel|museum)$"]',
                        '["natural"~"^(beach|coastline|peak)$"]',
                        '["leisure"~"^(beach|spa)$"]',
                        '["piste:type"]',
                        '["aerialway"]',
                        '["historic"="monument"]',
                        '["amenity"~"^(theatre|public_bath)$"]',
                        '["route"="hiking"]',
                    ]
                    q = (
                        "[out:json][timeout:15];("
                        + "".join("nwr" + selector + f + ";" for f in filters)
                        + ");out center 150;"
                    )
                    raw = await get_json(client, osm_endpoint, params={"data": q}, timeout=20)
                    if raw.get("remark") or not isinstance(raw.get("elements"), list):
                        raise ValueError("Invalid Overpass")
                    payload = {
                        "city": city["city"],
                        "country": spec[0],
                        "elements": raw["elements"],
                        "fetched_at": now.isoformat(),
                    }
                    result = database.ingest(
                        src, payload, lambda db, p, s: import_osm(database, db, p, s)
                    )
                    stats["osm"] += result["rows"]
                    osm_errors[osm_endpoint] = 0
                except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
                    osm_errors[osm_endpoint] += 1
                    if osm_errors[osm_endpoint] >= 3:
                        stats["overpass_state"] = "circuit_open"
                    code = getattr(exc, "status", "invalid_response")
                    database.log(src, code, stamp(), 0, code)
                    stats["failures"][city["city"] + ":osm"] = code
                await asyncio.sleep(delay)
            else:
                stats["overpass_state"] = "circuit_open"
            airport = airport_map.get(spec[3])
            if airport:
                try:
                    q = RouteQuery(
                        origin={"latitude": airport[0], "longitude": airport[1]},
                        destination={"latitude": city["latitude"], "longitude": city["longitude"]},
                    )
                    status, data = await OSRM().fetch(client, q)
                    if status == "ok":
                        payload = {
                            "city_id": key,
                            "hotel_id": None,
                            "query": q.model_dump(mode="json"),
                            "data": data,
                            "fetched_at": now.isoformat(),
                            "expires_at": (now + timedelta(hours=24)).isoformat(),
                        }
                        database.ingest(
                            "eu:osrm:" + key,
                            payload,
                            lambda db, p, s: route_rows(database, db, p, s),
                        )
                        stats["routes"] += 1
                except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
                    code = getattr(exc, "status", "invalid_response")
                    database.log("eu:osrm:" + key, code, stamp(), 0, code)
                    stats["failures"][city["city"] + ":osrm"] = code
            else:
                stats["failures"][city["city"] + ":airport"] = "not_found"
            if settings.travelpayouts_token:
                try:
                    raw = await get_json(
                        client,
                        "https://api.travelpayouts.com/v1/prices/cheap",
                        params={"origin": "MOW", "destination": spec[3], "currency": "rub"},
                        headers={"X-Access-Token": settings.travelpayouts_token.get_secret_value()},
                    )
                    if raw.get("success") is not True or not isinstance(raw.get("data"), dict):
                        raise ValueError("Invalid flight response")
                    quotes = []
                    for dest, variants in raw["data"].items():
                        for item in variants.values():
                            q = FlightEstimate(
                                origin="MOW",
                                destination=dest,
                                departure_at=item["departure_at"],
                                return_at=item["return_at"],
                                expires_at=item["expires_at"],
                                price={"amount": item["price"], "currency": "RUB"},
                                airline=item.get("airline"),
                            )
                            if (
                                dest == spec[3]
                                and all(
                                    t.utcoffset() is not None
                                    for t in (q.departure_at, q.return_at, q.expires_at)
                                )
                                and q.expires_at > now
                            ):
                                quotes.append(q.model_dump(mode="json"))
                    if quotes:
                        payload = {
                            "city": city["city"],
                            "quotes": quotes,
                            "fetched_at": now.isoformat(),
                        }
                        database.ingest(
                            "eu:flights:" + key,
                            payload,
                            lambda db, p, s: import_flights(database, db, p, s),
                        )
                        stats["flights"] += len(quotes)
                    else:
                        database.log("eu:flights:" + key, "empty", stamp(), 0)
                except (ProviderFailure, ValueError, KeyError, TypeError) as exc:
                    code = getattr(exc, "status", "invalid_response")
                    database.log("eu:flights:" + key, code, stamp(), 0, code)
                    stats["failures"][city["city"] + ":flights"] = code
            else:
                stats["failures"][city["city"] + ":flights"] = "not_configured"
    return stats
