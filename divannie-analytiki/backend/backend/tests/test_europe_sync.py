import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.europe_sync import city_payload, geocode_result, import_current, import_osm
from trip_data.main import create_app


def test_geocode_validates_country_and_spelling():
    response = {
        "results": [
            {
                "name": "Füssen",
                "country_code": "DE",
                "latitude": 47.57,
                "longitude": 10.7,
                "timezone": "Europe/Berlin",
            }
        ]
    }
    assert geocode_result(response, "DE", "Fussen") is not None
    assert geocode_result(response, "AT", "Fussen") is None
    assert geocode_result(response, "DE", "Berlin") is None


def test_europe_osm_weather_and_real_only_separated(tmp_path):
    settings = Settings(database_path=tmp_path / "db.sqlite3")
    db = CatalogDB(settings.database_path)
    db.load_files(settings)
    spec = ["RS", "Белград", "Belgrade", "BEG"]
    item = {
        "name": "Belgrade",
        "country_code": "RS",
        "latitude": 44.8,
        "longitude": 20.46,
        "timezone": "Europe/Belgrade",
    }
    city = city_payload(spec, item)
    db.ingest("geo:belgrade", [city], db.import_destinations)
    now = datetime.now(UTC)
    payload = {
        "city": "Белград",
        "country": "RS",
        "fetched_at": now.isoformat(),
        "elements": [
            {
                "type": "node",
                "id": 100,
                "lat": 44.8,
                "lon": 20.46,
                "tags": {"tourism": "hotel", "name": "Mapped Hotel", "stars": "4", "pets": "yes"},
            },
            {
                "type": "node",
                "id": 101,
                "lat": 44.81,
                "lon": 20.47,
                "tags": {"tourism": "museum", "name": "Museum"},
            },
        ],
    }
    assert (
        db.ingest(
            "eu:osm:" + city["id"],
            payload,
            lambda conn, value, src: import_osm(db, conn, value, src),
        )["rows"]
        == 2
    )
    weather = {
        "city": "Белград",
        "fetched_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=2)).isoformat(),
        "current": {
            "time": now.isoformat(),
            "temperature_2m": 15,
            "snow_depth": 0.12,
            "precipitation": 0,
        },
    }
    db.ingest(
        "weather:belgrade", weather, lambda conn, value, src: import_current(db, conn, value, src)
    )
    with db.connect() as conn:
        h = conn.execute(
            "SELECT pets_allowed FROM hotels WHERE source_id LIKE 'eu:osm:%'"
        ).fetchone()
        w = conn.execute(
            "SELECT snow_depth_cm,sea_temp_c FROM weather WHERE source_id='weather:belgrade'"
        ).fetchone()
        assert h[0] == 1 and abs(w[0] - 12) < 0.001 and w[1] is None
    req = json.loads(open("data/fixtures/search-request.json").read())["request"]
    req["destination"] = "Белград"
    with TestClient(create_app(settings)) as client:
        ctx = client.post("/api/v1/catalog/context", json={"city": "Белград"}).json()
        assert ctx["sections"]["hotels"]["total"] == 1
        assert ctx["sections"]["activities"]["total"] == 1
        explore = client.post(
            "/api/v1/explore", json={"month": 11, "vibe": "culture", "real_only": True}
        ).json()
        match = next(item for item in explore["candidates"] if item["city"] == "Белград")
        assert match["vibe_match"]["source"] == "openstreetmap"
        assert match["vibe_match"]["osm_poi_count"] == 1
        assert match["vibe_match"]["season_verified"] is False
        hotels = client.post("/api/v1/hotels/search", json={"city": "Белград"}).json()
        assert hotels["status"] == "ok" and hotels["hotels"][0]["pets_allowed"] is True
        result = client.post("/api/v1/tours/search", json={"request": req, "real_only": True})
        assert result.status_code == 200
        assert result.json()["search"]["data_mode"] == "none"
        assert result.json()["search"]["options"] == []


def test_provider_rate_limit_retains_previous_osm_data(tmp_path, monkeypatch):
    import asyncio

    from trip_data.europe_sync import sync
    from trip_data.providers.base import ProviderFailure

    settings = Settings(database_path=tmp_path / "db.sqlite3", travelpayouts_token=None)
    db = CatalogDB(settings.database_path)
    offline = False

    async def fake_get(client, url, **kwargs):
        if "geocoding-api" in url:
            return {
                "results": [
                    {
                        "name": "Belgrade",
                        "country_code": "RS",
                        "latitude": 44.8,
                        "longitude": 20.46,
                        "timezone": "Europe/Belgrade",
                    }
                ]
            }
        if "open-meteo.com/v1/forecast" in url:
            return {"current": {"time": datetime.now(UTC).isoformat(), "temperature_2m": 12}}
        if offline:
            raise ProviderFailure("rate_limited")
        return {
            "elements": [
                {
                    "type": "node",
                    "id": 100,
                    "lat": 44.8,
                    "lon": 20.46,
                    "tags": {"tourism": "hotel", "name": "Hotel"},
                }
            ]
        }

    async def fake_airports(client):
        return {}

    async def fake_passport(database, client, countries):
        return {"rows": 0}

    monkeypatch.setattr("trip_data.europe_sync.refresh_passport_index", fake_passport)
    monkeypatch.setattr("trip_data.europe_sync.get_json", fake_get)
    monkeypatch.setattr("trip_data.europe_sync.airports", fake_airports)
    spec = [["RS", "Белград", "Belgrade", "BEG"]]
    first = asyncio.run(sync(db, settings, spec, delay=0))
    assert first["osm"] == 1
    offline = True
    second = asyncio.run(sync(db, settings, spec, delay=0))
    assert second["failures"]["Белград:osm"] == "rate_limited"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM hotels WHERE active=1").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT status FROM ingest_runs WHERE source_id LIKE 'eu:osm:%' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            == "rate_limited"
        )


def test_marine_temperature_preserves_grid_and_units(tmp_path):
    from trip_data.europe_sync import distance_km, import_marine

    database = CatalogDB(tmp_path / "catalog.sqlite3")
    now = datetime.now(UTC)
    city = city_payload(
        ["FR", "Ницца", "Nice", "NCE"],
        {
            "name": "Nice",
            "country_code": "FR",
            "latitude": 43.7,
            "longitude": 7.26,
            "timezone": "Europe/Paris",
        },
    )
    database.ingest("geo:nice", [city], database.import_destinations)
    payload = {
        "city": "Ницца",
        "current": {"time": now.isoformat(), "sea_surface_temperature": 21.6},
        "grid_latitude": 43.71,
        "grid_longitude": 7.29,
        "fetched_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=2)).isoformat(),
    }
    database.ingest(
        "marine:nice", payload, lambda conn, value, src: import_marine(database, conn, value, src)
    )
    with database.connect() as conn:
        row = conn.execute(
            "SELECT sea_temp_c,payload_json FROM weather WHERE source_id='marine:nice'"
        ).fetchone()
    assert row[0] == 21.6 and json.loads(row[1])["grid_longitude"] == 7.29
    assert distance_km(43.7, 7.26, 43.71, 7.29) < 35
    assert distance_km(43.7, 7.26, 55, 7.29) > 35


def test_real_only_export_excludes_synthetic_catalog(tmp_path, monkeypatch):
    import runpy
    import sqlite3
    import sys

    settings = Settings(database_path=tmp_path / "source.sqlite3")
    db = CatalogDB(settings.database_path)
    db.load_files(settings)
    city = city_payload(
        ["RS", "Белград", "Belgrade", "BEG"],
        {
            "name": "Belgrade",
            "country_code": "RS",
            "latitude": 44.8,
            "longitude": 20.46,
            "timezone": "Europe/Belgrade",
        },
    )
    db.ingest("eu:geo:test", [city], db.import_destinations)
    output = tmp_path / "research.sqlite3"
    monkeypatch.setenv("TRIP_DATABASE_PATH", str(settings.database_path))
    monkeypatch.setattr(sys, "argv", ["export_database.py", "--real-only", "--output", str(output)])
    runpy.run_path("scripts/export_database.py", run_name="__main__")
    with sqlite3.connect(output) as conn:
        assert conn.execute("SELECT city FROM destinations").fetchall() == [("Белград",)]
        for table in (
            "bundles",
            "hotel_quotes",
            "transport_quotes",
            "transfer_quotes",
            "context_fixtures",
        ):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
