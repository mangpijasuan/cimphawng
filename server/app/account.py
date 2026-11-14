"""Account controls: download your data, sign out everywhere, delete your paper account.

Signing out everywhere and deleting need a sign-in from the last 10 minutes, so a stolen browser session
that has been open for a while can't be used to wipe the account. Deleting removes the member's paper balances,
trades, retry receipts, bot and sessions. It can't touch anything on a blockchain (nothing here ever does).
"""

import re
from datetime import UTC, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import COOKIE, _hash, current_user, db_dep, settings_dep
from .config import Settings
from .models import AuthNonce, Balance, OperationReceipt, PaperBot, PaperTrade, Session, User, utcnow
from .paper import ASSETS, ensure_account, num, trade_out

router = APIRouter(prefix="/api/account")
RECENT = timedelta(minutes=10)
PAGE = 200
CURSOR_RE = re.compile(r"^\d{1,18}$")


def epoch_ms(dt) -> int:
    return int(dt.replace(tzinfo=UTC).timestamp() * 1000)


async def require_recent_sign_in(request: Request, user: User, db: AsyncSession) -> None:
    sess = await db.get(Session, _hash(request.cookies.get(COOKIE) or ""))
    if sess is None or sess.user_id != user.id or utcnow() - sess.created_at > RECENT:
        raise HTTPException(403, "Please sign out and sign in again before this account action.")


@router.get("/export")
async def export(
    cursor: str | None = Query(None, max_length=32), user: User = Depends(current_user),
    db: AsyncSession = Depends(db_dep), s: Settings = Depends(settings_dep),
):
    """The member's account and every trade (archived ones too), newest first, 200 per page."""
    if cursor is not None and not CURSOR_RE.match(cursor):
        raise HTTPException(400, "Invalid export cursor.")
    await ensure_account(db, user, s)
    balances = {b.asset: b.amount for b in
                (await db.execute(select(Balance).where(Balance.user_id == user.id))).scalars().all()}
    q = select(PaperTrade).where(PaperTrade.user_id == user.id)
    if cursor is not None:
        q = q.where(PaperTrade.id < int(cursor))
    rows = (await db.execute(q.order_by(PaperTrade.id.desc()).limit(PAGE + 1))).scalars().all()
    page = rows[:PAGE]
    return {
        "format_version": 1,
        "exported_at": utcnow().isoformat(timespec="milliseconds") + "Z",
        "account": {
            "address": user.address,
            "balances": {a: num(balances[a]) for a in ASSETS if a in balances},
            "created_at": epoch_ms(user.created_at), "last_seen": epoch_ms(user.last_seen_at),
        },
        "trades": [{**trade_out(t), "archived": t.archived} for t in page],
        "next_cursor": str(page[-1].id) if len(rows) > PAGE else None,
    }


@router.post("/logout-all")
async def logout_all(
    request: Request, response: Response, user: User = Depends(current_user), db: AsyncSession = Depends(db_dep),
):
    await require_recent_sign_in(request, user, db)
    await db.execute(delete(Session).where(Session.user_id == user.id))
    await db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/delete")
async def delete_account(
    request: Request, response: Response, body: dict = Body(...), user: User = Depends(current_user),
    db: AsyncSession = Depends(db_dep),
):
    await require_recent_sign_in(request, user, db)
    confirmation = body.get("confirmation")
    if not isinstance(confirmation, str) or confirmation.lower() != user.address:
        raise HTTPException(400, "Type the connected wallet address to confirm account deletion.")
    # Lock the bot, then the balances: the same order a running bot uses, and a swap only needs the balances,
    # so none of them can deadlock with this. Anything that was waiting then finds the account gone.
    await db.execute(select(PaperBot).where(PaperBot.user_id == user.id).with_for_update())
    await db.execute(select(Balance).where(Balance.user_id == user.id).order_by(Balance.asset).with_for_update())
    for model in (OperationReceipt, PaperTrade, PaperBot, Balance, Session):
        await db.execute(delete(model).where(model.user_id == user.id))
    await db.execute(delete(AuthNonce).where(AuthNonce.address == user.address))
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True, "deleted": "wallet paper account",
            "note": "This does not alter blockchain transactions or tokens. "
                    "Backups may retain historical copies for their retention period."}
