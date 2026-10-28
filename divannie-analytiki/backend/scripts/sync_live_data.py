"""Compatibility entry point for the European live-data worker."""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "backend/scripts/sync_live_data.py"),
    run_name="__main__",
)
