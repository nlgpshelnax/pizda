import asyncio

import httpx
from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.main import create_app
from trip_data.providers.passport_index import refresh_passport_index


def test_historical_snapshot_is_not_a_visa_decision(tmp_path):
    settings = Settings(database_path=tmp_path / "travel.sqlite3")
    db = CatalogDB(settings.database_path)
    sha = "a" * 40

    def handler(req):
        if req.url.host == "api.github.com":
            return httpx.Response(200, json={"sha": sha})
        if req.url.path.endswith("README.md"):
            return httpx.Response(200, text="Last updated: **17 February 2026**.")
        return httpx.Response(200, json={"RU": {"RS": {"status": "visa free", "days": 30}}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await refresh_passport_index(db, client, ["RS", "FR"])

    assert asyncio.run(run())["rows"] == 1
    with TestClient(create_app(settings)) as client:
        ref = client.get(
            "/api/v1/visa/reference", params={"passport": "RU", "destination": "RS"}
        ).json()
        assert ref["status"] == "historical_unverified" and ref["requires_verification"]
        assert ref["record"]["dataset_date"] == "2026-02-17"
        assert ref["record"]["days"] == 30
        assert (
            client.get(
                "/api/v1/visa/reference", params={"passport": "RUS", "destination": "RS"}
            ).status_code
            == 422
        )
        missing = client.get(
            "/api/v1/visa/reference", params={"passport": "RU", "destination": "FR"}
        ).json()
        assert missing["status"] == "missing" and missing["requires_verification"]
