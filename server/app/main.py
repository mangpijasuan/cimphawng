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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import account, auth, bots, migrate, paper, stats
from .config import Settings
from .prices import GeckoTerminalFeed, PriceBook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def features(s: Settings) -> dict:
    """What this server can do, so the web app only offers what exists (it sends request IDs when `idempotency`)."""
    return {"wallet_signin": True, "paper_trading": True, "paper_bots": s.bots_enabled and s.price_feed,
            "real_trading": False, "testnet_lab": True, "idempotency": True, "account_export": True,
            "account_delete": True}


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
        # on top of the SameSite=Lax session cookie. Browsers also say where a write came from, so a write
        # from another site is refused outright.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in s.allowed_origins:
                return JSONResponse({"detail": "Cross-origin writes are blocked."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site writes are blocked."}, status_code=403)
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
        return {"ok": True, "mode": "paper-only", "backend": "fastapi", "features": features(s),
                "prices_fresh": book.fresh(), "prices": book.snapshot()}

    @app.get("/api/ready")
    async def ready():
        """For the status page and uptime monitors: 200 when the database answers and prices are fresh,
        503 when degraded (paper fills are blocked, never filled at invented prices)."""
        try:
            async with app.state.sessionmaker() as db:
                await db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"ok": False, "status": "unavailable", "database": "unreachable",
                                 "features": features(s)}, status_code=503)
        fresh = book.fresh()
        feed = getattr(app.state, "feed", None)
        return JSONResponse({
            "ok": fresh, "status": "ready" if fresh else "degraded", "database": "reachable",
            "features": features(s),
            "feed": [{"asset": a, "age_s": p["age_s"]} for a, p in book.snapshot().items()],
            "refresh": {"ok": feed.ok, "failed": feed.failed, "last_error": feed.last_error} if feed else None,
        }, status_code=200 if fresh else 503)

    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(paper.router)
    app.include_router(bots.router)
    app.include_router(stats.router)
    return app


app = create_app()
