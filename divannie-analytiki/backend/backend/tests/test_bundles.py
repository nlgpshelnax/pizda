from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from trip_data.main import create_app
from trip_data.models import Bundle, SearchInput, TripRequest
from trip_data.providers.catalog import MockCatalog
from trip_data.validation import total_price, validate_bundle


@pytest.fixture
def bundle():
    return MockCatalog(Path("data/fixtures/sochi.json")).bundles[0].model_copy(deep=True)


def codes(bundle, request=None):
    return {issue.code for issue in validate_bundle(bundle, request or bundle.request)}


def test_total_and_valid_journey(bundle):
    assert str(total_price(bundle).amount) == "73000.00"
    assert codes(bundle) == {"DEMO_DATA"}


def test_no_price_reuse_for_new_dates(bundle):
    request = bundle.request.model_copy(
        update={"check_in": bundle.request.check_in + timedelta(days=2)}
    )
    assert "QUOTE_SCOPE_MISMATCH" in codes(bundle, request)


def test_child_changes_quote_and_capacity(bundle):
    request = bundle.request.model_copy(deep=True)
    request.guests.children_ages = [4, 8]
    assert {"QUOTE_SCOPE_MISMATCH", "TRANSFER_CAPACITY"} <= codes(bundle, request)


def test_pet_unknown_is_not_allowed(bundle):
    bundle.request.guests.pets = 1
    assert "PETS_UNCONFIRMED" in codes(bundle)


def test_night_arrival_misses_checkin(bundle):
    bundle.outbound.arrival_at += timedelta(hours=12)
    assert "MISSED_CHECKIN" in codes(bundle)


def test_early_checkin_is_warning(bundle):
    bundle.outbound.arrival_at -= timedelta(hours=3)
    issue = next(
        i for i in validate_bundle(bundle, bundle.request) if i.code == "EARLY_CHECKIN_UNCONFIRMED"
    )
    assert issue.severity == "warning"


def test_impossible_return(bundle):
    bundle.inbound.departure_at = bundle.hotel.check_in_at + timedelta(minutes=30)
    assert "RETURN_UNREACHABLE" in codes(bundle)


def test_budget_breakfast_and_stars(bundle):
    request = bundle.request.model_copy(deep=True)
    request.budget.amount = 1
    request.min_stars = 5
    bundle.hotel.breakfast = False
    assert {"OVER_BUDGET", "BREAKFAST_REQUIRED", "STARS_REQUIRED"} <= codes(bundle, request)


def test_snapshot_expiry(bundle):
    bundle.provenance.kind = "snapshot"
    assert "QUOTE_EXPIRED" in {
        i.code for i in validate_bundle(bundle, bundle.request, datetime(2027, 1, 1, tzinfo=UTC))
    }


def test_unknown_fees_and_visa(bundle):
    bundle.mandatory_fees_known = False
    bundle.outbound.international = True
    assert {"UNKNOWN_FEES", "VISA_UNVERIFIED"} <= codes(bundle)


def test_timezone_comparison_uses_instant(bundle):
    # Same arrival instant written in UTC must not change validation.
    before = codes(bundle)
    bundle.outbound.arrival_at = bundle.outbound.arrival_at.astimezone(UTC)
    assert codes(bundle) == before


def test_naive_datetime_rejected(bundle):
    data = bundle.model_dump(mode="json")
    data["outbound"]["arrival_at"] = "2026-11-10T12:30:00"
    with pytest.raises(ValidationError):
        Bundle.model_validate(data)


@pytest.mark.parametrize("age", [-1, 18])
def test_invalid_child_age(bundle, age):
    data = bundle.request.model_dump(mode="json")
    data["guests"]["children_ages"] = [age]
    with pytest.raises(ValidationError):
        TripRequest.model_validate(data)


def test_api_and_openapi(bundle):
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["catalog_size"] == 6
        payload = SearchInput(request=bundle.request, plan_version=7).model_dump(mode="json")
        response = client.post("/api/v1/bundles/search", json=payload)
        assert response.status_code == 200
        result = response.json()
        assert result["plan_version"] == 7
        assert result["data_mode"] == "mock"
        assert result["options"][0]["total"]["amount"] == "73000.00"
        assert client.get("/openapi.json").status_code == 200
        payload["request"]["check_in"] = "2026-11-12"
        response = client.post("/api/v1/bundles/search", json=payload)
        assert response.json()["options"] == []
        assert "mock-sochi-001" in response.json()["rejected"]
        payload["request"]["check_out"] = "2026-11-01"
        assert client.post("/api/v1/bundles/search", json=payload).status_code == 422


def test_independent_transfers_and_price(bundle):
    outward, inward = bundle.transfers()
    bundle.outbound_transfer = outward.model_copy(deep=True)
    bundle.inbound_transfer = inward.model_copy(deep=True)
    bundle.inbound_transfer.price.amount = 2500
    bundle.inbound_transfer.duration_minutes = 8000
    assert total_price(bundle).amount == 74000
    assert "RETURN_UNREACHABLE" in codes(bundle)
    bundle.inbound_transfer.capacity = 1
    assert "TRANSFER_CAPACITY" in codes(bundle)


def test_missing_transfer_rejected(bundle):
    payload = bundle.model_dump(mode="json")
    del payload["transfer"]
    with pytest.raises(ValidationError):
        Bundle.model_validate(payload)


def test_hotel_capacity_and_unknown_child_policy(bundle):
    bundle.hotel.max_guests = 1
    assert "HOTEL_CAPACITY" in codes(bundle)
    bundle.hotel.max_guests = None
    assert "HOTEL_CAPACITY_UNCONFIRMED" in codes(bundle)
    bundle.request.guests.children_ages = [7]
    bundle.hotel.children_allowed = None
    assert "CHILDREN_UNCONFIRMED" in codes(bundle)


def test_provider_buffer_cannot_reduce_safety_default(bundle):
    before = codes(bundle)
    bundle.outbound.arrival_buffer_minutes = 0
    assert codes(bundle) == before
    bundle.outbound.arrival_buffer_minutes = 1000
    assert "MISSED_CHECKIN" in codes(bundle)


def test_train_and_waiting_after_checkout(bundle):
    bundle.inbound.mode = "train"
    bundle.inbound.departure_at += timedelta(hours=5)
    bundle.inbound.arrival_at += timedelta(hours=5)
    assert "WAIT_AFTER_CHECKOUT" in codes(bundle)


def test_component_provenance_cannot_hide_stale_or_mock_quote(bundle):
    bundle.provenance.kind = "live"
    assert "SOURCE_UNCONFIRMED" in codes(bundle)
    for component in (bundle.hotel, bundle.outbound, bundle.inbound, *bundle.transfers()):
        component.provenance = bundle.provenance.model_copy(deep=True)
    bundle.hotel.provenance.kind = "mock"
    assert "MIXED_MOCK_DATA" in codes(bundle)
    bundle.hotel.provenance.kind = "snapshot"
    issues = validate_bundle(bundle, bundle.request, datetime(2027, 1, 1, tzinfo=UTC))
    assert "COMPONENT_QUOTE_EXPIRED" in {i.code for i in issues}
