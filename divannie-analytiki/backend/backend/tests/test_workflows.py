import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from trip_data.components import ComponentCatalog
from trip_data.config import Settings
from trip_data.main import create_app
from trip_data.state import StateError, StateStore


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(Settings(cache_path=tmp_path / "cache", state_path=tmp_path / "state"))
    ) as client:
        yield client


def request():
    return json.loads(Path("data/fixtures/search-request.json").read_text())["request"]


def test_plan_patch_preserves_context_cas_and_checkout(client):
    plan = client.post("/api/v1/plans", json=request()).json()
    plan_id = plan["id"]
    changed = client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"base_version": 1, "changes": {"check_in": "2026-11-12", "check_out": "2026-11-17"}},
    )
    assert changed.status_code == 200
    plan = changed.json()
    assert plan["version"] == 2
    assert plan["request"]["guests"] == request()["guests"]
    assert plan["request"]["budget"] == request()["budget"]
    assert plan["search"]["options"][0]["total"]["amount"] == "76000.00"
    assert (
        client.patch(
            f"/api/v1/plans/{plan_id}", json={"base_version": 1, "changes": {"budget": None}}
        ).status_code
        == 409
    )
    selection = client.post(
        f"/api/v1/plans/{plan_id}/selection",
        json={"base_version": 2, "bundle_id": plan["search"]["options"][0]["bundle"]["id"]},
    ).json()
    assert selection["version"] == 3
    payload = {"base_version": 3, "idempotency_key": "checkout-key-1"}
    order = client.post(f"/api/v1/plans/{plan_id}/checkout", json=payload)
    assert order.status_code == 200
    assert order.json()["status"] == "demo_only"
    repeated = client.post(f"/api/v1/plans/{plan_id}/checkout", json=payload)
    assert order.json()["id"] == repeated.json()["id"]
    payload["base_version"] = 4
    assert client.post(f"/api/v1/plans/{plan_id}/checkout", json=payload).status_code == 409
    # Changing a plan cannot mutate an already-created order.
    client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"base_version": 3, "changes": {"guests": {"children_ages": [7]}}},
    )
    assert client.get("/api/v1/orders/" + order.json()["id"]).json() == order.json()


def test_nested_patch_unknown_fields_and_selection_invalidation(client):
    plan = client.post("/api/v1/plans", json=request()).json()
    path = "/api/v1/plans/" + plan["id"]
    plan = client.post(
        path + "/selection",
        json={"base_version": 1, "bundle_id": plan["search"]["options"][0]["bundle"]["id"]},
    ).json()
    assert (
        client.patch(path, json={"base_version": 2, "changes": {"guests": {"cat": 1}}}).status_code
        == 422
    )
    changed = client.patch(
        path,
        json={"base_version": 2, "changes": {"guests": {"children_ages": [7]}, "budget": None}},
    ).json()
    assert changed["request"]["guests"]["adults"] == 2
    assert changed["request"]["budget"] is None
    assert changed["selected_id"] is None
    assert changed["search"]["options"] == []


def test_checkout_requires_selection_and_valid_version(client):
    plan = client.post("/api/v1/plans", json=request()).json()
    path = "/api/v1/plans/" + plan["id"]
    assert (
        client.post(
            path + "/checkout", json={"base_version": 1, "idempotency_key": "checkout-key-1"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/selection", json={"base_version": 1, "bundle_id": "not-in-plan"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("kind", ["early_check_in", "transfer"])
@pytest.mark.parametrize("decision", ["confirmed", "unavailable"])
def test_post_purchase_service_idempotence_and_terminal_state(client, kind, decision):
    plan = client.post("/api/v1/plans", json=request()).json()
    path = "/api/v1/plans/" + plan["id"]
    client.post(
        path + "/selection",
        json={"base_version": 1, "bundle_id": plan["search"]["options"][0]["bundle"]["id"]},
    )
    order = client.post(
        path + "/checkout", json={"base_version": 2, "idempotency_key": "checkout-key-1"}
    ).json()
    path = "/api/v1/orders/" + order["id"] + "/services"
    payload = {"kind": kind, "idempotency_key": "service-key-1"}
    service = client.post(path, json=payload).json()
    assert service["status"] == "pending"
    assert service["data_mode"] == "mock"
    assert client.post(path, json=payload).json()["id"] == service["id"]
    payload["kind"] = "transfer" if kind == "early_check_in" else "early_check_in"
    assert client.post(path, json=payload).status_code == 409
    resolve = path + "/" + service["id"] + "/simulate"
    assert client.post(resolve, json={"status": decision}).json()["status"] == decision
    other = "unavailable" if decision == "confirmed" else "confirmed"
    assert client.post(resolve, json={"status": other}).status_code == 409
    assert client.get("/api/v1/orders/" + order["id"]).json() == order


def test_state_restored_and_old_cas_cannot_overwrite(tmp_path, client):
    plan_data = client.post("/api/v1/plans", json=request()).json()
    from trip_data.plan_models import Plan

    plan = Plan.model_validate(plan_data)
    store = StateStore(tmp_path / "persist")
    store.create(plan)
    plan.version = 2
    store.save(plan, 1)
    stale = plan.model_copy(update={"version": 3})
    with pytest.raises(StateError, match="STALE_PLAN_VERSION"):
        store.save(stale, 1)
    assert StateStore(tmp_path / "persist").get(plan.id).version == 2


def test_component_build_four_directions_and_rail(client):
    catalog = ComponentCatalog.model_validate_json(
        Path("data/fixtures/components.json").read_text()
    )
    for city in ["Сочи", "Казань", "Дубай", "Хургада"]:
        scope = next(h.scope for h in catalog.hotels if h.scope.destination == city)
        result = client.post(
            "/api/v1/bundles/compose",
            json={"request": scope.model_dump(mode="json"), "plan_version": 1},
        )
        assert result.status_code == 200, result.text
        assert result.json()["options"], city
        option = result.json()["options"][0]["bundle"]
        assert option["outbound_transfer"]["provenance"]["kind"] == "mock"
        if city == "Казань":
            rail = client.post("/api/v1/tools/rail", json=scope.model_dump(mode="json")).json()
            assert len(rail["quotes"]) == 2
            assert option["outbound"]["mode"] == "train"


def test_context_mock_kb_and_entry_rules(client):
    fixtures = json.loads(Path("data/fixtures/context.json").read_text())
    for tool, provider in [
        ("weather", "open-meteo"),
        ("route", "osrm"),
        ("places", "overpass"),
        ("flights", "travelpayouts-data"),
    ]:
        query = next(item["query"] for item in fixtures if item["provider"] == provider)
        response = client.post("/api/v1/tools/" + tool, json=query)
        assert response.status_code == 200
        assert response.json()["data_mode"] == "mock"
        assert response.json()["status"] == "ok"
    explore = client.post("/api/v1/explore", json={"month": 11, "vibe": "beach"}).json()
    assert explore["candidates"]
    assert all(
        not c["seasonality_verified"] and c["climatology"] is None for c in explore["candidates"]
    )
    rules = client.post(
        "/api/v1/tools/entry-rules",
        json={
            "citizenship": "RU",
            "destination_country": "AE",
            "travel_date": "2026-11-10",
            "duration_days": 5,
        },
    ).json()
    assert rules["status"] == "unknown"
    assert rules["source"].startswith("https://u.ae/")
    assert client.get("/api/v1/metrics").json()["mock-osrm"]["calls"] == 1


def test_data_evals_and_detectable_failure(tmp_path):
    from trip_data.evals import evaluate

    source = Path("data/evals/data-cases.json")
    report = evaluate(source, Path("data/fixtures/sochi.json"))
    assert report["total"] == 30
    assert report["failed"] == 0, [r for r in report["results"] if not r["passed"]]
    cases = json.loads(source.read_text())
    cases[0]["required_codes"] = ["DELIBERATELY_IMPOSSIBLE"]
    wrong = tmp_path / "bad-cases.json"
    wrong.write_text(json.dumps(cases))
    assert evaluate(wrong, Path("data/fixtures/sochi.json"))["failed"] == 1


def test_browser_patch_preflight(client):
    response = client.options(
        "/api/v1/plans/example",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert "PATCH" in response.headers["Access-Control-Allow-Methods"]


def test_transfer_routes_windows_and_timezone_rejected(client):
    from pydantic import ValidationError
    from trip_data.models import Bundle, TripRequest
    from trip_data.validation import validate_bundle

    raw = json.loads(Path("data/fixtures/component-source.json").read_text())[-1]
    raw["outbound_transfer"]["origin"] = "wrong-airport"
    raw["outbound_transfer"]["available_until"] = "2026-11-10T05:00:00+02:00"
    codes = {
        i.code
        for i in validate_bundle(
            Bundle.model_validate(raw), TripRequest.model_validate(raw["request"])
        )
    }
    assert {"TRANSFER_ROUTE_MISMATCH", "TRANSFER_CLOSED"} <= codes
    raw["outbound"]["segments"][0]["arrival_timezone"] = "Europe/Moscow"
    with pytest.raises(ValidationError):
        Bundle.model_validate(raw)


def test_selected_hotel_survives_requote_when_compatible(client):
    plan = client.post("/api/v1/plans", json=request()).json()
    path = "/api/v1/plans/" + plan["id"]
    plan = client.post(
        path + "/selection",
        json={"base_version": 1, "bundle_id": plan["search"]["options"][0]["bundle"]["id"]},
    ).json()
    assert plan["selected_id"] == "mock-sochi-001"
    plan = client.patch(
        path,
        json={"base_version": 2, "changes": {"check_in": "2026-11-12", "check_out": "2026-11-17"}},
    ).json()
    assert plan["selected_id"] == "mock-sochi-002-shifted"
    assert plan["search"]["options"][0]["total"]["amount"] == "76000.00"


def test_real_catalog_not_mislabeled_as_mock(tmp_path):
    from trip_data.providers.catalog import MockCatalog

    source = json.loads(Path("data/fixtures/sochi.json").read_text())
    source[0]["provenance"]["kind"] = "snapshot"
    path = tmp_path / "not-mock.json"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="synthetic"):
        MockCatalog(path)
