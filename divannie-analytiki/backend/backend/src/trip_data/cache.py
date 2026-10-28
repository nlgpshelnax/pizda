"""Exact-scope TTL cache. No expired fallback and no secrets in stored keys."""

import hashlib
import json
import sqlite3
from pathlib import Path

from trip_data.models import TripRequest


def cache_key(provider: str, request: TripRequest, revision: str = "1") -> str:
    payload = {
        "provider": provider,
        "revision": revision,
        "request": request.model_dump(mode="json"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class SQLiteCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS provider_cache (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL)""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def get(self, key: str, now: float) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload, expires_at FROM provider_cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            if row[1] <= now:
                db.execute("DELETE FROM provider_cache WHERE key = ?", (key,))
                return None
            return row[0]

    def put(self, key: str, payload: str, expires_at: float):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO provider_cache VALUES (?, ?, ?)", (key, payload, expires_at)
            )
