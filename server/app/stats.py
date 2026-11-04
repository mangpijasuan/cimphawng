"""Live system stats for the public System monitor: real numbers only, no personal data.

Request counters live in memory (they reset when the server restarts). Database figures are cached
for a few seconds so many viewers don't add load.
"""

import asyncio
import logging
import os
import resource
import sys
import time
from collections import deque
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from sqlalchemy import case, func, select, text

from .models import PaperBot, PaperTrade, User, utcnow

router = APIRouter(prefix="/api")
log = logging.getLogger("cimphawng.stats")


class RequestStats:
    """Counts API requests per minute (last 60 minutes), errors and response times."""

    def __init__(self):
        self.started = time.time()
        self.total = 0
        self.by_class = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
        self.minutes: deque[list] = deque(maxlen=60)  # [minute, requests, server errors, total ms]

    def record(self, status: int, ms: float) -> None:
        self.total += 1
        self.by_class[f"{min(max(status // 100, 2), 5)}xx"] += 1
        minute = int(time.time() // 60)
        if not self.minutes or self.minutes[-1][0] != minute:
            self.minutes.append([minute, 0, 0, 0.0])
        m = self.minutes[-1]
        m[1] += 1
        m[2] += status >= 500
        m[3] += ms

    def series(self, n: int = 30) -> list[dict]:
        """Requests per minute for the last n minutes, oldest first, including quiet minutes."""
        now = int(time.time() // 60)
        by_min = {m[0]: m for m in self.minutes}
        out = []
        for minute in range(now - n + 1, now + 1):
            m = by_min.get(minute)
            out.append({"requests": m[1] if m else 0, "errors": m[2] if m else 0,
                        "avg_ms": round(m[3] / m[1], 1) if m and m[1] else None})
        return out


def _rss_mb() -> float:
    # ru_maxrss is kilobytes on Linux and bytes on macOS; this is the peak memory of the process
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


async def _db_stats(request: Request) -> dict:
    """Cached; one refresh at a time (others wait for it), and a database failure doesn't hide other stats."""
    app = request.app
    if not hasattr(app.state, "db_stats_lock"):
        app.state.db_stats_lock = asyncio.Lock()

    def cached():
        c = getattr(app.state, "db_stats_cache", None)
        return c[1] if c and time.time() - c[0] < app.state.settings.stats_cache_s else None

    if (hit := cached()) is not None:
        return hit
    async with app.state.db_stats_lock:
        if (hit := cached()) is not None:  # another request refreshed it while we waited
            return hit
        try:
            out = await _query_db_stats(app)
        except Exception as e:
            log.warning("database stats failed: %s", e)
            out = {"db": {"engine": app.state.engine.dialect.name, "ok": False, "error": type(e).__name__},
                   "community": None}
        app.state.db_stats_cache = (time.time(), out)
        return out


def _count_if(cond):
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


async def _query_db_stats(app) -> dict:
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    t0 = time.perf_counter()
    async with app.state.sessionmaker() as db:
        await db.execute(text("SELECT 1"))
        ping_ms = round((time.perf_counter() - t0) * 1000, 2)
        # each table in one query, so its numbers come from the same snapshot
        members, active = (await db.execute(select(
            func.count(), _count_if(User.last_seen_at >= now - timedelta(hours=24))).select_from(User))).one()
        bots_on = await db.scalar(select(func.count()).select_from(PaperBot).where(PaperBot.enabled.is_(True)))
        trades_total, trades_today, trades_hour = (await db.execute(select(
            func.count(), _count_if(PaperTrade.created_at >= day_start),
            _count_if(PaperTrade.created_at >= now - timedelta(hours=1))).select_from(PaperTrade))).one()
        if db.bind.dialect.name == "postgresql":
            size = await db.scalar(text("SELECT pg_database_size(current_database())"))
        else:
            path = Path(app.state.engine.url.database or "")
            size = path.stat().st_size if path.is_file() else None
    return {
        "db": {"engine": app.state.engine.dialect.name, "ok": True, "ping_ms": ping_ms,
               "size_mb": round(size / 1e6, 2) if size is not None else None},
        "community": {"members": members, "active_24h": int(active), "paper_trades_total": trades_total,
                      "paper_trades_today": int(trades_today), "paper_trades_last_hour": int(trades_hour),
                      "bots_on": bots_on},
    }


@router.get("/stats")
async def stats(request: Request):
    app = request.app
    rs: RequestStats = app.state.request_stats
    feed = getattr(app.state, "feed", None)
    load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
    return {
        "server": {
            "uptime_s": round(time.time() - rs.started),
            "python": sys.version.split()[0],
            "memory_peak_mb": _rss_mb(),
            "load_avg": [round(x, 2) if x is not None else None for x in load],
            "cpus": os.cpu_count(),
        },
        "api": {
            "requests_total": rs.total,
            "by_status": rs.by_class,
            "per_minute": rs.series(30),
        },
        "prices": {
            "fresh": app.state.prices.fresh(),
            "assets": app.state.prices.snapshot(),
            "max_age_s": app.state.prices.max_age_s,
            "refresh_ok": feed.ok if feed else None,
            "refresh_failed": feed.failed if feed else None,
            "last_error": feed.last_error if feed else None,
            "pools": {a: p for a, (p, _) in feed.pools.items()} if feed else {},
        },
        "bots": {
            "running": bool(app.state.bots.candles),
            "ticks": app.state.bots.ticks,
            "trades": app.state.bots.trades,
            "last_error": app.state.bots.last_error,
        },
        **(await _db_stats(request)),
    }
