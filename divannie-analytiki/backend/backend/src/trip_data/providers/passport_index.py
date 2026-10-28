"""Unverified historical Passport Index dataset; never an entry determination."""

import re
from datetime import UTC, datetime

from trip_data.database import identity, stamp
from trip_data.providers.base import ProviderFailure
from trip_data.providers.http import get_json

REPO = "https://github.com/imorte/passport-index-data"
RAW = "https://raw.githubusercontent.com/imorte/passport-index-data"


async def refresh_passport_index(database, client, countries):
    commit = await get_json(
        client, "https://api.github.com/repos/imorte/passport-index-data/commits/main"
    )
    sha = commit.get("sha", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ProviderFailure("invalid_response")
    response = await client.get(f"{RAW}/{sha}/README.md", timeout=15)
    response.raise_for_status()
    match = re.search(r"Last updated:\s*\*\*(\d{1,2} [A-Za-z]+ \d{4})\*\*", response.text)
    if not match:
        raise ProviderFailure("invalid_response")
    try:
        dataset_date = datetime.strptime(match.group(1), "%d %B %Y").date()
    except ValueError:
        raise ProviderFailure("invalid_response") from None
    if dataset_date > datetime.now(UTC).date():
        raise ProviderFailure("invalid_response")
    data = await get_json(client, f"{RAW}/{sha}/passport-index.json", timeout=20)
    ru = data.get("RU")
    if not isinstance(ru, dict):
        raise ProviderFailure("invalid_response")
    allowed = {"visa free", "visa on arrival", "eta", "e-visa", "visa required", "no admission"}
    rows = []
    for country in sorted(set(countries)):
        item = ru.get(country)
        if not isinstance(item, dict) or item.get("status") not in allowed:
            continue
        days = item.get("days")
        if days is not None and (
            isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 366
        ):
            raise ProviderFailure("invalid_response")
        rows.append(
            {
                "id": identity(["RU", country]),
                "passport_country": "RU",
                "destination_country": country,
                "status_raw": item["status"],
                "days": days,
                "dataset_date": dataset_date.isoformat(),
                "commit_sha": sha,
                "source_url": f"{REPO}/blob/{sha}/passport-index.json",
            }
        )
    payload = {"rows": rows, "fetched_at": stamp(), "commit_sha": sha}

    def importer(db, value, source):
        for row in value["rows"]:
            database.upsert(
                db,
                "passport_index_reference",
                {**row, "source_id": source, "fetched_at": value["fetched_at"]},
            )
        return len(value["rows"])

    return database.ingest("passport_index_reference", payload, importer)


def visa_reference(database, passport, destination):
    with database.connect() as db:
        row = db.execute(
            "SELECT * FROM passport_index_reference WHERE passport_country=? "
            "AND destination_country=?",
            (passport, destination),
        ).fetchone()
    return {
        "status": "historical_unverified" if row else "missing",
        "record": dict(row) if row else None,
        "requires_verification": True,
        "warnings": [
            "Third-party historical dataset, not a current entry decision; "
            "verify official sources and transit"
        ],
    }
