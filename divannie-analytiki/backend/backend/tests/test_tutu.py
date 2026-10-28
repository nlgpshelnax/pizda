import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.main import create_app
from trip_data.providers.base import ProviderFailure
from trip_data.providers.tutu import read_schedule, refresh_schedule


def test_schedule_snapshot_is_research_only_and_survives_failure(tmp_path):
    settings = Settings(database_path=tmp_path / "db.sqlite3")
    db = CatalogDB(settings.database_path)
    sample = {
        "trips": [
            {
                "trainNumber": "001А",
                "departureTime": "23:55:00",
                "arrivalTime": "09:00:00",
                "travelTimeInSeconds": "32700",
                "categories": [{"type": "coupe", "price": 2300}],
            }
        ]
    }

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=sample))
        ) as client:
            await refresh_schedule(db, client, "Москва", "Казань")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(500))
        ) as client:
            with pytest.raises(ProviderFailure):
                await refresh_schedule(db, client, "Москва", "Казань")

    asyncio.run(run())
    rows = read_schedule(db, "Москва", "Казань")
    assert len(rows) == 1 and rows[0]["bookable"] == 0
    assert rows[0]["categories"][0]["price_rub"] == 2300
    assert read_schedule(db, "Казань", "Москва") == []
    db.log("tutu:2000000:2060615", "timeout", datetime.now(UTC).isoformat(), 0, "timeout")
    with TestClient(create_app(settings)) as client:
        result = client.get(
            "/api/v1/rail/schedule", params={"origin": "Москва", "destination": "Казань"}
        ).json()
        assert result["bookable"] is False and result["data_mode"] == "snapshot"
        assert result["last_sync"]["status"] == "timeout"
        assert any("refresh failed" in warning for warning in result["warnings"])
        assert "Undated" in result["warnings"][0]
        visa = client.post(
            "/api/v1/tools/entry-rules",
            json={
                "citizenship": "RU",
                "destination_country": "EG",
                "travel_date": "2026-11-10",
                "duration_days": 5,
            },
        ).json()
        assert visa["status"] == "unknown" and "gov.eg" in visa["source"]
    with db.connect() as conn:
        conn.execute(
            "UPDATE rail_schedule_estimates SET valid_until=?",
            (datetime(2000, 1, 1, tzinfo=UTC).isoformat(),),
        )
    assert read_schedule(db, "Москва", "Казань") == []
