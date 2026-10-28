"""Validate a component catalog or save an immutable local snapshot."""

import argparse
import hashlib
from pathlib import Path

from trip_data.components import ComponentCatalog

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["validate", "snapshot"])
parser.add_argument("source", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
catalog = ComponentCatalog.model_validate_json(args.source.read_text())
payload = catalog.model_dump_json(indent=2) + "\n"
print(
    f"properties={len(catalog.properties)} hotels={len(catalog.hotels)} "
    f"transport={len(catalog.transport)} transfers={len(catalog.transfers)}"
)
if args.command == "snapshot":
    if args.output is None:
        parser.error("snapshot requires --output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects pre-existing user snapshots.
    with args.output.open("x") as output:
        output.write(payload)
    print("sha256=" + hashlib.sha256(payload.encode()).hexdigest())
