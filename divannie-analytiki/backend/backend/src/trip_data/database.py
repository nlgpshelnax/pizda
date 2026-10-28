"""Indexed relational catalog; imports are atomic per source and idempotent by content hash."""

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trip_data.components import ComponentCatalog
from trip_data.hotels import HotelSearch, HotelSearchResult, HotelSnapshot, RealHotel
from trip_data.models import Bundle

PUBLIC_TABLES = {
    "activity_counts",
    "destinations",
    "hotels",
    "hotel_quotes",
    "transport_quotes",
    "transfer_quotes",
    "transport_estimates",
    "weather",
    "routes",
    "activities",
    "guests",
    "calendar_dates",
    "budget_statistics",
    "visa_rules",
    "ingest_sources",
    "ingest_runs",
    "hotel_catalog",
}


def stamp():
    return datetime.now(UTC).isoformat()


def identity(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def percentile_minor(values, percentile):
    """Linear interpolation, rounded half up to the nearest minor unit."""
    if not values:
        raise ValueError("A percentile needs at least one value")
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * Decimal(str(percentile))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    result = Decimal(ordered[lower]) + (
        Decimal(ordered[upper] - ordered[lower]) * (position - lower)
    )
    return int(result.quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def minor(amount):
    value = Decimal(str(amount)) * 100
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        raise ValueError("Price must have nonnegative minor units")
    return int(value)


class CatalogDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(Path(__file__).with_name("sql").joinpath("catalog.sql").read_text())
            db.execute("INSERT OR IGNORE INTO catalog_schema VALUES(1,?)", (stamp(),))
            additions = {
                "hotels": {
                    "closest_airport": "TEXT",
                    "distance_to_airport_m": "REAL",
                    "check_in_time": "TEXT",
                    "check_out_time": "TEXT",
                    "pets_allowed": "INTEGER",
                    "breakfast": "INTEGER",
                    "all_inclusive": "INTEGER",
                },
                "transport_quotes": {
                    "duration_minutes": "INTEGER",
                    "stops": "INTEGER",
                    "carrier": "TEXT",
                },
                "weather": {"avg_c": "REAL", "sea_temp_c": "REAL", "snow_depth_cm": "REAL"},
                "budget_statistics": {
                    "component": "TEXT NOT NULL DEFAULT 'hotel'",
                    "direction": "TEXT",
                    "avg_minor": "INTEGER",
                },
                "visa_rules": {"notes": "TEXT"},
            }
            for table, fields in additions.items():
                existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                for column, kind in fields.items():
                    if column not in existing:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
            db.execute("INSERT OR IGNORE INTO catalog_schema VALUES(2,?)", (stamp(),))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def upsert(db, table, row):
        if table != "ingest_sources" and "source_id" in row:
            existing = db.execute(
                f"SELECT source_id FROM {table} WHERE id=?", (row["id"],)
            ).fetchone()
            if existing and existing[0] != row["source_id"]:
                raise ValueError("Object ID is owned by another source")
        columns = list(row)
        sql = (
            f"INSERT INTO {table} ({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) "
            f"ON CONFLICT(id) DO UPDATE SET "
            + ",".join(f"{c}=excluded.{c}" for c in columns if c != "id")
        )
        db.execute(sql, tuple(row.values()))

    def ingest(self, source, payload, importer):
        started = stamp()
        fingerprint = identity({"import_revision": 2, "payload": payload})
        with self.connect() as db:
            previous = db.execute(
                "SELECT fingerprint FROM ingest_sources WHERE id=?", (source,)
            ).fetchone()
        if previous and previous[0] == fingerprint:
            self.log(source, "skipped", started, 0)
            return {"source": source, "status": "skipped", "rows": 0}
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self.upsert(
                    db,
                    "ingest_sources",
                    dict(id=source, fingerprint=fingerprint, last_success_at=stamp(), row_count=0),
                )
                count = importer(db, payload, source)
                db.execute("UPDATE ingest_sources SET row_count=? WHERE id=?", (count, source))
                db.execute(
                    "INSERT INTO ingest_runs(source_id,status,started_at,finished_at,row_count) "
                    "VALUES(?,?,?,?,?)",
                    (source, "ok", started, stamp(), count),
                )
            return {"source": source, "status": "ok", "rows": count}
        except Exception as exc:
            self.log(source, "failed", started, 0, type(exc).__name__)
            raise

    def log(self, source, status, started, count, error=None):
        with self.connect() as db:
            db.execute(
                "INSERT INTO ingest_runs(source_id,status,started_at,finished_at,"
                "row_count,error_code) "
                "VALUES(?,?,?,?,?,?)",
                (source, status, started, stamp(), count, error),
            )

    @staticmethod
    def city_id(db, city):
        row = db.execute("SELECT id FROM destinations WHERE city=?", (city,)).fetchone()
        if not row:
            raise ValueError("Unknown destination")
        return row[0]

    def import_destinations(self, db, payload, source):
        for value in payload:
            self.upsert(
                db,
                "destinations",
                dict(
                    id=value["id"],
                    city=value["city"],
                    country=value["country"],
                    latitude=value["latitude"],
                    longitude=value["longitude"],
                    timezone=value["timezone"],
                    source_id=source,
                    payload_json=json.dumps(value, ensure_ascii=False),
                ),
            )
        return len(payload)

    def import_hotels(self, db, payload, source):
        snapshot = HotelSnapshot.model_validate(payload)
        self.upsert(
            db,
            "catalog_metadata",
            dict(
                id=source,
                payload_json=json.dumps(snapshot.model_dump(mode="json", exclude={"hotels"})),
            ),
        )
        db.execute("UPDATE hotels SET active=0 WHERE source_id=?", (source,))
        for hotel in snapshot.hotels:
            self.upsert(
                db,
                "hotels",
                dict(
                    id=hotel.id,
                    city_id=self.city_id(db, hotel.city),
                    name=hotel.name,
                    category=hotel.category,
                    latitude=hotel.latitude,
                    longitude=hotel.longitude,
                    stars=hotel.stars,
                    rating=None,
                    review_count=None,
                    website=hotel.website,
                    address=hotel.address,
                    source_mode="snapshot",
                    source_id=source,
                    source_url=hotel.source_url,
                    fetched_at=hotel.fetched_at.isoformat(),
                    active=1,
                    payload_json=hotel.model_dump_json(),
                ),
            )
        return len(snapshot.hotels)

    @staticmethod
    def guest(db, request):
        guests = request.guests
        key = identity(guests.model_dump())
        db.execute(
            "INSERT OR IGNORE INTO guests(id,adults,children_ages_json,pets) VALUES(?,?,?,?)",
            (key, guests.adults, json.dumps(guests.children_ages), guests.pets),
        )
        return key

    @staticmethod
    def dates(db, check_in, check_out):
        current = check_in
        while current <= check_out:
            season = (
                "winter"
                if current.month in (12, 1, 2)
                else "spring"
                if current.month < 6
                else "summer"
                if current.month < 9
                else "autumn"
            )
            db.execute(
                "INSERT OR IGNORE INTO calendar_dates VALUES(?,?,?,?,?,?)",
                (
                    current.isoformat(),
                    current.year,
                    current.month,
                    current.weekday(),
                    int(current.weekday() >= 5),
                    season,
                ),
            )
            current += timedelta(days=1)

    def import_components(self, db, payload, source):
        catalog = ComponentCatalog.model_validate(payload)
        if any(
            q.provenance.kind != "mock"
            for q in (*catalog.hotels, *catalog.transport, *catalog.transfers)
        ):
            raise ValueError("Component demo catalog requires explicitly synthetic quotes")
        db.execute("UPDATE hotels SET active=0 WHERE source_id=?", (source,))
        for prop in catalog.properties:
            self.upsert(
                db,
                "hotels",
                dict(
                    id=prop.id,
                    city_id=self.city_id(db, prop.city),
                    name=prop.name,
                    category="hotel",
                    stars=prop.stars,
                    rating=prop.rating,
                    review_count=prop.review_count,
                    source_mode="mock",
                    source_id=source,
                    fetched_at=stamp(),
                    active=1,
                    payload_json=prop.model_dump_json(),
                ),
            )
        # Clear only this source's derived quotes inside the same transaction.
        for table in ("hotel_quotes", "transport_quotes", "transfer_quotes"):
            db.execute(f"DELETE FROM {table} WHERE source_id=?", (source,))
        for q in catalog.hotels:
            guest_id = self.guest(db, q.scope)
            self.dates(db, q.scope.check_in, q.scope.check_out)
            self.upsert(
                db,
                "hotel_quotes",
                dict(
                    id=q.id,
                    hotel_id=q.property_id,
                    guest_id=guest_id,
                    check_in=q.scope.check_in.isoformat(),
                    check_out=q.scope.check_out.isoformat(),
                    currency=q.price.currency,
                    amount_minor=minor(q.price.amount),
                    price_basis=q.price_basis,
                    breakfast=q.breakfast,
                    pets_allowed=q.pets_allowed,
                    max_guests=q.max_guests,
                    mandatory_fees_known=q.mandatory_fees_known,
                    source_mode=q.provenance.kind,
                    source_id=source,
                    fetched_at=q.provenance.fetched_at.isoformat(),
                    valid_until=q.provenance.valid_until.isoformat(),
                    payload_json=q.model_dump_json(),
                ),
            )
        for q in catalog.transport:
            t = q.transport
            self.upsert(
                db,
                "transport_quotes",
                dict(
                    id=q.id,
                    city_id=self.city_id(db, q.scope.destination),
                    guest_id=self.guest(db, q.scope),
                    direction=q.direction,
                    mode=t.mode,
                    duration_minutes=int((t.arrival_at - t.departure_at).total_seconds() / 60),
                    stops=len(t.segments) - 1 if t.segments else None,
                    carrier=t.segments[0].carrier if t.segments else None,
                    origin=t.origin,
                    destination=t.destination,
                    departure_at=t.departure_at.isoformat(),
                    arrival_at=t.arrival_at.isoformat(),
                    currency=t.price.currency,
                    amount_minor=minor(t.price.amount),
                    price_basis=t.price_basis,
                    source_mode=q.provenance.kind,
                    source_id=source,
                    fetched_at=q.provenance.fetched_at.isoformat(),
                    valid_until=q.provenance.valid_until.isoformat(),
                    payload_json=q.model_dump_json(),
                ),
            )
        for q in catalog.transfers:
            t = q.transfer
            self.upsert(
                db,
                "transfer_quotes",
                dict(
                    id=q.id,
                    hotel_id=q.hotel_property_id,
                    guest_id=self.guest(db, q.scope),
                    direction=q.direction,
                    duration_minutes=t.duration_minutes,
                    capacity=t.capacity,
                    child_seats=t.child_seats,
                    currency=t.price.currency,
                    amount_minor=minor(t.price.amount),
                    price_basis=t.price_basis,
                    source_mode=q.provenance.kind,
                    source_id=source,
                    fetched_at=q.provenance.fetched_at.isoformat(),
                    valid_until=q.provenance.valid_until.isoformat(),
                    payload_json=q.model_dump_json(),
                ),
            )
        return (
            len(catalog.properties)
            + len(catalog.hotels)
            + len(catalog.transport)
            + len(catalog.transfers)
        )

    def import_activities(self, db, payload, source):
        from trip_data.context_models import Coordinates

        db.execute("UPDATE activities SET active=0 WHERE source_id=?", (source,))
        for value in payload:
            Coordinates(latitude=value["latitude"], longitude=value["longitude"])
            if value["category"] not in (
                "museum",
                "attraction",
                "restaurant",
                "beach",
                "park",
                "ski",
            ):
                raise ValueError("Unknown activity category")
            self.upsert(
                db,
                "activities",
                dict(
                    id=value["id"],
                    city_id=self.city_id(db, value["city"]),
                    name=value["name"],
                    category=value["category"],
                    latitude=value["latitude"],
                    longitude=value["longitude"],
                    source_mode="snapshot",
                    source_id=source,
                    source_url=value["source_url"],
                    fetched_at=value["fetched_at"],
                    active=1,
                    payload_json=json.dumps(value, ensure_ascii=False),
                ),
            )
        return len(payload)

    def import_context_fixtures(self, db, payload, source):
        db.execute("DELETE FROM context_fixtures WHERE source_id=?", (source,))
        for entry in payload:
            self.upsert(
                db,
                "context_fixtures",
                dict(
                    id=identity([entry["provider"], entry["query"]]),
                    provider=entry["provider"],
                    query_hash=identity(entry["query"]),
                    source_id=source,
                    data_json=json.dumps(entry["data"], ensure_ascii=False),
                ),
            )
        return len(payload)

    def mock_context(self, provider, query):
        with self.connect() as db:
            row = db.execute(
                "SELECT data_json FROM context_fixtures WHERE provider=? AND query_hash=?",
                (provider, identity(query)),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def import_bundles(self, db, payload, source):
        bundles = [Bundle.model_validate(v) for v in payload]
        if any(b.provenance.kind != "mock" for b in bundles):
            raise ValueError("Legacy demo search only accepts synthetic bundles")
        db.execute("DELETE FROM bundles WHERE source_id=?", (source,))
        for b in bundles:
            self.upsert(
                db,
                "bundles",
                dict(
                    id=b.id,
                    destination=b.request.destination,
                    source_mode="mock",
                    source_id=source,
                    payload_json=b.model_dump_json(),
                ),
            )
        return len(bundles)

    def load_files(self, settings):
        sources = [
            ("destinations", settings.knowledge_path, self.import_destinations),
            ("osm_hotels", settings.hotel_snapshot_path, self.import_hotels),
            ("osm_activities", settings.activities_snapshot_path, self.import_activities),
            ("components", settings.component_catalog_path, self.import_components),
            ("bundles", settings.catalog_path, self.import_bundles),
            ("context_fixtures", settings.context_fixture_path, self.import_context_fixtures),
        ]
        results = []
        for name, path, importer in sources:
            try:
                payload = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                self.log(name, "failed", stamp(), 0, type(exc).__name__)
                results.append({"source": name, "status": "failed", "rows": 0})
                continue
            try:
                results.append(self.ingest(name, payload, importer))
            except (KeyError, TypeError, ValueError, sqlite3.Error):
                results.append({"source": name, "status": "failed", "rows": 0})
        if any(r["status"] == "ok" for r in results):
            self.populate_auxiliary()
        return results

    def populate_auxiliary(self):
        with self.connect() as db:
            for row in db.execute("SELECT DISTINCT country FROM destinations").fetchall():
                country = row[0]
                value = dict(
                    passport_country="RU",
                    destination_country=country,
                    passport_type="ordinary",
                    purpose="tourism",
                    visa_status="unknown",
                )
                self.upsert(
                    db,
                    "visa_rules",
                    dict(
                        id=identity(value),
                        **value,
                        source_mode="unknown",
                        payload_json=json.dumps(value),
                    ),
                )
            db.execute("DELETE FROM budget_statistics")
            rows = db.execute(
                "SELECT q.*,h.city_id FROM hotel_quotes q JOIN hotels h ON h.id=q.hotel_id"
            ).fetchall()
            groups = {}
            for row in rows:
                nights = (
                    date.fromisoformat(row["check_out"]) - date.fromisoformat(row["check_in"])
                ).days
                key = (
                    row["city_id"],
                    int(row["check_in"][5:7]),
                    row["guest_id"],
                    nights,
                    row["currency"],
                    row["source_mode"],
                )
                groups.setdefault(key, []).append(row["amount_minor"])
            for key, values in groups.items():
                values.sort()
                city, month, guest, nights, currency, mode = key
                self.upsert(
                    db,
                    "budget_statistics",
                    dict(
                        id=identity(key),
                        city_id=city,
                        month=month,
                        guest_id=guest,
                        nights=nights,
                        currency=currency,
                        source_mode=mode,
                        price_basis="hotel_stay_all_guests",
                        sample_count=len(values),
                        min_minor=values[0],
                        p25_minor=percentile_minor(values, "0.25"),
                        median_minor=percentile_minor(values, "0.5"),
                        p75_minor=percentile_minor(values, "0.75"),
                        max_minor=values[-1],
                        component="hotel",
                        direction=None,
                        avg_minor=int(
                            (Decimal(sum(values)) / len(values)).quantize(
                                Decimal("1"), rounding="ROUND_HALF_UP"
                            )
                        ),
                        computed_at=stamp(),
                    ),
                )

    def summary(self):
        with self.connect() as db:
            return {
                "schema_version": db.execute("SELECT max(version) FROM catalog_schema").fetchone()[
                    0
                ],
                "tables": {
                    table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    for table in sorted(PUBLIC_TABLES)
                },
                "hotel_modes": {
                    r[0]: r[1]
                    for r in db.execute(
                        "SELECT source_mode,count(*) FROM hotels WHERE active=1 "
                        "GROUP BY source_mode"
                    )
                },
            }

    def rows(self, table, *, city=None, source_mode=None, limit=50, offset=0):
        if table not in PUBLIC_TABLES or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Unsupported table or pagination")
        with self.connect() as db:
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            clauses, params = [], []
            if city is not None:
                if "city_id" in columns:
                    clauses.append("city_id=(SELECT id FROM destinations WHERE city=?)")
                elif "city" in columns:
                    clauses.append("city=?")
                else:
                    raise ValueError("This table has no city dimension")
                params.append(city)
            if source_mode is not None:
                if "source_mode" not in columns:
                    raise ValueError("This table has no source_mode dimension")
                clauses.append("source_mode=?")
                params.append(source_mode)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = db.execute(f"SELECT count(*) FROM {table}" + where, params).fetchone()[0]
            records = [
                dict(r)
                for r in db.execute(
                    f"SELECT * FROM {table}" + where + " LIMIT ? OFFSET ?", [*params, limit, offset]
                )
            ]
            for row in records:
                if "payload_json" in row:
                    row["data"] = json.loads(row.pop("payload_json"))
            return {
                "table": table,
                "total": total,
                "limit": limit,
                "offset": offset,
                "rows": records,
            }

    def component_catalog(self):
        with self.connect() as db:

            def payloads(table):
                return [
                    json.loads(r[0])
                    for r in db.execute(
                        f"SELECT payload_json FROM {table} WHERE source_id=?", ("components",)
                    )
                ]

            return ComponentCatalog.model_validate(
                dict(
                    properties=payloads("hotels"),
                    hotels=payloads("hotel_quotes"),
                    transport=payloads("transport_quotes"),
                    transfers=payloads("transfer_quotes"),
                )
            )

    def search_hotels(self, query: HotelSearch):
        with self.connect() as db:
            cities = [r[0] for r in db.execute("SELECT city FROM destinations")]
            canonical = next(
                (c for c in cities if c.casefold() == query.city.casefold()), query.city
            )
            rows = db.execute(
                "SELECT h.payload_json FROM hotels h JOIN destinations d ON d.id=h.city_id "
                "WHERE h.active=1 AND (h.source_id=? OR h.source_id LIKE ?) AND d.city=?",
                ("osm_hotels", "eu:osm:%", canonical),
            ).fetchall()
            row = db.execute(
                "SELECT payload_json FROM catalog_metadata WHERE id=?", ("osm_hotels",)
            ).fetchone()
            eu_row = db.execute(
                "SELECT s.last_success_at FROM ingest_sources s JOIN destinations d "
                "ON s.id='eu:osm:' || d.id WHERE d.city=?",
                (canonical,),
            ).fetchone()
        metadata = json.loads(row[0]) if row else {}
        hotels = [RealHotel.model_validate_json(r[0]) for r in rows]
        hotels = [
            h
            for h in hotels
            if (query.name is None or query.name.casefold() in h.name.casefold())
            and (query.category is None or h.category == query.category)
            and (query.min_stars is None or h.stars is not None and h.stars >= query.min_stars)
        ]
        coverage = metadata.get("coverage", {}).get(canonical)
        fetched = (
            datetime.fromisoformat(eu_row[0])
            if eu_row
            else datetime.fromisoformat(metadata["fetched_at"])
            if metadata
            else datetime.fromtimestamp(0, UTC)
        )
        return HotelSearchResult(
            status="out_of_coverage"
            if coverage is None and not eu_row
            else "ok"
            if hotels
            else "empty",
            fetched_at=fetched,
            stale=datetime.now(UTC) - fetched > timedelta(days=7),
            total_matches=len(hotels),
            hotels=hotels[: query.limit],
            coverage_bbox=coverage,
            warnings=[
                "OpenStreetMap snapshot; small sampled city area; metadata may be outdated",
                "No room prices, availability or review scores are confirmed; "
                "OSM pet tags may be outdated",
            ],
        )

    def migrate_legacy(self, directory: Path):
        groups = [
            (directory / "state.sqlite3", ("plans", "orders", "services")),
            (directory / "provider-cache.sqlite3", ("provider_cache", "observations", "snapshots")),
        ]
        migrated = {}
        for path, tables in groups:
            if not path.exists() or path.resolve() == self.path.resolve():
                continue
            with (
                sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as old,
                self.connect() as db,
            ):
                available = {
                    r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                existing = {
                    r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                common = [t for t in tables if t in available and t in existing]
                if any(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in common):
                    continue
                db.execute("BEGIN IMMEDIATE")
                for table in common:
                    fields = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                    columns = [
                        r[1] for r in old.execute(f"PRAGMA table_info({table})") if r[1] in fields
                    ]
                    rows = old.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
                    db.executemany(
                        f"INSERT INTO {table}({','.join(columns)}) "
                        f"VALUES({','.join('?' for _ in columns)})",
                        rows,
                    )
                    migrated[table] = len(rows)
        return migrated


class DatabaseBundles:
    def __init__(self, database):
        self.database = database

    @property
    def bundles(self):
        with self.database.connect() as db:
            return [
                Bundle.model_validate_json(r[0])
                for r in db.execute("SELECT payload_json FROM bundles")
            ]

    def search(self, request):
        with self.database.connect() as db:
            return [
                Bundle.model_validate_json(r[0])
                for r in db.execute(
                    "SELECT payload_json FROM bundles WHERE destination=?", (request.destination,)
                )
            ]


class DatabaseBundleProvider:
    name = "demo-catalog"
    data_mode = "mock"

    def __init__(self, database):
        self.database = database
        self.catalog = DatabaseBundles(database)

    @property
    def revision(self):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT fingerprint FROM ingest_sources WHERE id=?", ("bundles",)
            ).fetchone()
            return row[0] if row else "empty"

    async def search(self, request):
        return self.catalog.search(request)
