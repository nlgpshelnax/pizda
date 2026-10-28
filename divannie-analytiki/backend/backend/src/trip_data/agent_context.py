"""Bounded, database-only research context. Never fetches external providers."""

import json
from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, model_validator


class CatalogContextQuery(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    origin: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def period(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Supply both dates or neither")
        if self.start_date and self.end_date <= self.start_date:
            raise ValueError("end_date must follow start_date")
        return self


class CatalogContextResult(BaseModel):
    status: str
    read_from: str = "database"
    checked_at: datetime
    bookable: bool = False
    destination: dict | None = None
    sections: dict[str, dict] = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def read_context(database, query: CatalogContextQuery, now=None):
    now = now or datetime.now(UTC)
    warnings = [
        "Research context only; use a guest/date-scoped bundle search for a trip total",
        "OSM metadata has no guaranteed validity period or hotel availability",
        "Destination vibes and seasonality are unverified team hypotheses",
    ]
    with database.connect() as db:
        # Keep all sections consistent while an ingestion job commits updates.
        db.execute("BEGIN")
        destination = db.execute(
            "SELECT * FROM destinations WHERE city=?", (query.city,)
        ).fetchone()
        if destination is None:
            return CatalogContextResult(
                status="not_found", checked_at=now, warnings=["Destination is not in the catalog"]
            )
        destination = dict(destination)
        destination["data"] = json.loads(destination.pop("payload_json"))
        city_id = destination["id"]
        sections = {}
        source_ids = {destination["source_id"]}

        def section(name, where, params, order):
            # name/where/order are internal constants, user values are bound parameters.
            total = db.execute(f"SELECT count(*) FROM {name} WHERE {where}", params).fetchone()[0]
            records = db.execute(
                f"SELECT * FROM {name} WHERE {where} ORDER BY {order} LIMIT ?",
                [*params, query.limit],
            ).fetchall()
            rows = []
            for record in records:
                row = dict(record)
                source_ids.add(row["source_id"])
                if "payload_json" in row:
                    row["data"] = json.loads(row.pop("payload_json"))
                rows.append(row)
            sections[name] = {
                "status": "ok" if total else "missing",
                "total": total,
                "limit": query.limit,
                "truncated": total > len(rows),
                "rows": rows,
            }
            if not total:
                warnings.append(f"NO_MATCHING_DATA:{name}")

        section("hotels", "city_id=? AND active=1 AND source_mode!='mock'", [city_id], "id")
        section("activities", "city_id=? AND active=1 AND source_mode!='mock'", [city_id], "id")
        fresh = "city_id=? AND source_mode!='mock' AND julianday(valid_until)>julianday(?)"
        common = [city_id, now.isoformat()]
        weather_where, weather_params = fresh, list(common)
        if query.start_date:
            weather_where += " AND date>=? AND date<?"
            weather_params += [query.start_date.isoformat(), query.end_date.isoformat()]
        else:
            weather_where += " AND date>=?"
            weather_params += [now.date().isoformat()]
        section("weather", weather_where, weather_params, "date,id")
        section("routes", fresh, common, "id")
        flight_where, flight_params = fresh, list(common)
        if query.origin:
            flight_where += " AND origin=?"
            flight_params.append(query.origin)
        if query.start_date:
            flight_where += " AND substr(departure_at,1,10)=? AND substr(return_at,1,10)=?"
            flight_params += [query.start_date.isoformat(), query.end_date.isoformat()]
        else:
            flight_where += " AND julianday(departure_at)>julianday(?)"
            flight_params.append(now.isoformat())
        section("transport_estimates", flight_where, flight_params, "departure_at,id")
        sources = [
            dict(row)
            for source_id in sorted(source_ids)
            for row in db.execute("SELECT * FROM ingest_sources WHERE id=?", (source_id,))
        ]
    warnings += [
        "Flight estimates are cached tickets, not a group quote or confirmed availability",
        "Routes are specific coordinate pairs; fares are unknown",
        "Missing data requires a loader refresh or clarification; do not invent values",
    ]
    return CatalogContextResult(
        status="ok",
        checked_at=now,
        destination=destination,
        sections=sections,
        sources=sources,
        warnings=warnings,
    )
