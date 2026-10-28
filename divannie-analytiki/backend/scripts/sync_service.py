"""Run the existing bounded catalog synchronization once or as a foreground worker."""

import argparse
import asyncio

from trip_data.config import Settings
from trip_data.operations import worker

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--once", action="store_true")
parser.add_argument("--offline", action="store_true")
parser.add_argument("--interval", type=int, default=1800)
args = parser.parse_args()
if args.interval < 60:
    parser.error("Minimum interval is 60 seconds")
try:
    result = asyncio.run(worker(Settings(), args.interval, args.once, args.offline))
except KeyboardInterrupt:
    raise SystemExit(0) from None
if args.once and not result:
    raise SystemExit(1)
