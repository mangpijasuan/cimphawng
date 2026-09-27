"""Sign-In with Ethereum (EIP-4361).

1. GET  /api/auth/nonce?address=0x..  -> the server writes the exact message to sign (with a single-use nonce).
2. The member signs it in their own wallet. It's free: no transaction, no gas, no money moves.
3. POST /api/auth/verify {nonce, signature} -> the server recovers the signer from the signature, checks it
   matches, and sets an HttpOnly session cookie.

The server never sees a private key or seed phrase.
"""

import hashlib
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import AuthNonce, Session, User, utcnow

router = APIRouter(prefix="/api")
COOKIE = "cimp_session"
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
NONCE_LIMIT_PER_MIN = 20
_nonce_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    """Simple in-memory limit on sign-in requests per IP, so nobody can flood the nonce table."""
    now, hits = time.monotonic(), _nonce_hits[ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= NONCE_LIMIT_PER_MIN:
        return True
    hits.append(now)
    if len(_nonce_hits) > 10_000:  # forget idle IPs
        for k in [k for k, v in _nonce_hits.items() if not v or now - v[-1] > 60]:
            del _nonce_hits[k]
    return False


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def db_dep(request: Request):
    async with request.app.state.sessionmaker() as db:
        yield db


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def build_message(s: Settings, address: str, nonce: str, issued, expires) -> str:
    return (
        f"{s.site_domain} wants you to sign in with your Ethereum account:\n"
        f"{to_checksum_address(address)}\n\n"
        "Sign in to Cimphawng. This is free and does not send a transaction.\n\n"
        f"URI: {s.site_uri}\n"
        "Version: 1\n"
        f"Chain ID: {s.chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued.isoformat(timespec='seconds')}Z\n"
        f"Expiration Time: {expires.isoformat(timespec='seconds')}Z"
    )


def user_out(u: User, s: Settings) -> dict:
    return {
        "address": u.address,
        "display_name": u.display_name,
        "role": "owner" if u.address in s.owners else "member",
    }


@router.get("/auth/nonce")
async def nonce(
    request: Request, address: str = Query(...), s: Settings = Depends(settings_dep),
    db: AsyncSession = Depends(db_dep),
):
    if _rate_limited(request.client.host if request.client else "?"):
        raise HTTPException(429, "too many sign-in attempts; wait a minute")
    if not ADDRESS_RE.match(address):
        raise HTTPException(400, "invalid address")
    now = utcnow()
    n = secrets.token_hex(16)
    expires = now + timedelta(minutes=s.nonce_minutes)
    msg = build_message(s, address, n, now, expires)
    await db.execute(delete(AuthNonce).where(AuthNonce.expires_at < now))  # tidy up old ones
    db.add(AuthNonce(nonce=n, address=address.lower(), message=msg, expires_at=expires))
    await db.commit()
    return {"nonce": n, "message": msg}


class VerifyIn(BaseModel):
    nonce: str = Field(max_length=64)
    signature: str = Field(max_length=200)


@router.post("/auth/verify")
async def verify(
    body: VerifyIn, response: Response, s: Settings = Depends(settings_dep), db: AsyncSession = Depends(db_dep)
):
    now = utcnow()
    row = await db.get(AuthNonce, body.nonce, with_for_update=True)
    if row is None or row.used or row.expires_at < now:
        raise HTTPException(401, "sign-in request expired or already used; please try again")
    row.used = True  # single use, even if the signature turns out to be wrong
    await db.commit()
    try:
        signer = Account.recover_message(encode_defunct(text=row.message), signature=body.signature)
    except Exception:
        raise HTTPException(401, "invalid signature")
    if signer.lower() != row.address:
        raise HTTPException(401, "signature does not match the address")

    user = (await db.execute(select(User).where(User.address == row.address))).scalar_one_or_none()
    if user is None:
        user = User(address=row.address)
        db.add(user)
    user.last_login_at = now
    await db.flush()
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=_hash(token), user_id=user.id, expires_at=now + timedelta(days=s.session_days)))
    await db.commit()
    response.set_cookie(
        COOKIE, token, max_age=s.session_days * 86400, httponly=True, secure=s.cookie_secure,
        samesite="lax", path="/",
    )
    return user_out(user, s)


async def current_user(request: Request, db: AsyncSession = Depends(db_dep)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "not signed in")
    sess = await db.get(Session, _hash(token))
    if sess is None or sess.expires_at < utcnow():
        raise HTTPException(401, "session expired; please sign in again")
    user = await db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(401, "not signed in")
    return user


@router.get("/me")
async def me(user: User = Depends(current_user), s: Settings = Depends(settings_dep)):
    return user_out(user, s)


@router.post("/auth/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(db_dep)):
    token = request.cookies.get(COOKIE)
    if token:
        await db.execute(delete(Session).where(Session.token_hash == _hash(token)))
        await db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
