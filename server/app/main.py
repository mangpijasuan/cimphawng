"""Cimphawng API server.

Run locally:  uvicorn app.main:app --reload
In production it runs behind Caddy (see infra/), which serves the web app and forwards /api/* here.
"""

import asyncio
import contextlib
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import auth, bots, migrate, paper, stats
from .config import Settings
from .prices import GeckoTerminalFeed, PriceBook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()
    engine = create_async_engine(s.database_url, pool_pre_ping=True)
    book = PriceBook(s.price_max_age_s)

    async def init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(migrate.upgrade)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        tasks = []
        if s.price_feed:
            app.state.feed = GeckoTerminalFeed(book, s.price_refresh_s)
            tasks.append(asyncio.create_task(app.state.feed.run()))
            if s.bots_enabled:  # bots need the feed's pools for their candles
                app.state.bots.candles = app.state.feed.hourly_candles
                tasks.append(asyncio.create_task(app.state.bots.run()))
        yield
        for task in tasks:
            task.cancel()
        await engine.dispose()

    app = FastAPI(title="Cimphawng API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = s
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.prices = book
    app.state.init_db = init_db
    app.state.bots = bots.BotRunner(app.state.sessionmaker, book, s, candles=None)
    app.state.request_stats = stats.RequestStats()

    @app.middleware("http")
    async def json_only_writes(request: Request, call_next):
        # Cross-site forms can't send application/json, so requiring it on every write blocks CSRF,
        # on top of the SameSite=Lax session cookie.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
        return await call_next(request)

    # Added last, so it runs first: counts every /api request, including rejected and failed ones.
    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        t0, counted = time.perf_counter(), request.url.path.startswith("/api/")
        try:
            response = await call_next(request)
        except Exception:  # a crash becomes a 500; a cancelled request (client gone) isn't counted at all
            if counted:
                app.state.request_stats.record(500, (time.perf_counter() - t0) * 1000)
            raise
        if counted:
            app.state.request_stats.record(response.status_code, (time.perf_counter() - t0) * 1000)
        return response

    @app.get("/api/health")
    async def health():
        return {"ok": True, "prices_fresh": book.fresh(), "prices": book.snapshot()}

    app.include_router(auth.router)
    app.include_router(paper.router)
    app.include_router(bots.router)
    app.include_router(stats.router)
    return app


app = create_app()
