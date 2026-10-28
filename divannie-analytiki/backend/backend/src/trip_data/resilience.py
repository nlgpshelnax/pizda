"""Durable observations, snapshots and per-provider circuit breakers."""

import asyncio
import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime

from pydantic import ValidationError

from trip_data.cache import SQLiteCache
from trip_data.context_models import ContextResult
from trip_data.providers.base import ProviderFailure


class Observations:
    def __init__(self, cache: SQLiteCache):
        self.cache = cache
        with cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                  id INTEGER PRIMARY KEY, provider TEXT, status TEXT, latency REAL,
                  cache_hit INTEGER, recorded REAL);
                CREATE TABLE IF NOT EXISTS snapshots (
                  key TEXT PRIMARY KEY, payload TEXT NOT NULL, recorded REAL NOT NULL);
            """)

            columns = {row[1] for row in db.execute("PRAGMA table_info(observations)")}
            if "stale" not in columns:
                db.execute("ALTER TABLE observations ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")

    def record(self, result: ContextResult):
        with self.cache.connect() as db:
            db.execute(
                "INSERT INTO observations(provider,status,latency,cache_hit,recorded,stale) "
                "VALUES(?,?,?,?,?,?)",
                (
                    result.provider,
                    result.fallback_reason or result.status,
                    result.latency_ms,
                    int(result.cache_hit),
                    time.time(),
                    int(result.stale),
                ),
            )

    def snapshot(self, key: str, payload: str):
        with self.cache.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", (key, payload, time.time())
            )

    def get_snapshot(self, key: str):
        with self.cache.connect() as db:
            row = db.execute("SELECT payload FROM snapshots WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def metrics(self):
        with self.cache.connect() as db:
            rows = db.execute(
                "SELECT provider,status,latency,cache_hit,stale FROM observations"
            ).fetchall()
        result = {}
        for provider, status, latency, cache, stale in rows:
            entry = result.setdefault(
                provider,
                {"calls": 0, "cache_hits": 0, "fallbacks": 0, "statuses": {}, "latencies_ms": []},
            )
            entry["calls"] += 1
            entry["cache_hits"] += cache
            entry["fallbacks"] += stale
            entry["statuses"][status] = entry["statuses"].get(status, 0) + 1
            entry["latencies_ms"].append(latency)
        for entry in result.values():
            latencies = sorted(entry.pop("latencies_ms"))
            for name, percentile in (("p50_ms", 0.5), ("p95_ms", 0.95)):
                import math

                entry[name] = latencies[max(0, math.ceil(len(latencies) * percentile) - 1)]
        return result


class ContextRunner:
    def __init__(
        self, cache: SQLiteCache, *, deadline=10, threshold=3, cooldown=30, clock=time.time
    ):
        self.cache = cache
        self.observations = Observations(cache)
        self.deadline = deadline
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.failures = {}
        self.semaphore = asyncio.Semaphore(4)

    async def run(self, provider, query, client, *, allow_stale=False):
        started = time.perf_counter()
        now = self.clock()
        key = hashlib.sha256(
            json.dumps(
                {"provider": provider.name, "schema": 1, "query": query.model_dump(mode="json")},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        try:
            cached = await asyncio.to_thread(self.cache.get, key, now)
        except sqlite3.Error:
            cached = None
        if cached:
            try:
                result = ContextResult.model_validate_json(cached)
                result.cache_hit = True
                return self.finish(result, started)
            except ValidationError:
                pass
        count, opened = self.failures.get(provider.name, (0, 0))
        if count >= self.threshold and now - opened < self.cooldown:
            return self.finish(
                ContextResult(provider=provider.name, status="circuit_open", data_mode="live"),
                started,
            )
        status, data = "unavailable", None
        attempts = 0
        try:
            async with asyncio.timeout(self.deadline):
                async with self.semaphore:
                    for attempt in range(2):
                        try:
                            attempts += 1
                            status, data = await provider.fetch(client, query)
                            break
                        except ProviderFailure as exc:
                            if attempt:
                                raise
                            if exc.status == "unavailable":
                                await asyncio.sleep(0.05)
                            elif (
                                exc.status == "rate_limited"
                                and exc.retry_after_seconds is not None
                                and exc.retry_after_seconds <= self.deadline
                            ):
                                await asyncio.sleep(exc.retry_after_seconds)
                            else:
                                raise
        except TimeoutError:
            status = "timeout"
        except ProviderFailure as exc:
            status = exc.status
        except (KeyError, IndexError, ValueError, TypeError):
            status = "invalid_response"
        if status in ("ok", "empty"):
            self.failures.pop(provider.name, None)
        elif status in ("unavailable", "timeout", "rate_limited", "invalid_response"):
            self.failures[provider.name] = (count + 1, now)
        result = ContextResult(
            provider=provider.name, status=status, data=data, data_mode="live", attempts=attempts
        )
        if status in ("ok", "empty"):
            ttl = provider.ttl
            if provider.name == "travelpayouts-data" and data:
                ttl = min(
                    ttl,
                    min(
                        datetime.fromisoformat(q["expires_at"].replace("Z", "+00:00")).timestamp()
                        - now
                        for q in data
                    ),
                )
            result.fetched_at = datetime.fromtimestamp(now, UTC)
            result.expires_at = datetime.fromtimestamp(now + ttl, UTC)
            try:
                await asyncio.to_thread(self.cache.put, key, result.model_dump_json(), now + ttl)
                if status == "ok":
                    await asyncio.to_thread(
                        self.observations.snapshot, key, result.model_dump_json()
                    )
            except sqlite3.Error:
                result.warnings.append("Local cache write unavailable")
        elif allow_stale and status in ("unavailable", "timeout", "rate_limited"):
            # Explicit research-only opt-in; never used for bundle quotes or booking.
            try:
                snapshot = await asyncio.to_thread(self.observations.get_snapshot, key)
                if snapshot:
                    result = ContextResult.model_validate_json(snapshot)
                    result.stale = True
                    result.fallback_reason = status
                    result.attempts = attempts
                    result.warnings.append("Expired research snapshot; not a current quote")
            except (sqlite3.Error, ValidationError):
                pass
        return self.finish(result, started)

    def finish(self, result, started):
        result.latency_ms = (time.perf_counter() - started) * 1000
        try:
            self.observations.record(result)
        except sqlite3.Error:
            pass
        return result
