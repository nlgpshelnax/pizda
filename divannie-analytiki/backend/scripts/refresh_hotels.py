"""Explicit bounded refresh. OSM is parsed once for hotels and activities."""

import argparse
import asyncio
from pathlib import Path

from trip_data.hotels import refresh_snapshots

parser = argparse.ArgumentParser()
parser.add_argument("--from-local", type=Path)
parser.add_argument("--output", type=Path, default=Path("data/hotels/osm-properties.json"))
parser.add_argument(
    "--activities-output", type=Path, default=Path("data/hotels/osm-activities.json")
)
args = parser.parse_args()
print(asyncio.run(refresh_snapshots(args.output, args.activities_output, args.from_local)))
