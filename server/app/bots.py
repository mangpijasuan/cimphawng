"""Paper bots: each member can run one strategy on one coin, trading their own paper wallet.

The rules are the web app's backtest rules (index.html, "indicators"), on closed 1-hour candles:
- MA cross: be in the coin while MA20 is above MA50, out (in USDC) while it is below.
- RSI 30/70: buy when RSI 14 drops below 30, sell when it rises above 70, otherwise hold.
A bot acts at most once per closed candle, buys only when it holds none of its coin and sells all of it.
Trades go through the same swap code, prices and fees as a member's own swaps. Nothing touches a chain.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_user, db_dep, settings_dep
from .config import Settings
from .models import Balance, PaperBot, PaperTrade, User, utcnow
from .paper import SwapRefused, ensure_account, execute_swap, num, trade_out
from .prices import TOKENS, PriceBook, StalePrice

log = logging.getLogger("cimphawng.bots")
router = APIRouter(prefix="/api/bot")

HOUR = 3600
MIN_CANDLES = 60  # the web app's analysis needs 60 too
STRATEGIES = {"ma": "MA cross", "rsi": "RSI 30/70"}
BOT_ASSETS = tuple(TOKENS)  # ETH, cbBTC (always against USDC)
Candles = Callable[[str], Awaitable[list[tuple[int, float]]]]


# >>> indicators (the same maths as index.html)
def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    total = 0.0
    for i, x in enumerate(xs):
        total += x
        if i >= n:
            total -= xs[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def rsi(xs: list[float], n: int = 14) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        g, l = (g + d, l) if d > 0 else (g, l - d)
    g, l = g / n, l / n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def want_long(strategy: str, closes: list[float]) -> bool | None:
    """True = be in the coin, False = be out, None = no change; decided on the last close."""
    if strategy == "ma":
        m20, m50 = sma(closes, 20)[-1], sma(closes, 50)[-1]
        return None if m20 is None or m50 is None else m20 > m50
    r = rsi(closes, 14)[-1]
    return None if r is None else True if r < 30 else False if r > 70 else None
# <<< indicators


def closed_only(candles: list[tuple[int, float]], now: float) -> list[tuple[int, float]]:
    return [c for c in candles if c[0] + HOUR <= now]


class BotRunner:
    """Background task: on each newly closed hour, every running bot looks at its signal once."""

    def __init__(self, sessionmaker, book: PriceBook, s: Settings, candles: Candles | None):
        self.sessionmaker, self.book, self.s, self.candles = sessionmaker, book, s, candles
        self._cache: dict[str, tuple[float, list[tuple[int, float]]]] = {}  # asset -> (fetched at, closed candles)
        self.ticks = 0
        self.trades = 0
        self.last_error: dict | None = None

    async def closed_candles(self, asset: str, now: float) -> list[tuple[int, float]]:
        expected = (int(now) // HOUR - 1) * HOUR  # open time of the newest candle that has closed
        fetched_at, cs = self._cache.get(asset, (0.0, []))
        # fetch again once a new candle should exist; if the API hasn't got it yet, retry every 5 minutes
        if not cs or (cs[-1][0] < expected and now - fetched_at >= 300):
            cs = closed_only(await self.candles(asset), now)
            self._cache[asset] = (now, cs)
        return cs

    def signal(self, asset: str, strategy: str) -> dict | None:
        """The current signal from cached candles, for the app to show. None until candles have loaded."""
        cs = self._cache.get(asset, (0.0, []))[1]
        if len(cs) < MIN_CANDLES:
            return None
        closes = [c for _, c in cs]
        w = want_long(strategy, closes)
        return {"candle_at": cs[-1][0], "close": closes[-1], "want": {True: "in", False: "out", None: "hold"}[w],
                "ma20": sma(closes, 20)[-1], "ma50": sma(closes, 50)[-1], "rsi": rsi(closes, 14)[-1]}

    async def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.ticks += 1
        async with self.sessionmaker() as db:
            bots = (await db.execute(select(PaperBot.user_id, PaperBot.asset).where(PaperBot.enabled.is_(True)))).all()
        by_asset: dict[str, list[int]] = {}
        for user_id, asset in bots:
            by_asset.setdefault(asset, []).append(user_id)
        for asset, users in by_asset.items():
            try:
                cs = await self.closed_candles(asset, now)
            except Exception as e:  # a candle outage pauses bots; it never trades on guesses
                self.last_error = {"at": int(now), "error": f"{asset} candles: {type(e).__name__}: {e}"[:200]}
                log.warning("bot candles for %s failed: %s", asset, e)
                continue
            for user_id in users:
                await self.run_bot(user_id, asset, cs, now)

    async def run_bot(self, user_id: int, asset: str, cs: list[tuple[int, float]], now: float) -> None:
        async with self.sessionmaker() as db:
            await ensure_account(db, user_id, self.s)  # commits; the lock below starts a new transaction
            bot = (await db.execute(select(PaperBot).where(PaperBot.user_id == user_id).with_for_update())).scalar()
            # re-checked under the lock: the member may have stopped or changed it, or another runner got here first
            if bot is None or not bot.enabled or bot.asset != asset:
                return
            note = None
            if len(cs) < MIN_CANDLES:
                note = "waiting for enough price history"
            elif cs[-1][0] < now - 3 * HOUR:
                note = "price history is behind; waiting"
            elif cs[-1][0] <= bot.last_candle_at:
                return  # this candle was already used
            if note:
                bot.last_note, bot.last_run_at = note, utcnow()
                await db.commit()
                return
            w = want_long(bot.strategy, [c for _, c in cs])
            signal = {True: "in", False: "out", None: "hold"}[w]
            try:
                px = self.book.get(asset)
            except StalePrice:
                # no live price: try again on the next tick without using up the candle
                bot.last_note, bot.last_run_at = "waiting for live prices", utcnow()
                await db.commit()
                return
            bal = {b.asset: b.amount for b in (await db.execute(
                select(Balance).where(Balance.user_id == user_id, Balance.asset.in_(["USDC", asset])))).scalars()}
            holding = bal.get(asset, Decimal(0)) * px >= self.s.min_trade_usd
            note = "holding" if signal == "hold" else f"signal {signal}; nothing to do"
            try:
                if signal == "in" and not holding:
                    t = await execute_swap(db, user_id, "USDC", asset, None, self.book, self.s,
                                           fraction=Decimal(bot.size_pct) / 100, source="bot")
                    note = f"bought {num(t.amount_out)} {asset} for {num(t.amount_in)} USDC"
                elif signal == "out" and holding:
                    t = await execute_swap(db, user_id, asset, "USDC", None, self.book, self.s, source="bot")
                    note = f"sold {num(t.amount_in)} {asset} for {num(t.amount_out)} USDC"
                else:
                    t = None
            except SwapRefused as e:
                await db.rollback()  # nothing from a refused swap is kept
                bot = (await db.execute(
                    select(PaperBot).where(PaperBot.user_id == user_id).with_for_update())).scalar()
                if bot is None or not bot.enabled:
                    return
                t, note = None, f"could not trade: {e.detail}"
                if e.status == 503:  # prices went stale mid-way: retry this candle
                    bot.last_note, bot.last_run_at = "waiting for live prices", utcnow()
                    await db.commit()
                    return
            bot.last_candle_at, bot.last_signal, bot.last_run_at, bot.last_note = cs[-1][0], signal, utcnow(), note
            await db.commit()
            if t is not None:
                self.trades += 1

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # keep running; the System monitor shows the error
                self.last_error = {"at": int(time.time()), "error": f"{type(e).__name__}: {e}"[:200]}
                log.exception("bot tick failed")
            await asyncio.sleep(self.s.bot_check_s)


def runner_dep(request: Request) -> BotRunner:
    return request.app.state.bots


def bot_out(b: PaperBot | None) -> dict | None:
    if b is None:
        return None
    return {"strategy": b.strategy, "asset": b.asset, "size_pct": b.size_pct, "enabled": b.enabled,
            "last_candle_at": b.last_candle_at or None, "last_signal": b.last_signal,
            "last_run_at": b.last_run_at.isoformat() + "Z" if b.last_run_at else None, "last_note": b.last_note}


async def bot_view(db: AsyncSession, user: User, runner: BotRunner) -> dict:
    b = await db.get(PaperBot, user.id, populate_existing=True)
    q = (select(PaperTrade).where(PaperTrade.user_id == user.id, PaperTrade.source == "bot",
                                  PaperTrade.archived.is_(False)).order_by(PaperTrade.id.desc()).limit(10))
    return {
        "bot": bot_out(b),
        "signal": runner.signal(b.asset, b.strategy) if b else None,
        "strategies": STRATEGIES, "assets": list(BOT_ASSETS),
        "trades": [trade_out(t) for t in (await db.execute(q)).scalars().all()],
    }


@router.get("")
async def get_bot(user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
                  runner: BotRunner = Depends(runner_dep)):
    return await bot_view(db, user, runner)


class BotIn(BaseModel):
    strategy: str = Field(max_length=16)
    asset: str = Field(max_length=16)
    size_pct: int = Field(100, ge=10, le=100)
    enabled: bool


@router.post("")
async def set_bot(body: BotIn, user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
                  runner: BotRunner = Depends(runner_dep), s: Settings = Depends(settings_dep)):
    if body.strategy not in STRATEGIES:
        raise HTTPException(400, f"strategy must be one of {', '.join(STRATEGIES)}")
    if body.asset not in BOT_ASSETS:
        raise HTTPException(400, f"asset must be one of {', '.join(BOT_ASSETS)}")
    await ensure_account(db, user, s)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    await db.execute(insert(PaperBot).values(user_id=user.id, strategy=body.strategy, asset=body.asset,
                                             size_pct=body.size_pct, enabled=False).on_conflict_do_nothing())
    b = (await db.execute(select(PaperBot).where(PaperBot.user_id == user.id).with_for_update())).scalar_one()
    if (b.strategy, b.asset) != (body.strategy, body.asset) or (body.enabled and not b.enabled):
        # a new rule, or a fresh start: act on the latest closed candle rather than wait for the next one
        b.last_candle_at, b.last_signal = 0, None
    b.strategy, b.asset, b.size_pct, b.updated_at = body.strategy, body.asset, body.size_pct, utcnow()
    if body.enabled != b.enabled:
        b.enabled, b.last_note = body.enabled, "started" if body.enabled else "stopped"
    await db.commit()
    return await bot_view(db, user, runner)
