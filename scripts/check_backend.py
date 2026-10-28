"""Offline checks against the actual SQLite DB. No substitute model responses."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "divannie-analytiki"))
from fastapi.testclient import TestClient
from agent_api import app, check_database, ranked_bundle
from core.local_db_tools import LocalDBTravelTools

rows = check_database()
assert all(count > 0 for count in rows.values())
print("SQLite integrity and rows OK:", rows)
bundles = LocalDBTravelTools().get_trip_bundles(origin="Москва", destination="Сочи", dates="ноябрь")
assert bundles, "Expected bundled catalog to contain Moscow–Sochi options"
for bundle in bundles:
    mapped = ranked_bundle(bundle.model_dump())
    assert mapped["total"] == sum(mapped["costs"].values())
with TestClient(app) as client:
    assert client.get("/api/health").status_code == 200
    response = client.options("/api/v1/chat", headers={
        "Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert client.post("/api/v1/chat", json={"text": "", "preferences": {}}).status_code == 422
print("Database search, bundle mapping, HTTP health, CORS, request validation OK")
