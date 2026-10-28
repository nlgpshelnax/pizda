"""Repeatable ingestion jobs and quality checks. No credentials in job records."""

import asyncio
import os

if os.name == "nt":
    import msvcrt
else:
    import fcntl
import json
from datetime import UTC, datetime

import httpx

from trip_data.database import CatalogDB, stamp
from trip_data.live_ingestion import refresh_live
from trip_data.providers.base import ProviderFailure
from trip_data.providers.tutu import CODES, refresh_schedule


class AlreadyRunning(Exception):
    pass


class JobLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a")
        try:
            if os.name == "nt":
                self.file.seek(0)
                if self.path.stat().st_size == 0:
                    self.file.write("0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise AlreadyRunning("Ingestion is already running") from None
        return self

    def __exit__(self, *args):
        if os.name == "nt":
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


def quality(database, now=None):
    now = now or datetime.now(UTC).isoformat()
    findings = []
    with database.connect() as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            findings.append({"severity": "error", "code": "DATABASE_INTEGRITY"})
        if db.execute("PRAGMA foreign_key_check").fetchall():
            findings.append({"severity": "error", "code": "FOREIGN_KEYS"})
        for table in (
            "weather",
            "routes",
            "transport_estimates",
            "hotel_quotes",
            "xotelo_rates",
            "rail_schedule_estimates",
        ):
            # julianday compares instants regardless of ISO timezone representation.
            count = db.execute(
                f"SELECT count(*) FROM {table} WHERE julianday(valid_until)<=julianday(?)", (now,)
            ).fetchone()[0]
            if count:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "EXPIRED_RECORDS",
                        "table": table,
                        "count": count,
                    }
                )
        real_quotes = db.execute(
            "SELECT count(*) FROM hotel_quotes WHERE source_mode!='mock'"
        ).fetchone()[0]
        if not real_quotes:
            findings.append({"severity": "warning", "code": "NO_REAL_HOTEL_RATES"})
        latest = db.execute(
            "SELECT source_id,status FROM ingest_runs WHERE id IN "
            "(SELECT max(id) FROM ingest_runs GROUP BY source_id)"
        ).fetchall()
        for source, status in latest:
            if status not in ("ok", "empty", "skipped"):
                findings.append(
                    {
                        "severity": "warning",
                        "code": "SOURCE_FAILURE",
                        "source": source,
                        "status": status,
                    }
                )
    return {
        "checked_at": now,
        "ok": not any(v["severity"] == "error" for v in findings),
        "findings": findings,
    }


async def refresh_rail(database, settings):
    results = []
    try:
        with JobLock(settings.database_path.with_suffix(".tutu.lock")):
            async with httpx.AsyncClient() as client:
                for origin, destination in (("Москва", "Казань"), ("Казань", "Москва")):
                    source = f"tutu:{CODES[origin]}:{CODES[destination]}"
                    started = stamp()
                    try:
                        results.append(
                            await refresh_schedule(database, client, origin, destination)
                        )
                    except (ProviderFailure, httpx.HTTPError, ValueError, TypeError) as exc:
                        status = getattr(exc, "status", "unavailable")
                        database.log(source, status, started, 0, status)
                        results.append({"source": source, "status": status, "rows": 0})
    except AlreadyRunning:
        results.append({"source": "tutu", "status": "skipped", "rows": 0})
    return results


async def run_job(settings, *, online=True):
    lock = settings.database_path.with_suffix(".ingest.lock")
    with JobLock(lock):
        database = CatalogDB(settings.database_path)
        with database.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS ingestion_jobs "
                "(id INTEGER PRIMARY KEY,started_at TEXT,finished_at TEXT,"
                "status TEXT,report_json TEXT)"
            )
            job = db.execute(
                "INSERT INTO ingestion_jobs(started_at,status) VALUES(?,?)", (stamp(), "running")
            ).lastrowid
        try:
            loads = database.load_files(settings)
            if online:
                loads.extend(await refresh_live(database, settings))
                loads.extend(await refresh_rail(database, settings))
            database.populate_auxiliary()
            report = {"loads": loads, "quality": quality(database)}
            status = (
                "ok" if all(r["status"] in ("ok", "empty", "skipped") for r in loads) else "partial"
            )
        except asyncio.CancelledError:
            with database.connect() as db:
                db.execute(
                    "UPDATE ingestion_jobs SET finished_at=?,status=? WHERE id=?",
                    (stamp(), "cancelled", job),
                )
            raise
        except Exception as exc:
            status = "failed"
            report = {"error_code": type(exc).__name__}
        if "quality" in report and not report["quality"]["ok"]:
            status = "failed"
        with database.connect() as db:
            db.execute(
                "UPDATE ingestion_jobs SET finished_at=?,status=?,report_json=? WHERE id=?",
                (stamp(), status, json.dumps(report), job),
            )
        return {"job_id": job, "status": status, **report}


async def worker(settings, interval, once=False, offline=False):
    while True:
        try:
            result = await run_job(settings, online=not offline)
        except AlreadyRunning:
            result = {"status": "already_running"}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if once:
            return result["status"] in ("ok", "already_running")
        await asyncio.sleep(interval)
