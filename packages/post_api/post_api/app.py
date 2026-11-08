"""App factory: `create_app(registry_path)`. No module-level "open project" global (T10
spec) -- the registry and the runtime manager both live on `app.state`, created fresh by
this factory, so two `create_app()` calls (e.g. two test clients) never share state."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from post_core.cli import config as config_mod

from .errors import install_error_handlers
from .ingest_jobs import IngestJobs
from .registry import ProjectRegistry
from .routes import (
    brand_kits, brand_page, cuts, decisions, doctor, enrich, events, export, ingest, library, media, project_new, projects, queue,
    sources, suggest, transcribe, transcripts, workflows,
)
from .runtime import RuntimeManager


def create_app(registry_path: str | Path) -> FastAPI:
    registry = ProjectRegistry(registry_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # T35: the repo's `.env` (Deepgram's key), as the CLI does -- never overriding a variable
        # that is really set, never logging a value. Workers the queue starts inherit it.
        config_mod.load_env()
        app.state.registry = registry
        app.state.runtimes = RuntimeManager()
        app.state.ingest_jobs = IngestJobs()
        # Re-open every already-registered project's background executor thread on startup
        # (a fresh process has no in-memory record of which projects were open before), and
        # mark any T34 ingest job a previous process left `running` as interrupted.
        for entry in registry.list():
            app.state.runtimes.open(entry["id"], entry["root"])
            app.state.ingest_jobs.recover(entry["root"])
        try:
            yield
        finally:
            app.state.runtimes.stop_all()

    app = FastAPI(title="post_api", lifespan=lifespan)
    install_error_handlers(app)

    for router_module in (
        project_new, projects, sources, ingest, transcribe, transcripts, cuts, workflows, enrich, suggest, decisions,
        queue, export, doctor, media, events, library,
    ):
        app.include_router(router_module.router)
    app.include_router(media.assets_router)
    app.include_router(doctor.global_router)
    app.include_router(sources.shoots_router)
    app.include_router(brand_kits.router)
    app.include_router(brand_page.router)

    return app


__all__ = ["create_app"]
