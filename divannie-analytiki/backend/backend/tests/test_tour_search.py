import json
from pathlib import Path

from fastapi.testclient import TestClient
from trip_data.config import Settings
from trip_data.main import create_app


def test_tour_search_validates_scope_budget_and_pets(tmp_path):
    request = json.loads(Path("data/fixtures/search-request.json").read_text())["request"]
    settings = Settings(database_path=tmp_path / "test.sqlite3")
    with TestClient(create_app(settings)) as client:
        result = client.post("/api/v1/tours/search", json={"request": request})
        assert result.status_code == 200
        data = result.json()
        assert len(data["search"]["options"]) == 1
        assert data["search"]["options"][0]["total"]["amount"] == "73000.00"
        assert data["booking"] == "demo_only"
        assert data["visa"]["requires_verification"]
        request["budget"]["amount"] = "100.00"
        rejected = client.post("/api/v1/tours/search", json={"request": request}).json()
        assert rejected["search"]["options"] == []
        assert any(
            issue["code"] == "OVER_BUDGET"
            for issues in rejected["search"]["rejected"].values()
            for issue in issues
        )
        request["guests"]["pets"] = 1
        assert (
            client.post("/api/v1/tours/search", json={"request": request}).json()["search"][
                "options"
            ]
            == []
        )


def test_percentiles_interpolate_minor_units():
    from trip_data.database import percentile_minor

    assert percentile_minor([100, 300], '0.25') == 150
    assert percentile_minor([100, 300], '0.5') == 200
    assert percentile_minor([100, 300], '0.75') == 250
