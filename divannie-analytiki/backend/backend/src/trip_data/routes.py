"""Data endpoints for agent/UI integration; no chat orchestration is implemented here."""

import time
from datetime import date
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from trip_data.agent_context import CatalogContextQuery, CatalogContextResult, read_context
from trip_data.context_models import (
    ContextResult,
    FlightQuery,
    PlacesQuery,
    RouteQuery,
    WeatherQuery,
)
from trip_data.database import PUBLIC_TABLES
from trip_data.hotels import HotelSearch, HotelSearchResult
from trip_data.knowledge import EntryQuery, ExploreQuery, entry_rules, official_visa_source
from trip_data.models import SearchInput, SearchOutput, TripRequest
from trip_data.operations import quality
from trip_data.plan_models import (
    Checkout,
    DemoOrder,
    Plan,
    PlanPatch,
    Selection,
    ServiceDecision,
    ServiceInput,
    ServiceRequest,
)
from trip_data.providers.base import ProviderFailure
from trip_data.providers.external import OSRM, OpenMeteo, Overpass, Travelpayouts
from trip_data.providers.liteapi import HotelLookup, HotelRateQuery, lookup_hotels, search_rates
from trip_data.providers.passport_index import visa_reference
from trip_data.providers.tutu import CODES, DOC_URL, read_schedule
from trip_data.providers.xotelo import CITIES, current_estimates
from trip_data.service import build_search_result
from trip_data.state import StateError, apply_patch


class TourQuery(BaseModel):
    request: TripRequest
    plan_version: int = Field(default=1, ge=1)
    passport_country: str = Field(default="RU", pattern=r"^[A-Z]{2}$")
    real_only: bool = False


def register_routes(app: FastAPI, settings):
    def state_call(fn, *args):
        try:
            return fn(*args)
        except StateError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code}) from None

    @app.post("/api/v1/bundles/compose", response_model=SearchOutput)
    def compose(payload: SearchInput):
        catalog = app.state.database.component_catalog()
        if any(
            q.provenance.kind != "mock"
            for q in (*catalog.hotels, *catalog.transport, *catalog.transfers)
        ):
            raise HTTPException(503, detail={"code": "LIVE_COMPONENT_ACCESS_NOT_CONFIGURED"})
        return build_search_result(payload, catalog.build(payload.request, include_invalid=True))

    async def context(provider, query, allow_stale=False):
        if settings.external_mode == "mock":
            item = app.state.database.mock_context(provider.name, query.model_dump(mode="json"))
            result = ContextResult(
                provider="mock-" + provider.name,
                status="ok" if item is not None else "empty",
                data_mode="mock",
                data=item,
                warnings=["Synthetic context fixture; not live or bookable"],
            )
            return app.state.context_runner.finish(result, time.perf_counter())
        return await app.state.context_runner.run(
            provider, query, app.state.http, allow_stale=allow_stale
        )

    @app.post("/api/v1/tools/weather", response_model=ContextResult)
    async def weather(query: WeatherQuery, allow_stale: bool = False):
        return await context(OpenMeteo(), query, allow_stale)

    @app.post("/api/v1/tools/route", response_model=ContextResult)
    async def route(query: RouteQuery, allow_stale: bool = False):
        return await context(OSRM(), query, allow_stale)

    @app.post("/api/v1/tools/places", response_model=ContextResult)
    async def places(query: PlacesQuery, allow_stale: bool = False):
        return await context(Overpass(), query, allow_stale)

    @app.post("/api/v1/tools/flights", response_model=ContextResult)
    async def flights(query: FlightQuery, allow_stale: bool = False):
        return await context(Travelpayouts(settings.travelpayouts_token), query, allow_stale)

    @app.post("/api/v1/tools/rail")
    def rail(query: TripRequest):
        if settings.external_mode == "live":
            return {
                "status": "not_configured",
                "data_mode": "live",
                "quotes": [],
                "warning": "No licensed rail API is configured",
            }
        catalog = app.state.database.component_catalog()
        from trip_data.components import same_scope

        quotes = [
            q
            for q in catalog.transport
            if q.transport.mode == "train" and same_scope(q.scope, query)
        ]
        return {"status": "ok" if quotes else "empty", "data_mode": "mock", "quotes": quotes}

    @app.get("/api/v1/rail/schedule")
    def rail_schedule(origin: str, destination: str):
        rows = read_schedule(app.state.database, origin, destination)
        source = (
            f"tutu:{CODES[origin]}:{CODES[destination]}"
            if origin in CODES and destination in CODES and origin != destination
            else None
        )
        with app.state.database.connect() as db:
            last = db.execute(
                "SELECT status,started_at,finished_at,error_code FROM ingest_runs "
                "WHERE source_id=? ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
        last_sync = dict(last) if last else None
        warnings = [
            "Undated schedule and indicative fares, not real-time; "
            "cannot validate a dated connection. Times are Moscow time."
        ]
        if last_sync and last_sync["status"] not in ("ok", "empty", "skipped"):
            warnings.append("Latest source refresh failed; retained data may be older")
        return {
            "source": "tutu-travelpayouts",
            "last_sync": last_sync,
            "source_url": DOC_URL,
            "status": "ok" if rows else "empty",
            "data_mode": "snapshot",
            "bookable": False,
            "trips": rows,
            "warnings": warnings,
        }

    @app.post("/api/v1/explore")
    def destinations(query: ExploreQuery):
        entries = app.state.database.rows("destinations", limit=100)["rows"]
        categories = {
            "beach": ("beach",),
            "culture": ("culture", "museum"),
            "ski": ("ski",),
            "nature": ("nature",),
            "spa": ("spa",),
        }.get(query.vibe, ())
        counts = {}
        if categories:
            placeholders = ",".join("?" for _ in categories)
            with app.state.database.connect() as db:
                rows = db.execute(
                    "SELECT city_id,count(*),max(fetched_at) FROM activities WHERE active=1 "
                    "AND source_mode='snapshot' AND (source_id='osm_activities' "
                    "OR source_id LIKE 'eu:osm:%') AND category IN (" + placeholders + ") "
                    "GROUP BY city_id",
                    categories,
                ).fetchall()
                counts = {row[0]: {"count": row[1], "fetched_at": row[2]} for row in rows}
        candidates = []
        for row in entries:
            data = row["data"]
            evidence = counts.get(row["id"], {})
            count = evidence.get("count", 0)
            curated = query.vibe in data["vibes"] and query.month in data["months"]
            if count or (curated and not query.real_only):
                candidates.append(
                    {
                        **data,
                        "vibe_match": {
                            "vibe": query.vibe,
                            "osm_poi_count": count,
                            "fetched_at": evidence.get("fetched_at"),
                            "source": "openstreetmap" if count else "curated_hypothesis",
                            "season_verified": False,
                        },
                    }
                )
        return {
            "candidates": candidates,
            "warnings": [
                "OSM POI counts are sampled and may be outdated; "
                "they do not establish seasonal suitability",
                "Seasonality is an unverified team hypothesis, not a weather forecast",
                "No precise prices, availability or visa clearance are inferred",
            ],
        }

    @app.post("/api/v1/tools/entry-rules")
    def visas(query: EntryQuery):
        result = entry_rules(query)
        result["historical_reference"] = visa_reference(
            app.state.database, query.citizenship, query.destination_country
        )
        return result

    @app.get("/api/v1/visa/reference")
    def historical_visa_reference(passport: str, destination: str):
        if (
            len(passport) != 2
            or len(destination) != 2
            or not passport.isascii()
            or not destination.isascii()
            or not passport.isalpha()
            or not destination.isalpha()
        ):
            raise HTTPException(422, detail="Use two-letter country codes")
        return visa_reference(app.state.database, passport.upper(), destination.upper())

    @app.get("/api/v1/providers")
    def providers():
        return {
            "bundle_mode": settings.provider_mode,
            "external_mode": settings.external_mode,
            "travelpayouts_token_configured": bool(settings.travelpayouts_token),
            "hotel_live": "not_configured",
            "rail_live": "not_configured",
            "entry_rules_live": "not_configured",
        }

    @app.post("/api/v1/hotels/search", response_model=HotelSearchResult)
    def hotel_metadata(query: HotelSearch):
        return app.state.database.search_hotels(query)

    @app.post("/api/v1/hotels/provider-search")
    async def provider_hotels(query: HotelLookup):
        try:
            return await lookup_hotels(app.state.http, query, settings.liteapi_key)
        except ProviderFailure as exc:
            raise HTTPException(503, detail={"code": exc.status}) from None
        except (KeyError, TypeError, ValueError):
            raise HTTPException(503, detail={"code": "invalid_response"}) from None

    @app.post("/api/v1/hotels/rates")
    async def hotel_rates(query: HotelRateQuery):
        try:
            return await search_rates(
                app.state.http, query, settings.liteapi_key, settings.liteapi_environment
            )
        except ProviderFailure as exc:
            raise HTTPException(503, detail={"code": exc.status}) from None
        except (KeyError, TypeError, ValueError):
            raise HTTPException(503, detail={"code": "invalid_response"}) from None

    @app.post("/api/v1/tours/search")
    async def tours(query: TourQuery):
        request = query.request
        context = read_context(
            app.state.database,
            CatalogContextQuery(
                city=request.destination, start_date=request.check_in, end_date=request.check_out
            ),
        )
        if query.real_only:
            # No full verified real component bundle is configured yet.
            result = {
                "plan_version": query.plan_version,
                "data_mode": "none",
                "options": [],
                "rejected": {},
                "provider_reports": [],
                "limitations": [
                    "No verified real bundle is currently available; research data is not bookable"
                ],
            }
        else:
            catalog = app.state.database.component_catalog()
            if any(
                q.provenance.kind != "mock"
                for q in (*catalog.hotels, *catalog.transport, *catalog.transfers)
            ):
                raise HTTPException(503, detail={"code": "LIVE_COMPONENT_ACCESS_NOT_CONFIGURED"})
            result = build_search_result(
                SearchInput(request=request, plan_version=query.plan_version),
                catalog.build(request, include_invalid=True),
            )
        country = context.destination["country"] if context.destination else None
        with app.state.database.connect() as db:
            # These are only exact ordinary-tourist profiles, never inferred for transit.
            row = db.execute(
                "SELECT * FROM visa_rules WHERE passport_country=? AND destination_country=? "
                "AND passport_type='ordinary' AND purpose='tourism' LIMIT 1",
                (query.passport_country, country),
            ).fetchone()
        visa = dict(row) if row else {"visa_status": "unknown", "source_url": None}
        # Do not assert permission to enter from an unverified or expired record.
        if country:
            visa["source_url"] = official_visa_source(country)
            visa["historical_reference"] = visa_reference(
                app.state.database, query.passport_country, country
            )
        visa["requires_verification"] = True
        return {
            "search": result,
            "weather": context.sections.get("weather"),
            "visa": visa,
            "context_warnings": context.warnings,
            "connection_check": "validated_per_option_and_rejected_codes",
            "booking": "unavailable" if query.real_only else "demo_only",
        }

    @app.post("/api/v1/catalog/context", response_model=CatalogContextResult)
    def agent_catalog_context(query: CatalogContextQuery):
        return read_context(app.state.database, query)

    @app.get("/api/v1/hotels/estimates")
    def hotel_estimates(
        city: str,
        limit: int = 20,
        check_in: date | None = None,
        check_out: date | None = None,
        adults: int | None = None,
    ):
        if not 1 <= limit <= 50:
            raise HTTPException(422, detail="limit must be between 1 and 50")
        if (
            (check_in is None) != (check_out is None)
            or (check_in is not None and check_out <= check_in)
            or (adults is not None and not 1 <= adults <= 10)
        ):
            raise HTTPException(422, detail="Provide valid dates together and 1–10 adults")
        source = "xotelo:" + CITIES[city] if city in CITIES else None
        with app.state.database.connect() as db:
            row = db.execute(
                "SELECT status,started_at,finished_at,row_count,error_code FROM ingest_runs "
                "WHERE source_id=? ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
        last_sync = dict(row) if row else None
        warnings = ["Estimates only; verify availability, total and taxes with the seller"]
        if last_sync and last_sync["status"] not in ("ok", "empty", "skipped"):
            warnings.append(
                "Latest source refresh failed or partially failed; retained data may be older"
            )
        return {
            "source": "xotelo",
            "data_mode": "snapshot",
            "last_sync": last_sync,
            "status": "research_only",
            "bookable": False,
            "price_basis": "per_room_per_night",
            "taxes_confirmed": False,
            "estimates": current_estimates(
                app.state.database,
                city,
                limit,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
            ),
            "warnings": warnings,
        }

    @app.get("/api/v1/catalog-quality")
    def catalog_quality():
        return quality(app.state.database)

    @app.get("/api/v1/catalog")
    def catalog_summary():
        return app.state.database.summary()

    @app.get("/api/v1/catalog/{table}")
    def catalog_rows(
        table: str,
        city: str | None = None,
        source_mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        if table not in PUBLIC_TABLES:
            raise HTTPException(404, detail="Unknown public catalog table")
        try:
            return app.state.database.rows(
                table, city=city, source_mode=source_mode, limit=limit, offset=offset
            )
        except ValueError:
            raise HTTPException(422, detail="Unsupported filter or pagination") from None

    @app.get("/api/v1/metrics")
    def metrics():
        return app.state.context_runner.observations.metrics()

    @app.post("/api/v1/plans", response_model=Plan, status_code=201)
    async def create_plan(query: TripRequest):
        search = await app.state.search(SearchInput(request=query, plan_version=1))
        return state_call(
            app.state.store.create, Plan(id=str(uuid4()), version=1, request=query, search=search)
        )

    @app.get("/api/v1/plans/{plan_id}", response_model=Plan)
    def get_plan(plan_id: str):
        return state_call(app.state.store.get, plan_id)

    @app.patch("/api/v1/plans/{plan_id}", response_model=Plan)
    async def patch_plan(plan_id: str, patch: PlanPatch):
        previous = state_call(app.state.store.get, plan_id)
        if previous.version != patch.base_version:
            raise HTTPException(409, detail={"code": "STALE_PLAN_VERSION"})
        try:
            query = apply_patch(previous.request, patch.changes)
        except (ValueError, ValidationError):
            raise HTTPException(422, detail={"code": "INVALID_PATCH"}) from None
        version = previous.version + 1
        search = await app.state.search(SearchInput(request=query, plan_version=version))
        selected = (
            previous.selected_id
            if any(o.bundle.id == previous.selected_id for o in search.options)
            else None
        )
        if selected is None and previous.selected_id:
            old = next(
                (o.bundle for o in previous.search.options if o.bundle.id == previous.selected_id),
                None,
            )
            if old:
                old_property = old.hotel.location_id or old.hotel.id
                compatible = next(
                    (
                        o.bundle
                        for o in search.options
                        if (o.bundle.hotel.location_id or o.bundle.hotel.id) == old_property
                    ),
                    None,
                )
                if compatible:
                    selected = compatible.id
        result = Plan(
            id=plan_id, version=version, request=query, search=search, selected_id=selected
        )
        # CAS happens after provider calls too: a slow old response cannot replace newer state.
        return state_call(app.state.store.save, result, previous.version)

    @app.post("/api/v1/plans/{plan_id}/selection", response_model=Plan)
    def select(plan_id: str, selection: Selection):
        plan = state_call(app.state.store.get, plan_id)
        if plan.version != selection.base_version:
            raise HTTPException(409, detail={"code": "STALE_PLAN_VERSION"})
        if not any(o.bundle.id == selection.bundle_id for o in plan.search.options):
            raise HTTPException(422, detail={"code": "INVALID_SELECTION"})
        plan.selected_id = selection.bundle_id
        plan.version += 1
        plan.search.plan_version = plan.version
        return state_call(app.state.store.save, plan, selection.base_version)

    @app.post("/api/v1/plans/{plan_id}/checkout", response_model=DemoOrder)
    def checkout(plan_id: str, payload: Checkout):
        return state_call(
            app.state.store.checkout, plan_id, payload.base_version, payload.idempotency_key
        )

    @app.get("/api/v1/orders/{order_id}", response_model=DemoOrder)
    def order(order_id: str):
        return state_call(app.state.store.order, order_id)

    @app.post("/api/v1/orders/{order_id}/services", response_model=ServiceRequest)
    def request_service(order_id: str, payload: ServiceInput):
        return state_call(
            app.state.store.request_service, order_id, payload.kind, payload.idempotency_key
        )

    @app.get("/api/v1/orders/{order_id}/services", response_model=list[ServiceRequest])
    def list_services(order_id: str):
        return state_call(app.state.store.services, order_id)

    @app.post(
        "/api/v1/orders/{order_id}/services/{service_id}/simulate", response_model=ServiceRequest
    )
    def simulate_service(order_id: str, service_id: str, payload: ServiceDecision):
        if settings.provider_mode != "mock":
            raise HTTPException(403, detail="Supplier simulation is mock-only")
        return state_call(app.state.store.decide_service, order_id, service_id, payload.status)
