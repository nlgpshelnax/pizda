import asyncio
from datetime import UTC, date, datetime

import httpx
from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.main import create_app
from trip_data.providers.xotelo import current_estimates, refresh_city


def test_refresh_idempotence_scope_expiry_and_failure(tmp_path):
    settings = Settings(database_path=tmp_path / "db.sqlite3")
    db = CatalogDB(settings.database_path)
    stamp = int(datetime.now(UTC).timestamp() * 1000)

    def handler(req):
        if req.url.path.endswith("list"):
            return httpx.Response(
                200,
                json={
                    "error": None,
                    "timestamp": stamp,
                    "result": {"list": [{"key": "g298536-d123", "name": "Example hotel"}]},
                },
            )
        return httpx.Response(
            200,
            json={
                "error": None,
                "timestamp": stamp,
                "result": {
                    "chk_in": "2026-11-10",
                    "chk_out": "2026-11-15",
                    "currency": "RUB",
                    "rates": [{"name": "Vendor", "rate": 1234.5, "tax": None}],
                },
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for _ in range(2):
                result = await refresh_city(
                    db, client, "Сочи", date(2026, 11, 10), date(2026, 11, 15)
                )
                assert result["rates"][0]["status"] == "ok"

    asyncio.run(run())
    rows = current_estimates(db, "Сочи")
    assert len(rows) == 1 and rows[0]["nightly_minor"] == 123450
    assert rows[0]["bookable"] == 0 and rows[0]["tax_known"] == 0
    assert not current_estimates(db, "Казань")
    db.log("xotelo:g298536", "partial", datetime.now(UTC).isoformat(), 1, "timeout")
    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/v1/hotels/estimates", params={"city": "Сочи"}).json()
        assert payload["bookable"] is False and payload["data_mode"] == "snapshot"
        assert len(payload["estimates"]) == 1
        assert payload["last_sync"]["status"] == "partial"
        assert any("refresh failed" in warning for warning in payload["warnings"])
        params = {"city": "Сочи", "check_in": "2026-11-10", "check_out": "2026-11-15", "adults": 2}
        assert len(client.get("/api/v1/hotels/estimates", params=params).json()["estimates"]) == 1
        params["adults"] = 3
        assert client.get("/api/v1/hotels/estimates", params=params).json()["estimates"] == []
        params["adults"] = 2
        params["check_in"] = "2026-11-11"
        assert client.get("/api/v1/hotels/estimates", params=params).json()["estimates"] == []
        assert (
            client.get(
                "/api/v1/hotels/estimates", params={"city": "Сочи", "check_in": "2026-11-10"}
            ).status_code
            == 422
        )
    with db.connect() as conn:
        conn.execute("UPDATE xotelo_rates SET valid_until='2000-01-01T00:00:00+00:00'")
    assert not current_estimates(db, "Сочи")


def test_api_error_does_not_overwrite_existing_records(tmp_path):
    db = CatalogDB(tmp_path / "db.sqlite3")

    async def run():
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"error": {"message": "limited"}, "result": None})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            import pytest
            from trip_data.providers.base import ProviderFailure

            with pytest.raises(ProviderFailure):
                await refresh_city(db, client, "Сочи", date(2026, 11, 10), date(2026, 11, 15))

    asyncio.run(run())
    assert not current_estimates(db, "Сочи")


def test_stale_response_cannot_replace_newer_rates(tmp_path):
    db = CatalogDB(tmp_path / "db.sqlite3")
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    state = {"timestamp": now_ms, "price": 5000}

    def handler(req):
        if req.url.path.endswith("list"):
            result = {"list": [{"key": "g298536-d123", "name": "Hotel"}]}
        else:
            result = {
                "chk_in": "2026-11-10",
                "chk_out": "2026-11-15",
                "currency": "RUB",
                "rates": [{"name": "Vendor", "rate": state["price"]}],
            }
        return httpx.Response(
            200, json={"error": None, "timestamp": state["timestamp"], "result": result}
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await refresh_city(db, client, "Сочи", date(2026, 11, 10), date(2026, 11, 15))
            state.update(timestamp=now_ms - 60000, price=1000)
            await refresh_city(db, client, "Сочи", date(2026, 11, 10), date(2026, 11, 15))

    asyncio.run(run())
    rows = current_estimates(db, "Сочи")
    assert len(rows) == 1 and rows[0]["nightly_minor"] == 500000
