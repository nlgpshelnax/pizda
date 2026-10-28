from datetime import UTC, datetime

from fastapi.testclient import TestClient
from trip_data.agent_context import CatalogContextQuery, read_context
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.main import create_app


def test_agent_reads_real_metadata_without_provider_requests(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Catalog context must never call a provider")

    monkeypatch.setattr("httpx.AsyncClient.request", forbidden)
    settings = Settings(database_path=tmp_path / "catalog.sqlite3", external_mode="live")
    with TestClient(create_app(settings)) as client:
        result = client.post("/api/v1/catalog/context", json={"city": "Сочи", "limit": 2})
        assert result.status_code == 200
        body = result.json()
        assert body["read_from"] == "database" and not body["bookable"]
        hotels = body["sections"]["hotels"]
        assert hotels["total"] > 2 and hotels["truncated"]
        assert len(hotels["rows"]) == 2
        assert all(h["source_mode"] == "snapshot" for h in hotels["rows"])
        assert body["sections"]["weather"]["status"] == "missing"
        assert body["sources"]
        assert (
            client.post("/api/v1/catalog/context", json={"city": "Unknown"}).json()["status"]
            == "not_found"
        )
        for bad in [
            {"city": "Сочи", "limit": 1000},
            {"city": "Сочи", "start_date": "2026-11-10"},
            {"city": "Сочи", "start_date": "2026-11-10", "end_date": "2026-11-09"},
        ]:
            assert client.post("/api/v1/catalog/context", json=bad).status_code == 422


def test_context_filters_expired_mock_wrong_city_and_dates(tmp_path):
    settings = Settings(database_path=tmp_path / "catalog.sqlite3")
    database = CatalogDB(settings.database_path)
    database.load_files(settings)
    with database.connect() as db:
        db.execute("INSERT INTO ingest_sources VALUES('test-weather','hash','2026-10-27',5)")
        for ident, city, day, mode, expiry in [
            ("fresh", "sochi", "2026-10-28", "live", "2026-10-29T00:00:00+00:00"),
            # Despite later local clock time, this timestamp has already expired at noon UTC.
            ("expired", "sochi", "2026-10-28", "live", "2026-10-27T14:00:00+03:00"),
            ("demo", "sochi", "2026-10-28", "mock", "2026-10-29T00:00:00+00:00"),
            ("city", "kazan", "2026-10-28", "live", "2026-10-29T00:00:00+00:00"),
            ("date", "sochi", "2026-10-30", "live", "2026-10-29T00:00:00+00:00"),
        ]:
            db.execute(
                "INSERT INTO weather(id,city_id,date,kind,source_mode,source_id,"
                "fetched_at,valid_until,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    city,
                    day,
                    "forecast",
                    mode,
                    "test-weather",
                    "2026-10-27T10:00:00+00:00",
                    expiry,
                    "{}",
                ),
            )
    result = read_context(
        database,
        CatalogContextQuery(city="Сочи", start_date="2026-10-28", end_date="2026-10-29"),
        now=datetime(2026, 10, 27, 12, tzinfo=UTC),
    )
    assert [r["id"] for r in result.sections["weather"]["rows"]] == ["fresh"]
    assert result.sections["transport_estimates"]["status"] == "missing"
    assert any(s["id"] == "test-weather" for s in result.sources)
