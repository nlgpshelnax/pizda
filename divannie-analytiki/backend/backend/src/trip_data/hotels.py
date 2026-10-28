"""Real accommodation metadata. A property listing is never a room-price quote."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field, model_validator

AREAS = {
    "Сочи": {"key": "sochi", "country": "RU", "bbox": [39.727, 43.575, 39.737, 43.585]},
    "Казань": {"key": "kazan", "country": "RU", "bbox": [49.105, 55.79, 49.117, 55.80]},
    "Дубай": {"key": "dubai", "country": "AE", "bbox": [55.27, 25.195, 55.282, 25.205]},
    "Хургада": {"key": "hurghada", "country": "EG", "bbox": [33.836, 27.22, 33.848, 27.23]},
}
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "https://opendatacommons.org/licenses/odbl/1-0/"


class RealHotel(BaseModel):
    id: str
    name: str
    city: str
    country: str
    category: Literal["hotel", "guest_house", "hostel"]
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    coordinate_kind: Literal["mapped_point", "geometry_centroid"]
    address: str | None = None
    website: str | None = None
    stars: int | None = Field(default=None, ge=0, le=5)
    rating: None = None
    review_count: None = None
    price: None = None
    availability: Literal["unknown"] = "unknown"
    pets_allowed: bool | None = None
    breakfast: None = None
    source_url: str
    source_updated_at: datetime | None = None
    fetched_at: datetime
    attribution: str = OSM_ATTRIBUTION
    license_url: str = OSM_LICENSE
    bookable: Literal[False] = False


class HotelSnapshot(BaseModel):
    schema_version: Literal[1] = 1
    fetched_at: datetime
    attribution: str = OSM_ATTRIBUTION
    license_url: str = OSM_LICENSE
    coverage: dict[str, list[float]]
    hotels: list[RealHotel]

    @model_validator(mode="after")
    def unique_ids(self) -> "HotelSnapshot":
        if len({h.id for h in self.hotels}) != len(self.hotels):
            raise ValueError("Duplicate OSM object IDs")
        if self.fetched_at.utcoffset() is None:
            raise ValueError("Snapshot timestamp needs timezone")
        return self


class HotelSearch(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=100)
    min_stars: int | None = Field(default=None, ge=1, le=5)
    category: Literal["hotel", "guest_house", "hostel"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class HotelSearchResult(BaseModel):
    source_mode: Literal["snapshot"] = "snapshot"
    provider: Literal["openstreetmap"] = "openstreetmap"
    status: Literal["ok", "empty", "out_of_coverage"]
    fetched_at: datetime
    stale: bool
    total_matches: int
    hotels: list[RealHotel]
    coverage_bbox: list[float] | None
    warnings: list[str]


def safe_website(value: str | None) -> str | None:
    if not value:
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme in ("http", "https")
            and url.hostname
            and not url.username
            and not url.password
        ):
            return value[:1000]
    except ValueError:
        pass
    return None


def osm_objects(xml: str, city: str):
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise ValueError("XML DTD/entities are not supported")
    area = AREAS[city]
    root = ET.fromstring(xml)
    nodes = {
        n.attrib["id"]: (float(n.attrib["lat"]), float(n.attrib["lon"]))
        for n in root.findall("node")
    }
    ways = {
        w.attrib["id"]: [nd.attrib["ref"] for nd in w.findall("nd")] for w in root.findall("way")
    }
    west, south, east, north = area["bbox"]
    for obj in root:
        if obj.tag not in ("node", "way", "relation"):
            continue
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in obj.findall("tag")}
        if not (
            tags.get("tourism") in ("hotel", "guest_house", "hostel", "museum", "attraction")
            or tags.get("amenity") == "restaurant"
            or tags.get("natural") == "beach"
            or tags.get("leisure") == "park"
            or tags.get("piste:type") == "downhill"
        ):
            continue
        if obj.tag == "node":
            latitude, longitude = nodes[obj.attrib["id"]]
            coordinate_kind = "mapped_point"
        else:
            refs = (
                ways.get(obj.attrib["id"], [])
                if obj.tag == "way"
                else [
                    ref
                    for member in obj.findall("member")
                    if member.attrib.get("type") == "way"
                    for ref in ways.get(member.attrib["ref"], [])
                ]
            )
            points = [nodes[ref] for ref in set(refs) if ref in nodes]
            if not points:
                continue
            latitude = sum(p[0] for p in points) / len(points)
            longitude = sum(p[1] for p in points) / len(points)
            coordinate_kind = "geometry_centroid"
        if south <= latitude <= north and west <= longitude <= east:
            yield obj, tags, latitude, longitude, coordinate_kind


def hotels_from_objects(objects, city: str, fetched_at: datetime) -> list[RealHotel]:
    hotels = []
    for obj, tags, latitude, longitude, coordinate_kind in objects:
        category = tags.get("tourism")
        name = tags.get("name:ru") or tags.get("name") or tags.get("name:en")
        if category not in ("hotel", "guest_house", "hostel") or not name:
            continue
        stars = tags.get("stars", "")
        address = ", ".join(filter(None, (tags.get("addr:street"), tags.get("addr:housenumber"))))
        hotels.append(
            RealHotel(
                id=f"osm:{obj.tag}:{obj.attrib['id']}",
                name=name[:200],
                city=city,
                country=AREAS[city]["country"],
                category=category,
                latitude=latitude,
                longitude=longitude,
                coordinate_kind=coordinate_kind,
                address=address[:500] or None,
                website=safe_website(tags.get("website") or tags.get("contact:website")),
                stars=int(stars) if stars.isdigit() and 0 <= int(stars) <= 5 else None,
                source_url=f"https://www.openstreetmap.org/{obj.tag}/{obj.attrib['id']}",
                source_updated_at=obj.attrib.get("timestamp"),
                fetched_at=fetched_at,
            )
        )
    return hotels


def parse_osm(xml: str, city: str, fetched_at: datetime) -> list[RealHotel]:
    return hotels_from_objects(osm_objects(xml, city), city, fetched_at)


def activities_from_objects(objects, city: str, fetched_at: datetime):
    result = []
    for obj, tags, lat, lon, _ in objects:
        category = next(
            (
                name
                for key, value, name in (
                    ("tourism", "museum", "museum"),
                    ("tourism", "attraction", "attraction"),
                    ("amenity", "restaurant", "restaurant"),
                    ("natural", "beach", "beach"),
                    ("leisure", "park", "park"),
                    ("piste:type", "downhill", "ski"),
                )
                if tags.get(key) == value
            ),
            None,
        )
        if category is not None:
            name = tags.get("name:ru") or tags.get("name") or tags.get("name:en")
            result.append(
                dict(
                    id=f"osm:{obj.tag}:{obj.attrib['id']}",
                    city=city,
                    name=name[:200] if name else None,
                    category=category,
                    latitude=lat,
                    longitude=lon,
                    source_url=f"https://www.openstreetmap.org/{obj.tag}/{obj.attrib['id']}",
                    fetched_at=fetched_at.isoformat(),
                    attribution=OSM_ATTRIBUTION,
                    license_url=OSM_LICENSE,
                )
            )
    return result


async def refresh_snapshots(output: Path, activities_output: Path, from_local: Path | None = None):
    import asyncio

    import httpx

    fetched = datetime.now(UTC)
    hotels, activities = [], []
    async with httpx.AsyncClient(
        headers={"User-Agent": "OdinTripPrototype/0.4 (+https://github.com/nlgpshelnax/xyinya)"}
    ) as client:
        for city, area in AREAS.items():
            if from_local:
                xml = (from_local / (area["key"] + ".xml")).read_text()
            else:
                response = await client.get(
                    "https://api.openstreetmap.org/api/0.6/map",
                    params={"bbox": ",".join(map(str, area["bbox"]))},
                    timeout=30,
                )
                response.raise_for_status()
                xml = response.text
                await asyncio.sleep(1)
            objects = list(osm_objects(xml, city))
            batch = hotels_from_objects(objects, city, fetched)
            if not batch:
                raise ValueError("No named hotels; keep the previous snapshot")
            hotels.extend(batch)
            activities.extend(activities_from_objects(objects, city, fetched))
    snapshot = HotelSnapshot(
        fetched_at=fetched, coverage={c: a["bbox"] for c, a in AREAS.items()}, hotels=hotels
    )
    for path, content in (
        (output, snapshot.model_dump_json(indent=2)),
        (activities_output, json.dumps(activities, ensure_ascii=False, indent=2)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(content + "\n")
        temporary.replace(path)
    return {"hotels": len(hotels), "activities": len(activities)}


def search_hotels(query: HotelSearch, path: Path, now: datetime | None = None) -> HotelSearchResult:
    snapshot = HotelSnapshot.model_validate_json(path.read_text())
    hotels = [
        h
        for h in snapshot.hotels
        if h.city.casefold() == query.city.casefold()
        and (query.name is None or query.name.casefold() in h.name.casefold())
        and (query.category is None or h.category == query.category)
        and (query.min_stars is None or h.stars is not None and h.stars >= query.min_stars)
    ]
    coverage = next(
        (v for k, v in snapshot.coverage.items() if k.casefold() == query.city.casefold()), None
    )
    return HotelSearchResult(
        status="out_of_coverage" if coverage is None else "ok" if hotels else "empty",
        fetched_at=snapshot.fetched_at,
        stale=(now or datetime.now(UTC)) - snapshot.fetched_at > timedelta(days=7),
        total_matches=len(hotels),
        hotels=hotels[: query.limit],
        coverage_bbox=coverage,
        warnings=[
            "OpenStreetMap metadata may be incomplete or outdated; map stars are unverified",
            "Coverage is a small sampled city area, not every hotel in the city",
            "No room prices, occupancy, pets policy or availability are confirmed",
        ],
    )
