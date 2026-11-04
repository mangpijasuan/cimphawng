import asyncio
import math
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.bots import HOUR, closed_only, rsi, sma, want_long
from app.models import PaperBot, PaperTrade
from app.prices import TOKENS, USDC, GeckoTerminalFeed, PriceBook

from .conftest import TEST_DB

NOW = 1_800_000_000 + 1800  # half way through an hour


def hours(closes, now=NOW, open_candle=True):
    """Candles ending with the newest closed one; plus the still-open candle, as GeckoTerminal sends it."""
    last_closed = (now // HOUR - 1) * HOUR
    cs = [(last_closed - (len(closes) - 1 - i) * HOUR, c) for i, c in enumerate(closes)]
    return cs + ([(last_closed + HOUR, closes[-1] * 5)] if open_candle else [])


UP = [1000 + 10 * i for i in range(80)]  # steady rise: MA20 > MA50 and RSI 100
DOWN = [2000 - 10 * i for i in range(80)]  # steady fall: MA20 < MA50 and RSI 0


def feed(app, series):
    async def candles(asset):
        return hours(series[asset] if isinstance(series, dict) else series)
    app.state.bots.candles = candles


async def start(client, **kw):
    body = {"strategy": "ma", "asset": "ETH", "size_pct": 100, "enabled": True, **kw}
    r = await client.post("/api/bot", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def balances(client):
    return {b["asset"]: Decimal(b["amount"]) for b in (await client.get("/api/paper")).json()["balances"]}


def test_indicators_match_the_web_app():
    assert sma([1, 2, 3, 4, 5], 2) == [None, 1.5, 2.5, 3.5, 4.5]
    assert rsi(UP)[-1] == 100 and rsi(DOWN)[-1] == 0 and rsi([1.0] * 10)[-1] is None
    # A value worked through by hand with the index.html formula: gains 1,1 then a loss of 1, n=2
    xs = [10, 11, 12, 11]
    assert math.isclose(rsi(xs, 2)[2], 100) and math.isclose(rsi(xs, 2)[3], 100 - 100 / (1 + 0.5 / 0.5))
    assert want_long("ma", UP) is True and want_long("ma", DOWN) is False and want_long("ma", UP[:40]) is None
    assert want_long("rsi", DOWN) is True and want_long("rsi", UP) is False
    assert want_long("rsi", [100 + (i % 2) for i in range(80)]) is None  # RSI near 50: hold


def test_open_candle_is_never_used():
    cs = hours([1.0, 2.0, 3.0])
    assert closed_only(cs, NOW) == cs[:-1]


async def test_ma_bot_buys_on_an_uptrend_once_per_candle(app, signed_in):
    feed(app, UP)
    j = await start(signed_in)
    assert j["bot"]["enabled"] is True and j["bot"]["last_note"] == "started"
    await app.state.bots.tick(NOW)
    bal = await balances(signed_in)
    assert "USDC" in bal and bal["USDC"] == 0 and bal["ETH"] == Decimal("0.0498500")  # $100 - 0.3% at $2000
    await app.state.bots.tick(NOW + 60)  # same candle: nothing more
    j = (await signed_in.get("/api/bot")).json()
    assert len(j["trades"]) == 1 and j["trades"][0]["source"] == "bot"
    assert j["bot"]["last_signal"] == "in" and j["bot"]["last_note"].startswith("bought 0.04985 ETH")
    assert j["signal"]["want"] == "in" and j["signal"]["candle_at"] == hours(UP)[-2][0]
    # the member's own history shows it too, marked as the bot's
    assert (await signed_in.get("/api/paper/trades")).json()["trades"][0]["source"] == "bot"


async def test_buys_only_when_out_and_sells_everything(app, signed_in):
    feed(app, UP)
    await start(signed_in, size_pct=50)
    await app.state.bots.tick(NOW)
    assert (await balances(signed_in))["USDC"] == 50
    feed(app, UP + [UP[-1] + 10])  # next hour, still "in": it already holds ETH, so no second buy
    await app.state.bots.tick(NOW + HOUR)
    assert (await balances(signed_in))["USDC"] == 50
    await start(signed_in, strategy="rsi")  # RSI is 100 on this rise: sell
    await app.state.bots.tick(NOW + HOUR)
    bal = await balances(signed_in)
    assert "ETH" not in bal and bal["USDC"] < 100
    j = (await signed_in.get("/api/bot")).json()
    assert [t["from_asset"] for t in j["trades"]] == ["ETH", "USDC"] and j["bot"]["last_signal"] == "out"


async def test_out_signal_with_nothing_to_sell_does_nothing(app, signed_in):
    feed(app, DOWN)
    await start(signed_in)
    await app.state.bots.tick(NOW)
    j = (await signed_in.get("/api/bot")).json()
    assert j["trades"] == [] and j["bot"]["last_signal"] == "out" and "nothing to do" in j["bot"]["last_note"]


async def test_stale_prices_wait_without_using_up_the_candle(app, signed_in):
    feed(app, UP)
    await start(signed_in)
    app.state.prices.set("ETH", Decimal("2000"), at=0)
    await app.state.bots.tick(NOW)
    j = (await signed_in.get("/api/bot")).json()
    assert j["trades"] == [] and j["bot"]["last_note"] == "waiting for live prices"
    app.state.prices.set("ETH", Decimal("2000"))
    await app.state.bots.tick(NOW + 60)
    assert len((await signed_in.get("/api/bot")).json()["trades"]) == 1


async def test_needs_history_and_recent_candles(app, signed_in):
    feed(app, UP[:30])
    await start(signed_in)
    await app.state.bots.tick(NOW)
    assert (await signed_in.get("/api/bot")).json()["bot"]["last_note"] == "waiting for enough price history"
    feed(app, UP)
    app.state.bots._cache.clear()
    await app.state.bots.tick(NOW + 5 * HOUR)  # newest candle is 5 hours old: the data source is behind
    j = (await signed_in.get("/api/bot")).json()
    assert j["trades"] == [] and j["bot"]["last_note"] == "price history is behind; waiting"


async def test_stopped_bot_does_nothing_and_candle_errors_are_reported(app, signed_in):
    feed(app, UP)
    await start(signed_in, enabled=False)
    await app.state.bots.tick(NOW)
    assert (await signed_in.get("/api/bot")).json()["trades"] == []

    async def broken(asset):
        raise httpx.ConnectError("no route")
    app.state.bots.candles = broken
    await start(signed_in)
    await app.state.bots.tick(NOW)
    assert "ConnectError" in app.state.bots.last_error["error"]
    assert (await signed_in.get("/api/bot")).json()["trades"] == []
    s = (await signed_in.get("/api/stats")).json()
    assert s["community"]["bots_on"] == 1 and s["bots"]["ticks"] == 2


async def test_each_member_has_their_own_bot(app, client, signed_in):
    from eth_account import Account

    from .conftest import sign_in

    feed(app, {"ETH": UP, "cbBTC": DOWN})
    await start(signed_in)
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    async with other:
        assert (await sign_in(other, Account.create())).status_code == 200
        assert (await other.get("/api/bot")).json()["bot"] is None
        await start(other, strategy="rsi", asset="cbBTC")  # falling: RSI 0, buy
        await app.state.bots.tick(NOW)
        assert (await balances(other))["cbBTC"] > 0 and (await balances(signed_in))["ETH"] > 0
        assert len((await other.get("/api/bot")).json()["trades"]) == 1


async def test_bot_settings_are_checked(client, signed_in):
    assert (await client.post("/api/bot", json={"strategy": "moon", "asset": "ETH", "enabled": True})).status_code == 400
    assert (await client.post("/api/bot", json={"strategy": "ma", "asset": "DOGE", "enabled": True})).status_code == 400
    r = await client.post("/api/bot", json={"strategy": "ma", "asset": "ETH", "size_pct": 5, "enabled": True})
    assert r.status_code == 422
    r = await client.post("/api/bot", content='{"strategy":"ma"}', headers={"content-type": "text/plain"})
    assert r.status_code == 415
    await client.post("/api/auth/logout", json={})
    assert (await client.get("/api/bot")).status_code == 401


@pytest.mark.skipif(not TEST_DB, reason="row locks need PostgreSQL")
async def test_two_runners_never_trade_the_same_candle_twice(app, signed_in):
    from app.bots import BotRunner

    feed(app, UP)
    await start(signed_in, size_pct=50)  # half the USDC stays, so a second buy would go through if allowed
    other = BotRunner(app.state.sessionmaker, app.state.prices, app.state.settings, app.state.bots.candles)
    await asyncio.gather(app.state.bots.tick(NOW), other.tick(NOW))
    async with app.state.sessionmaker() as db:
        trades = (await db.execute(select(PaperTrade).where(PaperTrade.source == "bot"))).scalars().all()
    assert len(trades) == 1


async def test_hourly_candles_from_geckoterminal():
    pool = "0x" + "a" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        if "/tokens/" in request.url.path:
            return httpx.Response(200, json={"data": [{"attributes": {"address": pool, "reserve_in_usd": "1"},
                "relationships": {"base_token": {"data": {"id": f"base_{TOKENS['ETH']}"}},
                                  "quote_token": {"data": {"id": f"base_{USDC}"}}}}]})
        assert "/ohlcv/hour" in request.url.path and request.url.params["token"] == "base"
        return httpx.Response(200, json={"data": {"attributes": {"ohlcv_list": [
            [7200, 1, 1, 1, 2010.5, 9], [3600, 1, 1, 1, 2000, 9], ["bad"], [10800, 1, 1, 1, 0, 9]]}}})

    f = GeckoTerminalFeed(PriceBook(60), 20, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    f.pools = {"ETH": (pool, True)}
    assert await f.hourly_candles("ETH") == [(3600, 2000.0), (7200, 2010.5)]
