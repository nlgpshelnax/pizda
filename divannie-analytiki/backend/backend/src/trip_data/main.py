import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from trip_data.cache import SQLiteCache
from trip_data.config import Settings
from trip_data.context_models import ContextResult
from trip_data.database import CatalogDB, DatabaseBundleProvider, DatabaseBundles
from trip_data.models import RequoteInput, RequoteOutput, SearchInput, SearchOutput
from trip_data.providers.base import BundleProvider, ProviderRunner
from trip_data.resilience import ContextRunner
from trip_data.routes import register_routes
from trip_data.service import build_search_result
from trip_data.state import StateStore
from trip_data.validation import total_price


def create_app(settings: Settings | None = None, provider: BundleProvider | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = CatalogDB(settings.database_path)
        app.state.load_report = app.state.database.load_files(settings)
        with app.state.database.connect() as db:
            if db.execute("SELECT count(*) FROM ingest_sources").fetchone()[0] < 6:
                raise RuntimeError("Initial catalog load failed; inspect ingest_runs")
        app.state.catalog = DatabaseBundles(app.state.database)
        if not app.state.catalog.bundles:
            raise RuntimeError("Demo catalog is empty")
        app.state.provider = provider or DatabaseBundleProvider(app.state.database)
        if app.state.provider.data_mode != settings.provider_mode:
            raise RuntimeError("Provider mode must match application mode")
        app.state.runner = ProviderRunner(
            SQLiteCache(settings.cache_path),
            deadline_seconds=settings.provider_deadline_seconds,
            cache_ttl_seconds=settings.cache_ttl_seconds,
        )
        app.state.context_runner = ContextRunner(
            SQLiteCache(settings.cache_path), deadline=settings.provider_deadline_seconds
        )
        app.state.store = StateStore(settings.state_path)
        if settings.database_path.resolve() == Path(".runtime/travel.sqlite3").resolve():
            app.state.database.migrate_legacy(Path(".runtime"))
        async with httpx.AsyncClient() as http:
            app.state.http = http
            yield

    app = FastAPI(title="О!дин запрос — Data API", version="0.4.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "data_mode": "mock",
            "catalog_size": len(app.state.catalog.bundles),
            "cache": "sqlite",
            "catalog_database": "sqlite",
            "database_schema": app.state.database.summary()["schema_version"],
            "ingest_warnings": [
                r["source"] for r in app.state.load_report if r["status"] == "failed"
            ],
        }

    @app.post("/api/v1/bundles/search", response_model=SearchOutput)
    async def search(payload: SearchInput):
        outcome = await app.state.runner.search(app.state.provider, payload.request)
        report = outcome.report
        try:
            app.state.context_runner.observations.record(
                ContextResult(
                    provider=report.provider,
                    status=report.status,
                    data_mode="mock",
                    cache_hit=report.cache_hit,
                    latency_ms=report.latency_ms,
                )
            )
        except sqlite3.Error:
            pass
        if report.status not in ("ok", "empty"):
            status = 504 if report.status == "timeout" else 503
            raise HTTPException(
                status_code=status,
                detail={"code": "PROVIDER_FAILURE", "provider_report": report.model_dump()},
            )
        result = build_search_result(payload, outcome.bundles)
        result.provider_reports = [report]
        return result

    @app.post("/api/v1/bundles/requote", response_model=RequoteOutput)
    async def requote(payload: RequoteInput):
        # This legacy endpoint is stateless; /plans supplies persisted CAS for agent integration.
        previous = next(
            (b for b in app.state.catalog.bundles if b.id == payload.previous_bundle_id), None
        )
        if previous is None:
            raise HTTPException(status_code=404, detail="Previous bundle not found")
        result = await search(payload)
        old_total = total_price(previous)
        new_total = result.options[0].total if result.options else None
        quote_fields = ("origin", "destination", "check_in", "check_out", "guests")
        invalidated = (
            ["hotel", "outbound", "inbound", "outbound_transfer", "inbound_transfer"]
            if any(
                getattr(previous.request, key) != getattr(payload.request, key)
                for key in quote_fields
            )
            else []
        )
        return RequoteOutput(
            previous_bundle_id=previous.id,
            previous_total=old_total,
            new_total=new_total,
            price_delta=new_total.amount - old_total.amount if new_total else None,
            invalidated_components=invalidated,
            search=result,
        )

    app.state.search = search
    register_routes(app, settings)
    return app


app = create_app()
