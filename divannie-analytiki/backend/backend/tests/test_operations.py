import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.operations import AlreadyRunning, JobLock, quality, run_job
from trip_data.providers.liteapi import HotelRateQuery, search_rates


def test_job_lock_and_repeatable_worker(tmp_path):
    settings = Settings(database_path=tmp_path / "db")
    with (
        JobLock(tmp_path / "job.lock"),
        pytest.raises(AlreadyRunning),
        JobLock(tmp_path / "job.lock"),
    ):
        pass
    one = asyncio.run(run_job(settings, online=False))
    two = asyncio.run(run_job(settings, online=False))
    assert one["status"] == two["status"] == "ok"
    assert all(r["status"] == "skipped" for r in two["loads"])
    db = CatalogDB(settings.database_path)
    assert db.summary()["hotel_modes"]["snapshot"] == 62
    report = quality(db, now="2099-01-01T00:00:00Z")
    assert report["ok"]
    assert any(f["code"] == "EXPIRED_RECORDS" for f in report["findings"])
    assert any(f["code"] == "NO_REAL_HOTEL_RATES" for f in report["findings"])


def test_liteapi_scope_key_not_in_url_and_sandbox():
    q = HotelRateQuery(
        hotel_ids=["lp123"],
        check_in="2026-11-10",
        check_out="2026-11-15",
        guests={"adults": 2, "children_ages": [7]},
        guest_nationality="RU",
    )

    async def check():
        def respond(request):
            assert request.method == "POST"
            assert request.headers["X-API-Key"] == "test-only"
            assert "test-only" not in str(request.url)
            payload = json.loads(request.content)
            assert payload["occupancies"] == [{"rooms": 1, "adults": 2, "children": [7]}]
            assert payload["guestNationality"] == "RU"
            return httpx.Response(
                200,
                json={
                    "sandbox": True,
                    "data": [
                        {
                            "hotelId": "lp123",
                            "roomTypes": [
                                {
                                    "offerId": "offer",
                                    "rates": [
                                        {
                                            "rateId": "rate",
                                            "adultCount": 2,
                                            "childrenAges": [7],
                                            "retailRate": {
                                                "total": [{"currency": "RUB", "amount": 12345}]
                                            },
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert (await search_rates(client, q, None))["status"] == "not_configured"
            result = await search_rates(client, q, SecretStr("test-only"), "production")
            assert result["environment"] == "sandbox"
            assert result["rates"][0]["price"]["amount"] == "12345"
            assert result["rates"][0]["mandatory_fees_known"] is False
            assert result["rates"][0]["bookable"] is False

    asyncio.run(check())


def test_import_reviewed_rate_atomic(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("importer", "scripts/import_hotel_rates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = Settings(database_path=tmp_path / "db")
    db = CatalogDB(settings.database_path)
    db.load_files(settings)
    with db.connect() as con:
        prop = con.execute(
            "SELECT id FROM hotels WHERE city_id='sochi' AND source_mode='snapshot' LIMIT 1"
        ).fetchone()[0]
    q = json.loads(Path("data/fixtures/components.json").read_text())["hotels"][0]
    q["id"] = "reviewed"
    q["property_id"] = prop
    q["provenance"]["kind"] = "snapshot"
    q["provenance"]["source_url"] = "https://example.com/evidence"
    assert module.import_rates(db, [q])["rows"] == 1
    assert module.import_rates(db, [q])["status"] == "skipped"
    q["provenance"]["source_url"] = None
    with pytest.raises(ValueError):
        module.import_rates(db, [q])
    with db.connect() as con:
        assert (
            con.execute(
                "SELECT count(*) FROM hotel_quotes WHERE source_mode='snapshot'"
            ).fetchone()[0]
            == 1
        )
