import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ExploreQuery(BaseModel):
    month: int = Field(ge=1, le=12)
    real_only: bool = False
    vibe: Literal["beach", "nature", "city_walks", "culture", "ski", "family", "nightlife", "spa"]


class EntryQuery(BaseModel):
    citizenship: str = Field(pattern=r"^[A-Z]{2}$")
    destination_country: str = Field(pattern=r"^[A-Z]{2}$")
    passport_type: Literal["ordinary", "diplomatic", "other"] = "ordinary"
    purpose: Literal["tourism", "business", "other"] = "tourism"
    transit_countries: list[str] = Field(default_factory=list)
    travel_date: date
    duration_days: int = Field(ge=1, le=365)


def explore(query: ExploreQuery, path: Path):
    entries = json.loads(path.read_text())
    return {
        "candidates": [
            entry
            for entry in entries
            if query.vibe in entry["vibes"] and query.month in entry["months"]
        ],
        "warnings": [
            "Seasonality is an unverified team hypothesis, not a weather forecast",
            "No precise prices, availability or visa clearance are inferred",
        ],
    }


def official_visa_source(country: str):
    official_sources = {
        "EG": "https://www.visa2egypt.gov.eg/eVisa/FAQ",
        "AE": "https://u.ae/en/information-and-services/visa-and-emirates-id/"
        "Visa-information/do-you-need-an-entry-permit-or-a-visa-to-enter-the-uae",
    }
    return official_sources.get(country)


def entry_rules(query: EntryQuery):
    return {
        "status": "unknown",
        "profile": query.model_dump(mode="json"),
        "source": official_visa_source(query.destination_country),
        "checked_at": None,
        "warnings": [
            "No licensed/current visa-rule source is configured",
            "Verify citizenship, passport, transit and entry rules with official sources",
        ],
    }
