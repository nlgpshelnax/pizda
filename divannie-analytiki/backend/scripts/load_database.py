"""One-command catalog load. Default is offline; --online refreshes available API sources."""

import argparse
import asyncio
import json
from xml.etree.ElementTree import ParseError

import httpx
from trip_data.config import Settings
from trip_data.database import CatalogDB, stamp
from trip_data.hotels import refresh_snapshots

parser = argparse.ArgumentParser()
parser.add_argument("--online", action="store_true")
parser.add_argument("--refresh-hotels", action="store_true")
args = parser.parse_args()


async def main():
    settings = Settings()
    database = CatalogDB(settings.database_path)
    refresh_failed = False
    if args.refresh_hotels:
        started = stamp()
        try:
            refreshed = await refresh_snapshots(
                settings.hotel_snapshot_path, settings.activities_snapshot_path
            )
            database.log(
                "osm_refresh", "ok", started, refreshed["hotels"] + refreshed["activities"]
            )
            print(json.dumps({"osm_refresh": refreshed}, ensure_ascii=False))
        except (httpx.HTTPError, OSError, ParseError, ValueError) as exc:
            refresh_failed = True
            database.log("osm_refresh", "failed", started, 0, type(exc).__name__)
    results = database.load_files(settings)
    if args.online:
        from trip_data.live_ingestion import refresh_live

        results.extend(await refresh_live(database, settings))
    print(
        json.dumps({"loads": results, "database": database.summary()}, ensure_ascii=False, indent=2)
    )
    if refresh_failed or any(row["status"] not in ("ok", "skipped", "empty") for row in results):
        raise SystemExit(1)


asyncio.run(main())
