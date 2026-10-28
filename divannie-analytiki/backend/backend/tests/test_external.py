import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import SecretStr
from trip_data.cache import SQLiteCache
from trip_data.context_models import FlightQuery, PlacesQuery, RouteQuery, WeatherQuery
from trip_data.providers.base import ProviderFailure
from trip_data.providers.external import OSRM, OpenMeteo, Overpass, Travelpayouts
from trip_data.resilience import ContextRunner


def run(coro):
    return asyncio.run(coro)


def test_weather_coverage_and_daily_schema():
    today = datetime.now(UTC).date()
    calls = []

    async def check():
        def respond(request):
            calls.append(request)
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": [today.isoformat()],
                        "temperature_2m_min": [10],
                        "temperature_2m_max": [20],
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            q = WeatherQuery(latitude=43.6, longitude=39.73, start_date=today, end_date=today)
            status, data = await OpenMeteo().fetch(client, q)
            assert status == "ok" and data["days"][0]["max_c"] == 20
            q.end_date = today + timedelta(days=100)
            assert (await OpenMeteo().fetch(client, q))[0] == "out_of_coverage"
            assert len(calls) == 1

    run(check())


def test_route_lon_lat_no_fare_and_overpass_query():
    async def check():
        def respond(request):
            if "osrm" in request.url.host:
                assert "/39.73,43.6;40.0,44.0" in request.url.path
                return httpx.Response(
                    200, json={"code": "Ok", "routes": [{"distance": 1000, "duration": 600}]}
                )
            assert "natural" in request.url.params["data"]
            assert "out tags 30" in request.url.params["data"]
            return httpx.Response(
                200, json={"elements": [{"type": "way", "id": 1, "tags": {"name": "sample"}}]}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            _, route = await OSRM().fetch(
                client,
                RouteQuery(
                    origin={"latitude": 43.6, "longitude": 39.73},
                    destination={"latitude": 44, "longitude": 40},
                ),
            )
            assert route["fare"] is None
            assert route["duration_seconds"] == 600
            _, places = await Overpass().fetch(
                client, PlacesQuery(latitude=43.6, longitude=39.73, category="beach")
            )
            assert places[0]["id"] == "way/1"

    run(check())


def test_travelpayouts_header_scope_expiry_and_missing_key():
    today = datetime.now(UTC).date()
    q = FlightQuery(
        origin="MOW",
        destination="AER",
        departure_date=today + timedelta(days=2),
        return_date=today + timedelta(days=7),
    )

    def quote(expires):
        return {
            "price": 10000,
            "airline": "XX",
            "departure_at": q.departure_date.isoformat() + "T09:00:00Z",
            "return_at": q.return_date.isoformat() + "T12:00:00Z",
            "expires_at": expires,
        }

    calls = []

    async def check():
        def respond(request):
            calls.append(request)
            assert request.headers["X-Access-Token"] == "test-only"
            assert "token" not in request.url.params
            assert request.url.params["currency"] == "rub"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "AER": {
                            "0": quote((datetime.now(UTC) + timedelta(minutes=10)).isoformat()),
                            "1": quote("2000-01-01T00:00:00Z"),
                        }
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert (await Travelpayouts(None).fetch(client, q))[0] == "not_configured"
            assert calls == []
            status, data = await Travelpayouts(SecretStr("test-only")).fetch(client, q)
            assert status == "ok" and len(data) == 1
            assert data[0]["bookable"] is False
            assert data[0]["price_basis"] == "provider_cached_ticket"
            assert "X-Access-Token" not in client.headers

    run(check())


def test_context_retry_after_and_circuit_breaker(tmp_path):
    q = PlacesQuery(latitude=43.6, longitude=39.73, category="beach")

    class Broken:
        name = "broken"
        ttl = 1
        calls = 0

        async def fetch(self, client, query):
            self.calls += 1
            raise ProviderFailure("unavailable")

    clock = [1000]
    runner = ContextRunner(
        SQLiteCache(tmp_path / "db"), threshold=2, cooldown=30, clock=lambda: clock[0]
    )
    provider = Broken()

    async def check():
        assert (await runner.run(provider, q, None)).status == "unavailable"
        assert (await runner.run(provider, q, None)).status == "unavailable"
        assert provider.calls == 4
        assert (await runner.run(provider, q, None)).status == "circuit_open"
        assert provider.calls == 4
        clock[0] += 31
        assert (await runner.run(provider, q, None)).status == "unavailable"
        assert provider.calls == 6

        class Limited:
            name = "limited"
            ttl = 1
            calls = 0

            async def fetch(self, client, query):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderFailure("rate_limited", retry_after_seconds=0)
                return "ok", []

        limited = Limited()
        assert (await runner.run(limited, q, None)).status == "ok"
        assert limited.calls == 2

    run(check())
    assert runner.observations.metrics()["broken"]["statuses"]["circuit_open"] == 1


def test_context_cache_snapshot_explicit_only(tmp_path):
    q = PlacesQuery(latitude=43.6, longitude=39.73, category="beach")

    class Provider:
        name = "snapshot-test"
        ttl = 1
        broken = False

        async def fetch(self, client, query):
            if self.broken:
                raise ProviderFailure("timeout")
            return "ok", [{"id": "source-only"}]

    clock = [1000.0]
    provider = Provider()
    runner = ContextRunner(SQLiteCache(tmp_path / "db"), clock=lambda: clock[0])

    async def check():
        assert (await runner.run(provider, q, None)).stale is False
        assert (await runner.run(provider, q, None)).cache_hit is True
        provider.broken = True
        clock[0] += 2
        assert (await runner.run(provider, q, None)).status == "timeout"
        stale = await runner.run(provider, q, None, allow_stale=True)
        assert stale.stale and stale.warnings
        assert stale.fallback_reason == "timeout"
        assert stale.data == [{"id": "source-only"}]
        assert stale.expires_at.timestamp() < clock[0]

    run(check())
    observed = runner.observations.metrics()["snapshot-test"]
    assert observed["fallbacks"] == 1
    assert observed["statuses"]["timeout"] == 2


def test_invalid_provider_schema_is_an_error_not_empty(tmp_path):
    q = RouteQuery(
        origin={"latitude": 0, "longitude": 0}, destination={"latitude": 1, "longitude": 1}
    )

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"code": "Ok", "routes": []})
            )
        ) as client:
            result = await ContextRunner(SQLiteCache(tmp_path / "db")).run(OSRM(), q, client)
            assert result.status == "invalid_response"

    run(check())
