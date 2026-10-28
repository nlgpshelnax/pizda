"""Rehearse backend scenarios in an isolated DB with all provider HTTP requests disabled."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.main import create_app


async def disconnected(self, method, url, **kwargs):
    raise httpx.ConnectError(
        "Demo rehearsal: network unavailable", request=httpx.Request(method, url)
    )


def main():
    fixtures = json.loads(Path("data/fixtures/component-source.json").read_text())
    queries = {}
    for item in fixtures:
        req = item["request"]
        queries.setdefault(req["destination"], req)
    with tempfile.TemporaryDirectory(prefix="trip-demo-") as tmp:
        settings = Settings(database_path=Path(tmp) / "demo.sqlite3", external_mode="live")
        with patch.object(httpx.AsyncClient, "request", disconnected):
            with TestClient(create_app(settings)) as client:
                for city in ("Сочи", "Казань", "Дубай"):
                    req = queries[city]
                    response = client.post("/api/v1/tours/search", json={"request": req})
                    response.raise_for_status()
                    payload = response.json()
                    assert payload["booking"] == "demo_only"
                    assert payload["search"]["data_mode"] == "mock"
                    options = payload["search"]["options"]
                    assert options and any(i["code"] == "DEMO_DATA" for i in options[0]["issues"])
                    bundle = options[0]["bundle"]
                    assert bundle["provenance"]["kind"] == "mock"
                    assert bundle["outbound_transfer"] and bundle["inbound_transfer"]
                    if city == "Казань":
                        assert bundle["outbound"]["mode"] == "train"
                    if city == "Дубай":
                        assert payload["visa"]["visa_status"] == "unknown"
                        assert payload["visa"]["requires_verification"]
                        assert payload["visa"]["source_url"].startswith("https://u.ae/")
                    print(f"{city}: {options[0]['total']['amount']} RUB, mock")
                req = queries["Сочи"]
                plan = client.post("/api/v1/plans", json=req).json()
                path = "/api/v1/plans/" + plan["id"]
                update = client.patch(
                    path,
                    json={
                        "base_version": 1,
                        "changes": {
                            "check_in": "2026-11-12",
                            "check_out": "2026-11-17",
                            "guests": {"children_ages": [7]},
                        },
                    },
                )
                update.raise_for_status()
                plan = update.json()
                assert plan["request"]["guests"]["adults"] == 2
                assert plan["request"]["budget"] == req["budget"]
                assert plan["search"]["options"][0]["total"]["amount"] == "89000.00"
                assert (
                    client.patch(path, json={"base_version": 1, "changes": {}}).status_code == 409
                )
                bad_budget = dict(req, budget={"amount": "100.00", "currency": "RUB"})
                rejected = client.post("/api/v1/tours/search", json={"request": bad_budget}).json()
                assert not rejected["search"]["options"]
                assert any(
                    issue["code"] == "OVER_BUDGET"
                    for issues in rejected["search"]["rejected"].values()
                    for issue in issues
                )
                pets = dict(req, guests={"adults": 2, "children_ages": [], "pets": 1})
                assert not client.post("/api/v1/tours/search", json={"request": pets}).json()[
                    "search"
                ]["options"]
                context = client.post("/api/v1/catalog/context", json={"city": "Сочи"}).json()
                assert context["read_from"] == "database"
                assert context["sections"]["weather"]["status"] == "missing"
                fixture = json.loads(Path("data/fixtures/context.json").read_text())
                weather = next(row["query"] for row in fixture if row["provider"] == "open-meteo")
                unavailable = client.post("/api/v1/tools/weather", json=weather)
                assert unavailable.status_code == 200
                assert unavailable.json()["status"] != "ok"
                print("PASS: пересборка, бюджет, питомец, старая версия, отключение поставщиков")


if __name__ == "__main__":
    main()
