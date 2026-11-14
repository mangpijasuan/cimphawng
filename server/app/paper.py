"""Paper trading: pretend USDC, swapped at real Base DEX prices. Nothing is sent to the blockchain."""

import hashlib
import json
import re
from decimal import ROUND_DOWN, Decimal, localcontext

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_user, db_dep, settings_dep
from .config import Settings
from .models import Balance, OperationReceipt, PaperTrade, User
from .prices import ASSETS, PriceBook, StalePrice

router = APIRouter(prefix="/api/paper")
Q = Decimal("1e-18")  # store amounts to 18 decimal places, like ERC-20 tokens


def num(d: Decimal) -> str:
    """Plain decimal text without padding or exponents, e.g. 100.000000000000000000 -> "100".

    (Decimal.normalize() would round to the context's 28 digits and silently lose the end of a large amount.)
    """
    text = format(d, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def book_dep(request: Request) -> PriceBook:
    return request.app.state.prices


async def ensure_account(db: AsyncSession, user: User | int, s: Settings) -> None:
    """Create a row for every asset (USDC at the starting amount, the rest at zero).

    Every row existing up front means swaps can always lock both sides. ON CONFLICT DO NOTHING makes
    this safe when two requests for a new member arrive at the same time.
    """
    user_id = user if isinstance(user, int) else user.id
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    rows = [{"user_id": user_id, "asset": a, "amount": s.paper_start_usdc if a == "USDC" else Decimal(0)}
            for a in ASSETS]
    try:
        await db.execute(insert(Balance).values(rows).on_conflict_do_nothing())
        await db.commit()
    except IntegrityError:  # the member deleted their account while this request was starting
        await db.rollback()
        raise HTTPException(401, "Please sign in again.")


async def portfolio(db: AsyncSession, user: User, book: PriceBook, s: Settings) -> dict:
    rows = (await db.execute(select(Balance).where(Balance.user_id == user.id))).scalars().all()
    items, total, priced = [], Decimal(0), True
    for b in sorted(rows, key=lambda r: ASSETS.index(r.asset) if r.asset in ASSETS else 99):
        if b.amount == 0 and b.asset != "USDC":
            continue
        try:
            px = book.get(b.asset)
            value = b.amount * px
            total += value
        except StalePrice:
            px, value, priced = None, None, False
        items.append({"asset": b.asset, "amount": num(b.amount), "price_usd": num(px) if px else None,
                      "value_usd": str(value.quantize(Decimal("0.01"))) if value is not None else None})
    prices = {}
    for a in ASSETS:  # every tradable asset, so the app can preview any swap
        try:
            prices[a] = num(book.get(a))
        except StalePrice:
            prices[a] = None
    return {
        "balances": items,
        "prices": prices,
        "total_usd": str(total.quantize(Decimal("0.01"))) if priced else None,
        "start_usd": num(s.paper_start_usdc),
        "prices_fresh": priced,
    }


@router.get("")
async def get_portfolio(
    user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
    book: PriceBook = Depends(book_dep), s: Settings = Depends(settings_dep),
):
    await ensure_account(db, user, s)
    return await portfolio(db, user, book, s)


KEY_RE = re.compile(r"^[-a-zA-Z0-9_]{16,80}$")


def idempotency_key(request: Request) -> str:
    """Every swap and reset carries a request ID, so a retry after a lost answer can't repeat it."""
    key = request.headers.get("Idempotency-Key", "")
    if not KEY_RE.match(key):
        raise HTTPException(400, "A unique Idempotency-Key is required for each paper operation.")
    return key


def payload_hash(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


class Replay(Exception):
    """This request ID already has a stored result."""

    def __init__(self, receipt: OperationReceipt):
        super().__init__("replay")
        self.receipt = receipt


async def find_receipt(db: AsyncSession, user_id: int, key: str) -> OperationReceipt | None:
    q = (select(OperationReceipt).where(OperationReceipt.user_id == user_id, OperationReceipt.key == key)
         .execution_options(populate_existing=True))
    return (await db.execute(q)).scalar_one_or_none()


async def replay_response(
    db: AsyncSession, user: User, book: PriceBook, s: Settings, receipt: OperationReceipt, kind: str, phash: str
) -> dict:
    """The original answer for a repeated request ID, with the portfolio as it is now. Nothing is run again."""
    if receipt.kind != kind or receipt.payload_hash != phash:
        raise HTTPException(409, "That request ID was already used for a different operation.")
    pf = await portfolio(db, user, book, s)
    if kind == "swap":
        return {"trade": json.loads(receipt.result), "portfolio": pf, "replayed": True}
    return {**pf, "replayed": True}


async def answer_from_receipt(
    db: AsyncSession, user: User, user_id: int, key: str, book: PriceBook, s: Settings, kind: str, phash: str
) -> dict | None:
    """Drop this transaction (and its row locks), then answer a repeated request ID from its stored receipt.

    A rollback expires every loaded object, so the member is reloaded before it is used again.
    Returns None if there is no receipt (the caller then re-raises whatever went wrong).
    """
    await db.rollback()
    await db.refresh(user)
    receipt = await find_receipt(db, user_id, key)
    return None if receipt is None else await replay_response(db, user, book, s, receipt, kind, phash)


AMOUNT_RE = re.compile(r"[0-9]{1,22}(\.[0-9]{1,18})?")  # plain digits only, same rule as the Cloudflare Worker


class SwapIn(BaseModel):
    from_asset: str = Field(max_length=16)
    to_asset: str = Field(max_length=16)
    amount: Decimal = Field(gt=0, max_digits=40, decimal_places=18)

    @field_validator("amount", mode="before")
    @classmethod
    def plain_decimal_string(cls, v):
        """Only a string of digits with an optional fractional part: no 1e2, +5, .5, 5., spaces or JSON numbers."""
        if not isinstance(v, str) or not AMOUNT_RE.fullmatch(v):
            raise ValueError("Use a positive decimal amount with at most 18 decimal places.")
        return v


class SwapRefused(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


async def execute_swap(
    db: AsyncSession, user_id: int, from_asset: str, to_asset: str, amount: Decimal | None,
    book: PriceBook, s: Settings, *, fraction: Decimal = Decimal(1), source: str = "manual",
    receipt: tuple[str, str] | None = None,
) -> PaperTrade:
    """Book one swap in the current transaction; the caller commits. Raises SwapRefused.

    amount=None swaps `fraction` of whatever the from_asset balance is once it is locked (used by bots).
    receipt=(request ID, payload hash) stores the result under that ID; if one already exists, raises Replay.
    The account rows must already exist (ensure_account).
    """
    # Lock both balance rows (in a fixed order, so two swaps can't deadlock) until the caller commits.
    q = (select(Balance).where(Balance.user_id == user_id, Balance.asset.in_([from_asset, to_asset]))
         .order_by(Balance.asset).with_for_update())
    rows = {b.asset: b for b in (await db.execute(q)).scalars().all()}
    if from_asset not in rows or to_asset not in rows:  # the account was deleted while this waited for the lock
        raise SwapRefused(401, "Please sign in again.")
    if receipt:  # checked while holding the lock: an identical request that ran first has already committed
        prior = await find_receipt(db, user_id, receipt[0])
        if prior:
            raise Replay(prior)
    src, dst = rows[from_asset], rows[to_asset]
    if amount is None:
        amount = (src.amount * fraction).quantize(Q, rounding=ROUND_DOWN)
    if amount <= 0 or src.amount < amount:
        raise SwapRefused(400, f"not enough {from_asset}")
    try:
        # read prices only once the locks are held, so a long wait can't let a stale price through
        px_in, px_out = book.get(from_asset), book.get(to_asset)
    except StalePrice:
        # stale-data guard: never trade on old prices, even pretend ones
        raise SwapRefused(503, "live prices are unavailable right now; try again shortly")

    # Round down to 18 decimals at each step (dollar value, fee, amount received), exactly as the Cloudflare
    # Worker does, so both backends make the same fill to the last digit. The wide context stops Python's
    # default 28 digits from rounding a large product on its own.
    with localcontext() as ctx:
        ctx.prec = 80
        value_usd = (amount * px_in).quantize(Q, rounding=ROUND_DOWN)
        if value_usd < s.min_trade_usd:
            raise SwapRefused(400, f"minimum trade is ${s.min_trade_usd}")
        fee_usd = (value_usd * s.swap_fee).quantize(Q, rounding=ROUND_DOWN)
        out = ((value_usd - fee_usd) / px_out).quantize(Q, rounding=ROUND_DOWN)

    src.amount = src.amount - amount
    dst.amount = dst.amount + out
    trade = PaperTrade(user_id=user_id, from_asset=from_asset, to_asset=to_asset, amount_in=amount,
                       amount_out=out, price_in_usd=px_in, price_out_usd=px_out, fee_usd=fee_usd,
                       source=source)
    db.add(trade)
    if receipt:
        await db.flush()  # assigns the trade's id and time, which the stored answer includes
        db.add(OperationReceipt(user_id=user_id, key=receipt[0], kind="swap", payload_hash=receipt[1],
                                result=json.dumps(trade_out(trade))))
    return trade


@router.post("/swap")
async def swap(
    body: SwapIn, user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
    book: PriceBook = Depends(book_dep), s: Settings = Depends(settings_dep),
    key: str = Depends(idempotency_key),
):
    uid = user.id  # read now: a rollback below expires the member object
    phash = payload_hash("swap", body.from_asset, body.to_asset, num(body.amount))
    # A repeat of something already done gets its original answer, even if prices are stale by now.
    prior = await find_receipt(db, user.id, key)
    if prior:
        return await replay_response(db, user, book, s, prior, "swap", phash)
    if body.from_asset not in ASSETS or body.to_asset not in ASSETS:
        raise HTTPException(400, f"assets must be one of {', '.join(ASSETS)}")
    if body.from_asset == body.to_asset:
        raise HTTPException(400, "pick two different assets")
    try:  # fail fast before queueing for the lock
        book.get(body.from_asset), book.get(body.to_asset)
    except StalePrice:
        raise HTTPException(503, "live prices are unavailable right now; try again shortly")

    await ensure_account(db, user, s)
    try:
        trade = await execute_swap(db, user.id, body.from_asset, body.to_asset, body.amount, book, s,
                                   receipt=(key, phash))
        result = trade_out(trade)
        await db.commit()
    except Replay:
        answer = await answer_from_receipt(db, user, uid, key, book, s, "swap", phash)
        if answer is None:
            raise HTTPException(409, "That request was being processed; please retry it.")
        return answer
    except SwapRefused as e:
        raise HTTPException(e.status, e.detail)
    except IntegrityError:
        # two identical requests raced (SQLite has no row locks); the other one committed first
        answer = await answer_from_receipt(db, user, uid, key, book, s, "swap", phash)
        if answer is None:
            raise
        return answer
    return {"trade": result, "portfolio": await portfolio(db, user, book, s)}


def trade_out(t: PaperTrade) -> dict:
    return {
        "id": t.id, "from_asset": t.from_asset, "to_asset": t.to_asset,
        "amount_in": num(t.amount_in), "amount_out": num(t.amount_out),
        "price_in_usd": num(t.price_in_usd), "price_out_usd": num(t.price_out_usd),
        "fee_usd": num(t.fee_usd), "created_at": t.created_at.isoformat() + "Z",
        "source": t.source,
    }


@router.get("/trades")
async def trades(
    limit: int = Query(50, ge=1, le=200), user: User = Depends(current_user), db: AsyncSession = Depends(db_dep)
):
    q = (select(PaperTrade).where(PaperTrade.user_id == user.id, PaperTrade.archived.is_(False))
         .order_by(PaperTrade.id.desc()).limit(limit))
    return {"trades": [trade_out(t) for t in (await db.execute(q)).scalars().all()]}


@router.post("/reset")
async def reset(
    user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
    book: PriceBook = Depends(book_dep), s: Settings = Depends(settings_dep),
    key: str = Depends(idempotency_key),
):
    uid = user.id  # read now: a rollback below expires the member object
    phash = payload_hash("reset")
    prior = await find_receipt(db, user.id, key)
    if prior:
        return await replay_response(db, user, book, s, prior, "reset", phash)
    # One transaction under the same row locks swaps use. Rows are reset in place, never deleted,
    # so a swap running at the same moment always finds them.
    await ensure_account(db, user, s)
    q = select(Balance).where(Balance.user_id == user.id).order_by(Balance.asset).with_for_update()
    rows = (await db.execute(q)).scalars().all()
    if not rows:  # the account was deleted while this waited for the lock
        raise HTTPException(401, "Please sign in again.")
    if await find_receipt(db, uid, key):  # under the lock, so an identical request that ran first is seen
        return await answer_from_receipt(db, user, uid, key, book, s, "reset", phash)
    for b in rows:
        b.amount = s.paper_start_usdc if b.asset == "USDC" else Decimal(0)
    await db.execute(update(PaperTrade).where(PaperTrade.user_id == user.id).values(archived=True))
    db.add(OperationReceipt(user_id=user.id, key=key, kind="reset", payload_hash=phash, result="{}"))
    try:
        await db.commit()
    except IntegrityError:  # an identical request raced us (SQLite has no row locks) and committed first
        answer = await answer_from_receipt(db, user, uid, key, book, s, "reset", phash)
        if answer is None:
            raise
        return answer
    return await portfolio(db, user, book, s)
