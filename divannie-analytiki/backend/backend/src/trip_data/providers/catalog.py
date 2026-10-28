import json
from pathlib import Path
from typing import Protocol

from trip_data.models import Bundle, TripRequest


class CatalogProvider(Protocol):
    def search(self, request: TripRequest) -> list[Bundle]: ...


class MockCatalog:
    """Immutable synthetic quotes. Never stretch prices to new dates or occupancy."""

    def __init__(self, path: Path):
        self.bundles = [Bundle.model_validate(item) for item in json.loads(path.read_text())]
        if any(bundle.provenance.kind != "mock" for bundle in self.bundles):
            raise ValueError("MockCatalog accepts only explicitly synthetic bundles")

    def search(self, request: TripRequest) -> list[Bundle]:
        return [item for item in self.bundles if item.request.destination == request.destination]


class MockBundleProvider:
    name = "demo-catalog"
    data_mode = "mock"

    def __init__(self, catalog: MockCatalog):
        import hashlib

        self.catalog = catalog
        content = "".join(bundle.model_dump_json() for bundle in catalog.bundles)
        self.revision = hashlib.sha256(content.encode()).hexdigest()

    async def search(self, request: TripRequest) -> list[Bundle]:
        return [bundle.model_copy(deep=True) for bundle in self.catalog.search(request)]
