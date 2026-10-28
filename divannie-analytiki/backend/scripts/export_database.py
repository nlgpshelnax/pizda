"""Export catalog tables only. Excludes plans, orders, credentials and runtime caches."""

import argparse
from pathlib import Path

from trip_data.config import Settings
from trip_data.database import CatalogDB

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path(".runtime/catalog-export.sqlite3"))
parser.add_argument("--real-only", action="store_true", help="Export European research data only")
args = parser.parse_args()
if args.output.exists():
    parser.error("Output already exists; choose a new path to preserve it")
source = CatalogDB(Settings().database_path)
target = CatalogDB(args.output)
tables = [
    "ingest_sources",
    "destinations",
    "hotels",
    "guests",
    "calendar_dates",
    "hotel_quotes",
    "transport_quotes",
    "transfer_quotes",
    "bundles",
    "weather",
    "routes",
    "activities",
    "transport_estimates",
    "visa_rules",
    "budget_statistics",
    "ingest_runs",
    "catalog_metadata",
    "context_fixtures",
    "xotelo_hotels",
    "xotelo_rates",
    "rail_schedule_estimates",
    "passport_index_reference",
]
with source.connect() as src, target.connect() as dst:
    src.execute("BEGIN")
    for table in tables:
        fields = [row[1] for row in src.execute(f"PRAGMA table_xinfo({table})") if row[6] == 0]
        if args.real_only:
            filters = {
                "ingest_sources": "id LIKE 'eu:%' OR id='passport_index_reference'",
                "destinations": "id LIKE 'eu-%'",
                "hotels": "source_id LIKE 'eu:osm:%' AND active=1",
                "activities": "source_id LIKE 'eu:osm:%' AND active=1",
                "weather": "source_id LIKE 'eu:%' AND julianday(valid_until)>julianday('now')",
                "routes": "source_id LIKE 'eu:osrm:%' AND julianday(valid_until)>julianday('now')",
                "transport_estimates": "source_id LIKE 'eu:flights:%' "
                "AND julianday(valid_until)>julianday('now')",
                "visa_rules": "source_mode='unknown' AND destination_country IN "
                "(SELECT DISTINCT country FROM destinations WHERE id LIKE 'eu-%')",
                "passport_index_reference": "passport_country='RU'",
                "ingest_runs": "source_id LIKE 'eu:%' OR source_id='passport_index_reference'",
            }
            where = filters.get(table, "0")
        else:
            where = "1"
        values = src.execute(f"SELECT {','.join(fields)} FROM {table} WHERE {where}").fetchall()
        dst.executemany(
            f"INSERT INTO {table}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
            values,
        )
    assert dst.execute("PRAGMA foreign_key_check").fetchall() == []
print(args.output)
