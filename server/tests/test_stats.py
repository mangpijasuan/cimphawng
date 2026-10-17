import time

from app.stats import RequestStats


async def test_stats_shape_and_counts(app, signed_in):
    app.state.settings.stats_cache_s = 0  # no caching in tests
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "10"})
    await signed_in.post("/api/paper/swap", content="x", headers={"content-type": "text/plain"})  # 415
    j = (await signed_in.get("/api/stats")).json()
    assert j["community"] == {"members": 1, "active_24h": 1, "paper_trades_total": 1,
                              "paper_trades_today": 1, "paper_trades_last_hour": 1, "bots_on": 0}
    assert j["api"]["requests_total"] == 4  # nonce, verify, swap, rejected post (this request counts after it answers)
    assert j["api"]["by_status"]["4xx"] >= 1  # the rejected form post is counted
    assert len(j["api"]["per_minute"]) == 30 and j["api"]["per_minute"][-1]["requests"] == 4
    assert j["prices"]["fresh"] is True and set(j["prices"]["assets"]) == {"ETH", "cbBTC"}
    assert j["db"]["ping_ms"] >= 0 and j["db"]["engine"] in ("sqlite", "postgresql")
    assert j["server"]["uptime_s"] >= 0 and j["server"]["memory_peak_mb"] > 0


async def test_stats_has_no_personal_data(app, signed_in, wallet):
    body = (await signed_in.get("/api/stats")).text.lower()
    assert wallet.address.lower()[2:] not in body
    assert "cookie" not in body and "session" not in body


async def test_stats_is_public(client):
    assert (await client.get("/api/stats")).status_code == 200


async def test_db_figures_are_cached(app, signed_in):
    app.state.settings.stats_cache_s = 60
    first = (await signed_in.get("/api/stats")).json()["community"]["paper_trades_total"]
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "10"})
    assert (await signed_in.get("/api/stats")).json()["community"]["paper_trades_total"] == first


def test_series_fills_quiet_minutes():
    rs = RequestStats()
    rs.record(200, 5.0)
    rs.record(503, 15.0)
    rs.minutes.appendleft([int(time.time() // 60) - 3, 4, 0, 40.0])  # 3 minutes ago
    s = rs.series(5)
    assert [m["requests"] for m in s] == [0, 4, 0, 0, 2]
    assert s[-1] == {"requests": 2, "errors": 1, "avg_ms": 10.0}
    assert rs.by_class == {"2xx": 1, "3xx": 0, "4xx": 0, "5xx": 1}


async def test_database_failure_keeps_other_stats(app, client, monkeypatch):
    from app import stats as st

    async def broken(_app):
        raise ConnectionError("db down")

    monkeypatch.setattr(st, "_query_db_stats", broken)
    app.state.settings.stats_cache_s = 0
    r = await client.get("/api/stats")
    assert r.status_code == 200
    j = r.json()
    assert j["db"] == {"engine": app.state.engine.dialect.name, "ok": False, "error": "ConnectionError"}
    assert j["community"] is None and j["server"]["uptime_s"] >= 0 and "fresh" in j["prices"]


async def test_concurrent_viewers_share_one_database_refresh(app, client, monkeypatch):
    import asyncio

    from app import stats as st

    calls, real = [], st._query_db_stats

    async def counted(a):
        calls.append(1)
        await asyncio.sleep(0.05)
        return await real(a)

    monkeypatch.setattr(st, "_query_db_stats", counted)
    app.state.settings.stats_cache_s = 60
    results = await asyncio.gather(*[client.get("/api/stats") for _ in range(10)])
    assert all(r.status_code == 200 for r in results) and len(calls) == 1


async def test_reset_keeps_community_trade_totals(app, signed_in):
    app.state.settings.stats_cache_s = 0
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "10"})
    await signed_in.post("/api/paper/reset", json={})
    assert (await signed_in.get("/api/paper/trades")).json()["trades"] == []  # member's history is cleared
    c = (await signed_in.get("/api/stats")).json()["community"]
    assert c["paper_trades_total"] == 1 and c["paper_trades_today"] == 1  # but the swap still happened


async def test_active_members_counts_ongoing_sessions(app, signed_in):
    from datetime import timedelta

    from sqlalchemy import update

    from app.models import User, utcnow

    app.state.settings.stats_cache_s = 0
    two_days_ago = utcnow() - timedelta(days=2)
    async with app.state.sessionmaker() as db:
        await db.execute(update(User).values(last_login_at=two_days_ago, last_seen_at=two_days_ago))
        await db.commit()
    assert (await signed_in.get("/api/stats")).json()["community"]["active_24h"] == 0
    await signed_in.get("/api/me")  # still using a valid session from an older sign-in
    assert (await signed_in.get("/api/stats")).json()["community"]["active_24h"] == 1


async def test_crash_counts_as_500_but_cancelled_request_does_not(app):
    import asyncio

    import httpx

    @app.get("/api/_boom")
    async def boom():
        raise ValueError("boom")

    @app.get("/api/_slow")
    async def slow():
        await asyncio.sleep(5)
        return {}

    rs = app.state.request_stats
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test") as c:
        assert (await c.get("/api/_boom")).status_code == 500
        assert rs.by_class["5xx"] == 1
        total = rs.total
        task = asyncio.create_task(c.get("/api/_slow"))
        await asyncio.sleep(0.2)
        task.cancel()  # like the server cancelling a request whose client went away
        try:
            await task
        except BaseException:
            pass
    assert rs.by_class["5xx"] == 1 and rs.total == total  # the cancelled request isn't counted
