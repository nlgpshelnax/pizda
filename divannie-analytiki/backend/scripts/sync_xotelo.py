"""Refresh a small, date-scoped set of research estimates from Xotelo."""

import argparse
import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import httpx
from trip_data.config import Settings
from trip_data.database import CatalogDB, stamp
from trip_data.operations import AlreadyRunning, JobLock
from trip_data.providers.base import ProviderFailure
from trip_data.providers.xotelo import CITIES, refresh_city

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--city", choices=list(CITIES))
parser.add_argument("--adults", type=int, default=2)
parser.add_argument("--interval", type=int, help="Repeat every N seconds (minimum 1800)")
parser.add_argument("--check-in", type=date.fromisoformat)
parser.add_argument("--check-out", type=date.fromisoformat)
args = parser.parse_args()
if not 1 <= args.adults <= 10:
    parser.error("Adults must be between 1 and 10")
if args.interval is not None and args.interval < 1800:
    parser.error("Minimum interval is 1800 seconds")
if bool(args.check_in) != bool(args.check_out):
    parser.error("Specify both check-in and check-out")
if args.check_in and args.check_out <= args.check_in:
    parser.error("Check-out must be later than check-in")


async def main():
    start = args.check_in or datetime.now(UTC).date() + timedelta(days=21)
    end = args.check_out or start + timedelta(days=5)
    db = CatalogDB(Settings().database_path)
    db.load_files(Settings())
    results = []
    try:
        with JobLock(Settings().database_path.with_suffix(".xotelo.lock")):
            async with httpx.AsyncClient() as client:
                for city in [args.city] if args.city else CITIES:
                    started = stamp()
                    try:
                        result = await refresh_city(db, client, city, start, end, args.adults)
                        failures = [
                            x for x in result["rates"] if x["status"] not in ("ok", "empty")
                        ]
                        status = "partial" if failures else "ok"
                        db.log(
                            "xotelo:" + CITIES[city],
                            status,
                            started,
                            result["hotels"],
                            failures[0]["status"] if failures else None,
                        )
                    except (ProviderFailure, httpx.HTTPError, ValueError, TypeError) as exc:
                        status = getattr(exc, "status", "unavailable")
                        result = {"city": city, "status": status}
                        db.log("xotelo:" + CITIES[city], status, started, 0, status)
                    results.append(result)
    except AlreadyRunning:
        print(json.dumps({"status": "already_running"}), flush=True)
        raise SystemExit(1) from None
    print(json.dumps(results, ensure_ascii=False), flush=True)
    if any(
        r.get("status") or any(x["status"] not in ("ok", "empty") for x in r.get("rates", []))
        for r in results
    ):
        raise SystemExit(1)


async def loop():
    while True:
        try:
            await main()
        except SystemExit as exc:
            if args.interval is None:
                raise
            print(json.dumps({"status": "partial", "exit_code": exc.code}), flush=True)
        if args.interval is None:
            return
        await asyncio.sleep(args.interval)


try:
    asyncio.run(loop())
except KeyboardInterrupt:
    raise SystemExit(0) from None
