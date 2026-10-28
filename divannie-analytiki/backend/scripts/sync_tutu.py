"""Load undated Tutu schedule estimates into the catalog."""

import asyncio
import json

import httpx
from trip_data.config import Settings
from trip_data.database import CatalogDB, stamp
from trip_data.operations import AlreadyRunning, JobLock
from trip_data.providers.base import ProviderFailure
from trip_data.providers.tutu import CODES, refresh_schedule


async def main():
    settings = Settings()
    db = CatalogDB(settings.database_path)
    db.load_files(settings)
    results = []
    try:
        with JobLock(settings.database_path.with_suffix(".tutu.lock")):
            async with httpx.AsyncClient() as client:
                for origin, destination in [("Москва", "Казань"), ("Казань", "Москва")]:
                    started = stamp()
                    try:
                        result = await refresh_schedule(db, client, origin, destination)
                    except (ProviderFailure, httpx.HTTPError, ValueError, TypeError) as exc:
                        status = getattr(exc, "status", "unavailable")
                        source = f"tutu:{CODES[origin]}:{CODES[destination]}"
                        db.log(source, status, started, 0, status)
                        result = {"source": source, "status": status}
                    results.append(result)
    except AlreadyRunning:
        print(json.dumps({"status": "already_running"}))
        raise SystemExit(1) from None
    print(json.dumps(results, ensure_ascii=False))
    if any(r["status"] not in ("ok", "skipped", "empty") for r in results):
        raise SystemExit(1)


asyncio.run(main())
