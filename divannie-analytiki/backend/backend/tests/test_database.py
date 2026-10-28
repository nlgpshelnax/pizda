import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.database import CatalogDB, minor
from trip_data.hotels import HotelSearch, parse_osm, safe_website
from trip_data.main import create_app
from trip_data.plan_models import Plan
from trip_data.state import StateStore

REAL_HOTEL_COUNT = len(json.loads(Path("data/hotels/osm-properties.json").read_text())["hotels"])
REAL_ACTIVITY_COUNT = len(json.loads(Path("data/hotels/osm-activities.json").read_text()))
SOCHI_COUNT = sum(
    h["city"] == "Сочи"
    for h in json.loads(Path("data/hotels/osm-properties.json").read_text())["hotels"]
)


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "travel.sqlite3")


@pytest.fixture
def database(settings):
    db = CatalogDB(settings.database_path)
    db.load_files(settings)
    return db


def test_complete_schema_real_and_mock_separated(database):
    result = database.summary()
    assert result["hotel_modes"] == {"mock": 4, "snapshot": REAL_HOTEL_COUNT}
    assert result["tables"]["activities"] == REAL_ACTIVITY_COUNT
    assert result["tables"]["hotel_quotes"] == 6
    assert result["tables"]["transfer_quotes"] == 12
    assert result["tables"]["visa_rules"] == 3
    with database.connect() as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute(
                "SELECT count(*) FROM hotels WHERE source_mode=? AND rating IS NOT NULL",
                ("snapshot",),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM hotel_quotes q JOIN hotels h ON q.hotel_id=h.id "
                "WHERE h.source_mode=?",
                ("snapshot",),
            ).fetchone()[0]
            == 0
        )
        guest = db.execute("SELECT * FROM guests WHERE children_count=1").fetchone()
        assert guest["total_guests"] == 3
        budget = db.execute(
            "SELECT * FROM budget_statistics WHERE city_id=? AND sample_count=2", ("sochi",)
        ).fetchone()
        assert budget["median_minor"] == 3150000


def test_repeat_load_is_idempotent_and_indexes_exist(database, settings):
    before = database.summary()["tables"]
    assert all(row["status"] == "skipped" for row in database.load_files(settings))
    after = database.summary()["tables"]
    for table in ("hotels", "activities", "hotel_quotes", "guests", "bundles", "budget_statistics"):
        if table in before:
            assert before[table] == after[table]
    with database.connect() as db:
        assert "hotels_city_stars" in {r[1] for r in db.execute("PRAGMA index_list(hotels)")}


def test_source_failure_rolls_back_previous_records(database):
    def broken(db, payload, source):
        db.execute("UPDATE hotels SET name=? WHERE source_id=?", ("CORRUPTED", "osm_hotels"))
        raise ValueError("bad data")

    with pytest.raises(ValueError):
        database.ingest("osm_hotels", {"changed": True}, broken)
    with database.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM hotels WHERE name=?", ("CORRUPTED",)).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT status FROM ingest_runs ORDER BY id DESC LIMIT 1").fetchone()[0]
            == "failed"
        )
    assert database.search_hotels(HotelSearch(city="Сочи")).hotels


def test_invalid_file_keeps_previous_source(database, settings, tmp_path):
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{bad json")
    settings.hotel_snapshot_path = corrupt
    result = database.load_files(settings)
    assert next(r for r in result if r["source"] == "osm_hotels")["status"] == "failed"
    assert database.summary()["hotel_modes"]["snapshot"] == REAL_HOTEL_COUNT


def test_atomic_fk_failure_and_safe_queries(database):
    with database.connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO hotels(id,city_id,name,category,source_mode,source_id,"
            "fetched_at,payload_json) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("bad", "unknown", "name", "hotel", "mock", "components", "now", "{}"),
        )
    for table in ("plans", "provider_cache", "hotels; DROP TABLE hotels;--"):
        with pytest.raises(ValueError):
            database.rows(table)
    assert database.rows("hotels", city="' OR 1=1--")["total"] == 0


def test_hotel_snapshot_queries_and_unknown_prices(database):
    result = database.search_hotels(HotelSearch(city="сочи", limit=2))
    assert result.status == "ok" and len(result.hotels) == 2
    assert result.total_matches == SOCHI_COUNT
    assert result.fetched_at.year > 2020
    for hotel in result.hotels:
        assert hotel.price is None and hotel.rating is None
        assert hotel.availability == "unknown" and not hotel.bookable
        assert hotel.source_url.startswith("https://www.openstreetmap.org/")
    high = database.search_hotels(HotelSearch(city="Казань", min_stars=5))
    assert all(h.stars >= 5 for h in high.hotels)
    assert database.search_hotels(HotelSearch(city="no-such-city")).status == "out_of_coverage"


def test_runtime_reads_database_without_json_reads(settings, monkeypatch):
    with TestClient(create_app(settings)) as client:

        def no_files(*args, **kwargs):
            raise AssertionError("request must query the database")

        monkeypatch.setattr(Path, "read_text", no_files)
        assert client.get("/api/v1/catalog").json()["hotel_modes"]["snapshot"] == REAL_HOTEL_COUNT
        assert client.post("/api/v1/hotels/search", json={"city": "Сочи"}).json()["hotels"]
        payload = {
            "origin": "Москва",
            "destination": "Сочи",
            "check_in": "2026-11-10",
            "check_out": "2026-11-15",
            "guests": {"adults": 2},
        }
        for endpoint in ("search", "compose"):
            r = client.post(
                "/api/v1/bundles/" + endpoint, json={"request": payload, "plan_version": 1}
            )
            assert r.status_code == 200 and r.json()["options"]
        assert client.post("/api/v1/explore", json={"month": 11, "vibe": "beach"}).json()[
            "candidates"
        ]
        assert (
            client.post(
                "/api/v1/tools/route",
                json={
                    "origin": {"latitude": 43.45, "longitude": 39.96},
                    "destination": {"latitude": 43.6, "longitude": 39.73},
                },
            ).json()["status"]
            == "ok"
        )
        assert (
            client.get("/api/v1/catalog/hotels?city=Сочи&source_mode=snapshot&limit=2").json()[
                "total"
            ]
            == 11
        )
        assert client.get("/api/v1/catalog/orders").status_code == 404
        assert client.get("/api/v1/catalog/hotels?limit=999999").status_code == 422


def test_osm_parser_unknowns_url_safety_and_xml_entities():
    xml = (
        '<osm><node id="1" lat="43.58" lon="39.73"><tag k="tourism" v="hotel"/>'
        '<tag k="name" v="Mapped hotel"/><tag k="stars" v="unknown"/>'
        '<tag k="website" v="javascript:bad"/></node></osm>'
    )
    hotels = parse_osm(xml, "Сочи", datetime.now(UTC))
    assert len(hotels) == 1 and hotels[0].stars is None and hotels[0].website is None
    assert safe_website("https://user:secret@example.com/") is None
    with pytest.raises(ValueError):
        parse_osm("<!DOCTYPE test>" + xml, "Сочи", datetime.now(UTC))


def test_minor_units_exact_no_float_rounding():
    assert minor("100.01") == 10001
    with pytest.raises(ValueError):
        minor("1.001")
    with pytest.raises(ValueError):
        minor("-1")


def test_legacy_state_migration_preserves_existing_records(settings, tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    old = StateStore(legacy / "state.sqlite3")
    raw = json.loads(Path("data/fixtures/search-request.json").read_text())["request"]
    from trip_data.models import SearchOutput, TripRequest

    plan = Plan(
        id="keep-me",
        version=1,
        request=TripRequest.model_validate(raw),
        search=SearchOutput(plan_version=1, options=[], rejected={}, limitations=[]),
    )
    old.create(plan)
    target = CatalogDB(settings.database_path)
    new = StateStore(settings.database_path)
    assert target.migrate_legacy(legacy)["plans"] == 1
    assert new.get("keep-me").version == 1
    assert old.get("keep-me").id == "keep-me"
    assert target.migrate_legacy(legacy) == {}


def test_source_identity_cannot_overwrite_other_source(database):
    with database.connect() as db:
        row = db.execute(
            "SELECT id FROM hotels WHERE source_mode=? LIMIT 1", ("snapshot",)
        ).fetchone()
        with pytest.raises(ValueError, match="another source"):
            database.upsert(db, "hotels", dict(id=row[0], source_id="components"))


def test_money_nan_is_invalid():
    with pytest.raises(ValueError):
        minor("NaN")
