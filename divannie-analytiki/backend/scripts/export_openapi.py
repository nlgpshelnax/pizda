import json
from pathlib import Path

from trip_data.components import ComponentCatalog
from trip_data.hotels import HotelSnapshot
from trip_data.main import create_app

Path("docs/openapi.json").write_text(
    json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n"
)


Path("docs/components.schema.json").write_text(
    json.dumps(ComponentCatalog.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)

Path("docs/hotels.schema.json").write_text(
    json.dumps(HotelSnapshot.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
