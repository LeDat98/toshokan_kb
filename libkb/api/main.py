"""FastAPI app factory. Run: uvicorn libkb.api.main:app --reload --port 8000"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libkb.api.routes import router
from libkb.config import get_settings
from libkb.library.store import LibraryStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.store = LibraryStore(settings.library_dir)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="LibraryKB API", version="0.1.0", lifespan=lifespan)
    # dev: the browser talks to the vite proxy, but allow direct :5173 access too
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
