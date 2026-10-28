"""Provider boundary shared by future commercial bundle adapters."""

import asyncio
import json
import sqlite3
import time
from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from trip_data.cache import SQLiteCache, cache_key
from trip_data.models import Bundle, ProviderReport, TripRequest

Status = Literal["timeout", "unauthorized", "rate_limited", "unavailable", "invalid_response"]


class ProviderFailure(Exception):
    def __init__(self, status: Status, retry_after_seconds: float | None = None):
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(status)  # Never expose credential-bearing provider errors.


class BundleProvider(Protocol):
    name: str
    revision: str
    data_mode: Literal["mock", "live"]

    async def search(self, request: TripRequest) -> list[Bundle]: ...


class ProviderOutcome(BaseModel):
    bundles: list[Bundle]
    report: ProviderReport


class ProviderRunner:
    def __init__(
        self,
        cache: SQLiteCache,
        *,
        deadline_seconds: float = 10,
        cache_ttl_seconds: float = 900,
        clock: Callable[[], float] = time.time,
    ):
        self.cache = cache
        self.deadline = deadline_seconds
        self.ttl = cache_ttl_seconds
        self.clock = clock
        self.semaphore = asyncio.Semaphore(4)

    async def search(self, provider: BundleProvider, request: TripRequest) -> ProviderOutcome:
        started = time.perf_counter()
        key = cache_key(f"{provider.name}:{provider.data_mode}", request, provider.revision)
        attempts = 0

        def outcome(bundles, status, cache_hit=False):
            return ProviderOutcome(
                bundles=bundles,
                report=ProviderReport(
                    provider=provider.name,
                    status=status,
                    cache_hit=cache_hit,
                    attempts=attempts,
                    latency_ms=(time.perf_counter() - started) * 1000,
                ),
            )

        # Local cache failure must not suppress provider access.
        try:
            cached = await asyncio.to_thread(self.cache.get, key, self.clock())
            if cached is not None:
                bundles = [Bundle.model_validate(item) for item in json.loads(cached)]
                if provider.data_mode == "live" and any(
                    bundle.provenance.kind == "mock" for bundle in bundles
                ):
                    raise ValueError("Invalid cached data mode")
                return outcome(bundles, "ok" if bundles else "empty", True)
        except (sqlite3.Error, ValueError, TypeError):
            pass
        try:
            async with asyncio.timeout(self.deadline):
                async with self.semaphore:
                    for attempt in range(2):
                        attempts += 1
                        try:
                            bundles = await provider.search(request)
                            # Revalidate at the boundary, including custom provider implementations.
                            bundles = [Bundle.model_validate(item) for item in bundles]
                            if provider.data_mode == "live" and any(
                                b.provenance.kind == "mock" for b in bundles
                            ):
                                raise ProviderFailure("invalid_response")
                            break
                        except ProviderFailure as exc:
                            if exc.status != "unavailable" or attempt == 1:
                                raise
                            await asyncio.sleep(0.05)
        except TimeoutError:
            return outcome([], "timeout")
        except ProviderFailure as exc:
            return outcome([], exc.status)
        except (ValidationError, ValueError, TypeError):
            return outcome([], "invalid_response")
        expires = self.clock() + self.ttl
        # Never keep a live/snapshot quote beyond provider validity.
        for bundle in bundles:
            sources = [bundle.provenance] + [
                c.provenance
                for c in (bundle.hotel, bundle.outbound, bundle.inbound, *bundle.transfers())
            ]
            for source in sources:
                if source and source.kind != "mock":
                    expires = min(expires, source.valid_until.timestamp())
        try:
            await asyncio.to_thread(
                self.cache.put,
                key,
                json.dumps([b.model_dump(mode="json") for b in bundles]),
                expires,
            )
        except sqlite3.Error:
            pass
        return outcome(bundles, "ok" if bundles else "empty")
