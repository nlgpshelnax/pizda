import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from trip_data.cache import SQLiteCache, cache_key
from trip_data.config import Settings
from trip_data.main import create_app
from trip_data.models import SearchInput
from trip_data.providers.base import ProviderFailure, ProviderRunner
from trip_data.providers.catalog import MockCatalog
from trip_data.providers.http import get_json


class FakeProvider:
    name = "fake"
    revision = "1"
    data_mode = "mock"

    def __init__(self, bundles=None, failure=None, delay=0):
        self.bundles = bundles or []
        self.failure = failure
        self.delay = delay
        self.calls = 0

    async def search(self, request):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise ProviderFailure(self.failure)
        return self.bundles


@pytest.fixture
def quote():
    return MockCatalog(Path("data/fixtures/sochi.json")).bundles[0].model_copy(deep=True)


def test_cache_survives_restart_and_expires(tmp_path, quote):
    path = tmp_path / "cache.sqlite"
    clock = [1000.0]
    provider = FakeProvider([quote])
    runner = ProviderRunner(SQLiteCache(path), cache_ttl_seconds=10, clock=lambda: clock[0])
    first = asyncio.run(runner.search(provider, quote.request))
    assert first.report.cache_hit is False
    # New runner/connection mimics process restart.
    restarted = ProviderRunner(SQLiteCache(path), clock=lambda: clock[0])
    cached = asyncio.run(restarted.search(provider, quote.request))
    assert cached.bundles[0].id == quote.id
    assert cached.report.cache_hit is True
    assert provider.calls == 1
    clock[0] = 1011
    asyncio.run(restarted.search(provider, quote.request))
    assert provider.calls == 2


def test_scope_key_contains_all_conditions(quote):
    original = cache_key("demo", quote.request)
    for field, value in [
        ("check_in", "2026-11-12"),
        ("budget", {"amount": "1"}),
        ("min_stars", 5),
        ("breakfast_required", False),
        ("guests", {"adults": 2, "children_ages": [7], "pets": 0}),
    ]:
        request = quote.request.model_dump(mode="json")
        request[field] = value
        assert cache_key("demo", type(quote.request).model_validate(request)) != original
    assert cache_key("other", quote.request) != original
    assert cache_key("demo", quote.request, "2") != original


def test_cache_not_shared_between_modes(tmp_path, quote):
    cache = SQLiteCache(tmp_path / "cache.sqlite")
    provider = FakeProvider([quote])
    runner = ProviderRunner(cache)
    asyncio.run(runner.search(provider, quote.request))
    provider.data_mode = "live"
    result = asyncio.run(runner.search(provider, quote.request))
    assert result.report.status == "invalid_response"
    assert not result.bundles


@pytest.mark.parametrize(
    "failure,attempts",
    [("unauthorized", 1), ("rate_limited", 1), ("unavailable", 2), ("timeout", 1)],
)
def test_failures_have_status_and_bounded_retries(tmp_path, quote, failure, attempts):
    provider = FakeProvider(failure=failure)
    runner = ProviderRunner(SQLiteCache(tmp_path / "cache.sqlite"))
    result = asyncio.run(runner.search(provider, quote.request))
    assert result.report.status == failure
    assert result.report.attempts == attempts
    assert result.bundles == []
    assert provider.calls == attempts


def test_deadline_cancels_hanging_provider(tmp_path, quote):
    runner = ProviderRunner(SQLiteCache(tmp_path / "cache.sqlite"), deadline_seconds=0.01)
    result = asyncio.run(runner.search(FakeProvider(delay=1), quote.request))
    assert result.report.status == "timeout"


def test_transient_failure_recovers(tmp_path, quote):
    class Flaky(FakeProvider):
        async def search(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderFailure("unavailable")
            return [quote]

    result = asyncio.run(
        ProviderRunner(SQLiteCache(tmp_path / "db")).search(Flaky(), quote.request)
    )
    assert result.report.status == "ok"
    assert result.report.attempts == 2


def test_corrupt_cache_is_ignored(tmp_path, quote):
    cache = SQLiteCache(tmp_path / "db")
    cache.put(cache_key("fake:mock", quote.request), "not json", 9e9)
    result = asyncio.run(ProviderRunner(cache).search(FakeProvider([quote]), quote.request))
    assert result.report.status == "ok"
    assert not result.report.cache_hit


def test_empty_not_confused_with_outage(tmp_path, quote):
    settings = Settings(cache_path=tmp_path / "cache.sqlite")
    payload = SearchInput(request=quote.request, plan_version=1).model_dump(mode="json")
    with TestClient(create_app(settings, FakeProvider())) as client:
        response = client.post("/api/v1/bundles/search", json=payload)
        assert response.status_code == 200
        assert response.json()["provider_reports"][0]["status"] == "empty"
    with TestClient(
        create_app(
            Settings(cache_path=tmp_path / "other.sqlite"), FakeProvider(failure="unauthorized")
        )
    ) as client:
        response = client.post("/api/v1/bundles/search", json=payload)
        assert response.status_code == 503
        assert response.json()["detail"]["provider_report"]["status"] == "unauthorized"


def test_cached_quote_is_revalidated_after_expiry(tmp_path, quote):
    from datetime import UTC, datetime, timedelta

    quote.provenance.kind = "snapshot"
    quote.provenance.fetched_at = datetime.now(UTC) - timedelta(hours=1)
    quote.provenance.valid_until = datetime.now(UTC) - timedelta(seconds=1)
    provider = FakeProvider([quote])
    runner = ProviderRunner(SQLiteCache(tmp_path / "db"))
    asyncio.run(runner.search(provider, quote.request))
    assert not asyncio.run(runner.search(provider, quote.request)).report.cache_hit


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "unauthorized"),
        (403, "unauthorized"),
        (429, "rate_limited"),
        (503, "unavailable"),
        (400, "invalid_response"),
    ],
)
def test_http_error_normalization(status, expected):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="sensitive provider message")
            )
        ) as client:
            with pytest.raises(ProviderFailure) as exc:
                await get_json(client, "https://example.com/api")
            assert exc.value.status == expected
            assert "sensitive" not in str(exc.value)

    asyncio.run(run())


def test_http_network_and_schema_failures():
    async def run():
        def fail(request):
            raise httpx.ReadTimeout("credential-bearing upstream URL")

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(ProviderFailure, match="timeout"):
                await get_json(client, "https://example.com")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))
        ) as client:
            with pytest.raises(ProviderFailure, match="invalid_response"):
                await get_json(client, "https://example.com")

    asyncio.run(run())


def test_requote_dates_and_child_from_separate_quotes(tmp_path):
    payload = json.loads(Path("data/fixtures/requote-request.json").read_text())
    with TestClient(create_app(Settings(cache_path=tmp_path / "db"))) as client:
        first = client.post("/api/v1/bundles/requote", json=payload)
        assert first.status_code == 200
        result = first.json()
        assert result["previous_total"]["amount"] == "73000.00"
        assert result["new_total"]["amount"] == "76000.00"
        assert result["price_delta"] == "3000.00"
        assert result["search"]["plan_version"] == 2
        assert len(result["invalidated_components"]) == 5
        repeat = client.post("/api/v1/bundles/requote", json=payload).json()
        assert repeat["search"]["provider_reports"][0]["cache_hit"]
        payload["request"]["guests"]["children_ages"] = [7]
        payload["plan_version"] = 3
        child = client.post("/api/v1/bundles/requote", json=payload).json()
        assert child["new_total"]["amount"] == "89000.00"
        assert not child["search"]["provider_reports"][0]["cache_hit"]
        payload["request"]["guests"]["children_ages"] = [6]
        uncovered = client.post("/api/v1/bundles/requote", json=payload).json()
        assert uncovered["new_total"] is None
        assert uncovered["price_delta"] is None
        payload["previous_bundle_id"] = "missing"
        assert client.post("/api/v1/bundles/requote", json=payload).status_code == 404
