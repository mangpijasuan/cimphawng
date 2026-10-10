import time

from app.stats import RequestStats


async def test_stats_shape_and_counts(app, signed_in):
    app.state.settings.stats_cache_s = 0  # no caching in tests
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "10"})
    await signed_in.post("/api/paper/swap", content="x", headers={"content-type": "text/plain"})  # 415
    j = (await signed_in.get("/api/stats")).json()
    assert j["community"] == {"members": 1, "active_24h": 1, "paper_trades_total": 1,
                              "paper_trades_today": 1, "paper_trades_last_hour": 1}
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
