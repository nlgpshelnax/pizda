from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIP_", env_file=".env", extra="ignore")
    # Live mode is intentionally unavailable until commercial contracts are confirmed.
    provider_mode: Literal["mock"] = "mock"
    catalog_path: Path = Path("data/fixtures/component-source.json")
    external_mode: Literal["mock", "live"] = "mock"
    liteapi_key: SecretStr | None = None
    liteapi_environment: Literal["sandbox", "production"] = "sandbox"
    travelpayouts_token: SecretStr | None = None
    component_catalog_path: Path = Path("data/fixtures/components.json")
    context_fixture_path: Path = Path("data/fixtures/context.json")
    knowledge_path: Path = Path("data/knowledge/destinations.json")
    database_path: Path = Path(".runtime/travel.sqlite3")
    hotel_snapshot_path: Path = Path("data/hotels/osm-properties.json")
    activities_snapshot_path: Path = Path("data/hotels/osm-activities.json")
    state_path: Path | None = None
    cache_path: Path | None = None
    cache_ttl_seconds: float = Field(default=900, gt=0)
    provider_deadline_seconds: float = Field(default=10, gt=0, le=60)
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def shared_database(self) -> "Settings":
        self.state_path = self.state_path or self.database_path
        self.cache_path = self.cache_path or self.database_path
        return self
