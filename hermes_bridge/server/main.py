from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from . import db as db_mod
from .config import get_settings
from .routes_agents import router as agents_router
from .routes_files import router as files_router
from .routes_messages import router as messages_router

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Deferred to startup (not create_app/import time) so merely importing this module
    # never touches disk — matters for tests that build the app against a tmp_path DB.
    settings = get_settings()
    db_mod.init_db(settings.resolved_db_path)
    settings.resolved_files_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Hermes Bridge", lifespan=lifespan)

    @app.get("/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION}

    app.include_router(messages_router)
    app.include_router(agents_router)
    app.include_router(files_router)
    return app


app = create_app()
