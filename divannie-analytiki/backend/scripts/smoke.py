"""Exercise the actual running server. Uses only explicit mock/demo operations."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--restore", action="store_true")
parser.add_argument("--state", type=Path, default=Path(".runtime/smoke-state.json"))
args = parser.parse_args()

with httpx.Client(base_url=args.base_url, timeout=15) as client:

    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def post(path, data):
        response = client.post(path, json=data)
        response.raise_for_status()
        return response.json()

    if args.restore:
        state = json.loads(args.state.read_text())
        plan = get("/api/v1/plans/" + state["plan_id"])
        order = get("/api/v1/orders/" + state["order_id"])
        services = get("/api/v1/orders/" + state["order_id"] + "/services")
        assert plan["version"] == state["version"]
        assert order["status"] == "demo_only" and order["total"]["amount"] == "89000.00"
        assert services[0]["status"] == "confirmed" and services[0]["data_mode"] == "mock"
        print("RESTORE PASS: plan, immutable demo order and simulated service survive restart")
    else:
        assert get("/api/health")["catalog_size"] == 6
        source = json.loads(Path("data/fixtures/component-source.json").read_text())
        for city in ["Сочи", "Казань", "Дубай", "Хургада"]:
            query = next(b["request"] for b in source if b["request"]["destination"] == city)
            assert post("/api/v1/bundles/search", {"request": query, "plan_version": 1})["options"]
            assert post("/api/v1/bundles/compose", {"request": query, "plan_version": 1})["options"]
        query = json.loads(Path("data/fixtures/search-request.json").read_text())["request"]
        plan = post("/api/v1/plans", query)
        path = "/api/v1/plans/" + plan["id"]
        patched = client.patch(
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
        patched.raise_for_status()
        plan = patched.json()
        assert plan["search"]["options"][0]["total"]["amount"] == "89000.00"
        assert plan["request"]["guests"]["adults"] == 2
        assert client.patch(path, json={"base_version": 1, "changes": {}}).status_code == 409
        plan = post(
            path + "/selection",
            {"base_version": 2, "bundle_id": plan["search"]["options"][0]["bundle"]["id"]},
        )
        payload = {"base_version": plan["version"], "idempotency_key": str(uuid4())}
        order = post(path + "/checkout", payload)
        assert post(path + "/checkout", payload)["id"] == order["id"]
        service = post(
            "/api/v1/orders/" + order["id"] + "/services",
            {"kind": "early_check_in", "idempotency_key": str(uuid4())},
        )
        assert service["status"] == "pending"
        resolved = post(
            "/api/v1/orders/" + order["id"] + "/services/" + service["id"] + "/simulate",
            {"status": "confirmed"},
        )
        assert resolved["data_mode"] == "mock"
        fixtures = json.loads(Path("data/fixtures/context.json").read_text())
        for tool, name in [
            ("weather", "open-meteo"),
            ("route", "osrm"),
            ("places", "overpass"),
            ("flights", "travelpayouts-data"),
        ]:
            query = next(f["query"] for f in fixtures if f["provider"] == name)
            result = post("/api/v1/tools/" + tool, query)
            assert result["status"] == "ok" and result["data_mode"] == "mock"
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(
            json.dumps({"plan_id": plan["id"], "version": plan["version"], "order_id": order["id"]})
            + "\n"
        )
        print(
            "SMOKE PASS: 4 destinations, component composition, context tools, patch/CAS, "
            "idempotent demo order and post-purchase request"
        )
