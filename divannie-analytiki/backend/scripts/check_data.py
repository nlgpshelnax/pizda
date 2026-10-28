import json

from trip_data.config import Settings
from trip_data.database import CatalogDB
from trip_data.operations import quality

report = quality(CatalogDB(Settings().database_path))
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["ok"] else 1)
