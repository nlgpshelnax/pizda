"""Sync European research data once or continuously; never fabricate live offers."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from trip_data.config import Settings
from trip_data.database import CatalogDB, stamp
from trip_data.europe_sync import CATALOG, sync
from trip_data.operations import AlreadyRunning, JobLock

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--once", action="store_true")
parser.add_argument("--wait-first", action="store_true", help="Wait one interval before first run")
parser.add_argument("--weather-only", action="store_true", help="Refresh current weather only")
parser.add_argument("--interval", type=int, default=7200)
parser.add_argument(
    "--city", action="append", help="Exact destination name; repeat to select several"
)
parser.add_argument("--limit", type=int, help="Only first N destinations, for smoke checks")
args = parser.parse_args()
if args.once and args.wait_first:
    parser.error("--wait-first cannot be combined with --once")
if args.interval < 3600:
    parser.error("Minimum interval is 3600 seconds")
if args.limit is not None and args.limit < 1:
    parser.error("Limit must be positive")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def main():
    config = Settings()
    specs = json.loads(Path(CATALOG).read_text())
    if args.city:
        selected = set(args.city)
        specs = [spec for spec in specs if spec[1] in selected]
        if len(specs) != len(selected):
            raise ValueError("Unknown city in --city")
    if args.limit:
        specs = specs[: args.limit]
    if args.wait_first:
        await asyncio.sleep(args.interval)
    while True:
        started = stamp()
        database = CatalogDB(config.database_path)
        try:
            with JobLock(config.database_path.with_suffix(".europe.lock")):
                result = await sync(database, config, specs, weather_only=args.weather_only)
            status = (
                "partial" if result["failures"] or result["overpass_state"] != "available" else "ok"
            )
            database.log(
                "europe_weather_sync" if args.weather_only else "europe_sync",
                status,
                started,
                result["geocoded"],
            )
            print(json.dumps({"status": status, **result}, ensure_ascii=False), flush=True)
        except AlreadyRunning:
            logging.warning("European sync is already running")
            status = "already_running"
        except Exception as exc:
            status = "failed"
            database.log("europe_sync", status, started, 0, type(exc).__name__)
            logging.warning("European sync failed: %s", type(exc).__name__)
        if args.once:
            return 0 if status == "ok" else 1
        await asyncio.sleep(args.interval)


try:
    raise SystemExit(asyncio.run(main()))
except KeyboardInterrupt:
    raise SystemExit(0) from None
