"""Paper trading: pretend USDC, swapped at real Base DEX prices. Nothing is sent to the blockchain."""

from decimal import ROUND_DOWN, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_user, db_dep, settings_dep
from .config import Settings
from .models import Balance, PaperTrade, User
from .prices import ASSETS, PriceBook, StalePrice

router = APIRouter(prefix="/api/paper")
Q = Decimal("1e-18")  # store amounts to 18 decimal places, like ERC-20 tokens


def num(d: Decimal) -> str:
    """Plain decimal text without padding or exponents, e.g. 100.000000000000000000 -> "100"."""
    return format(d.normalize(), "f")


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
    await db.execute(insert(Balance).values(rows).on_conflict_do_nothing())
    await db.commit()


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


class SwapIn(BaseModel):
    from_asset: str = Field(max_length=16)
    to_asset: str = Field(max_length=16)
    amount: Decimal = Field(gt=0, max_digits=40, decimal_places=18)


class SwapRefused(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


async def execute_swap(
    db: AsyncSession, user_id: int, from_asset: str, to_asset: str, amount: Decimal | None,
    book: PriceBook, s: Settings, *, fraction: Decimal = Decimal(1), source: str = "manual",
) -> PaperTrade:
    """Book one swap in the current transaction; the caller commits. Raises SwapRefused.

    amount=None swaps `fraction` of whatever the from_asset balance is once it is locked (used by bots).
    The account rows must already exist (ensure_account).
    """
    # Lock both balance rows (in a fixed order, so two swaps can't deadlock) until the caller commits.
    q = (select(Balance).where(Balance.user_id == user_id, Balance.asset.in_([from_asset, to_asset]))
         .order_by(Balance.asset).with_for_update())
    rows = {b.asset: b for b in (await db.execute(q)).scalars().all()}
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

    value_usd = amount * px_in
    if value_usd < s.min_trade_usd:
        raise SwapRefused(400, f"minimum trade is ${s.min_trade_usd}")
    fee_usd = value_usd * s.swap_fee
    out = ((value_usd - fee_usd) / px_out).quantize(Q, rounding=ROUND_DOWN)

    src.amount = src.amount - amount
    dst.amount = dst.amount + out
    trade = PaperTrade(user_id=user_id, from_asset=from_asset, to_asset=to_asset, amount_in=amount,
                       amount_out=out, price_in_usd=px_in, price_out_usd=px_out, fee_usd=fee_usd.quantize(Q),
                       source=source)
    db.add(trade)
    return trade


@router.post("/swap")
async def swap(
    body: SwapIn, user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
    book: PriceBook = Depends(book_dep), s: Settings = Depends(settings_dep),
):
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
        trade = await execute_swap(db, user.id, body.from_asset, body.to_asset, body.amount, book, s)
    except SwapRefused as e:
        raise HTTPException(e.status, e.detail)
    await db.commit()
    return {"trade": trade_out(trade), "portfolio": await portfolio(db, user, book, s)}


def trade_out(t: PaperTrade) -> dict:
    return {
        "id": t.id, "from_asset": t.from_asset, "to_asset": t.to_asset,
        "amount_in": num(t.amount_in), "amount_out": num(t.amount_out),
        "price_in_usd": num(t.price_in_usd), "price_out_usd": num(t.price_out_usd),
        "fee_usd": str(t.fee_usd.quantize(Decimal("0.0001"))), "created_at": t.created_at.isoformat() + "Z",
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
):
    # One transaction under the same row locks swaps use. Rows are reset in place, never deleted,
    # so a swap running at the same moment always finds them.
    await ensure_account(db, user, s)
    q = select(Balance).where(Balance.user_id == user.id).order_by(Balance.asset).with_for_update()
    for b in (await db.execute(q)).scalars().all():
        b.amount = s.paper_start_usdc if b.asset == "USDC" else Decimal(0)
    await db.execute(update(PaperTrade).where(PaperTrade.user_id == user.id).values(archived=True))
    await db.commit()
    return await portfolio(db, user, book, s)
