"""Cimphawng API server.

Run locally:  uvicorn app.main:app --reload
In production it runs behind Caddy (see infra/), which serves the web app and forwards /api/* here.
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import auth, paper
from .config import Settings
from .models import Base
from .prices import GeckoTerminalFeed, PriceBook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()
    engine = create_async_engine(s.database_url, pool_pre_ping=True)
    book = PriceBook(s.price_max_age_s)

    async def init_db() -> None:
        # Tables are created on start-up for now; database migrations (Alembic) come with later schema changes.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        task = asyncio.create_task(GeckoTerminalFeed(book, s.price_refresh_s).run()) if s.price_feed else None
        yield
        if task:
            task.cancel()
        await engine.dispose()

    app = FastAPI(title="Cimphawng API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = s
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.prices = book
    app.state.init_db = init_db

    @app.middleware("http")
    async def json_only_writes(request: Request, call_next):
        # Cross-site forms can't send application/json, so requiring it on every write blocks CSRF,
        # on top of the SameSite=Lax session cookie.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "prices_fresh": book.fresh(), "prices": book.snapshot()}

    app.include_router(auth.router)
    app.include_router(paper.router)
    return app


app = create_app()
