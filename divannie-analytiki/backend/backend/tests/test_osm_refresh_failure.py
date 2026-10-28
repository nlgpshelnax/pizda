import runpy
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
from trip_data.config import Settings
from trip_data.database import CatalogDB


def test_osm_timeout_retains_snapshot_and_other_sources(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog.sqlite3"
    settings = Settings(database_path=db_path)
    database = CatalogDB(db_path)
    database.load_files(settings)
    before = database.summary()["hotel_modes"]

    async def failing_refresh(*args, **kwargs):
        raise httpx.ReadTimeout("simulated")

    monkeypatch.setenv("TRIP_DATABASE_PATH", str(db_path))
    monkeypatch.setattr("trip_data.hotels.refresh_snapshots", failing_refresh)
    monkeypatch.setattr(sys, "argv", ["load_database.py", "--refresh-hotels"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path("scripts/load_database.py")), run_name="__main__")
    assert exc.value.code == 1
    assert CatalogDB(db_path).summary()["hotel_modes"] == before
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT status,error_code FROM ingest_runs WHERE source_id='osm_refresh' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row == ("failed", "ReadTimeout")
