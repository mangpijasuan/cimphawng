"""Retry safety for paper swaps and resets: a lost answer must never mean a double spend."""

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.models import OperationReceipt, PaperTrade


SWAP = {"from_asset": "USDC", "to_asset": "ETH", "amount": "10"}


def key():
    return {"Idempotency-Key": uuid.uuid4().hex}


async def trades(client):
    return (await client.get("/api/paper/trades")).json()["trades"]


async def test_retry_returns_the_original_fill_and_spends_once(signed_in):
    h = key()
    one = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    two = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    assert one.status_code == 200 and two.status_code == 200
    assert two.json()["replayed"] is True and "replayed" not in one.json()
    assert one.json()["trade"] == two.json()["trade"]  # the same fill: id, amounts, time
    assert len(await trades(signed_in)) == 1
    usdc = next(b for b in two.json()["portfolio"]["balances"] if b["asset"] == "USDC")
    assert usdc["amount"] == "90"  # spent once, not twice


async def test_same_id_for_a_different_request_is_refused(signed_in):
    h = key()
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers=h)).status_code == 200
    r = await signed_in.post("/api/paper/swap", json={**SWAP, "amount": "11"}, headers=h)
    assert r.status_code == 409 and "already used" in r.json()["detail"]
    r = await signed_in.post("/api/paper/reset", json={}, headers=h)  # a reset can't reuse a swap's ID either
    assert r.status_code == 409
    assert len(await trades(signed_in)) == 1


async def test_an_equal_amount_written_differently_is_the_same_request(signed_in):
    h = key()
    await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    r = await signed_in.post("/api/paper/swap", json={**SWAP, "amount": "10.000"}, headers=h)
    assert r.status_code == 200 and r.json()["replayed"] is True


async def test_missing_or_malformed_ids_are_refused(signed_in):
    for bad in ["", "short", "has spaces in it 1234567890", "x" * 81, "bad/chars/1234567890123"]:
        for path, body in [("/api/paper/swap", SWAP), ("/api/paper/reset", {})]:
            r = await signed_in.post(path, json=body, headers={"Idempotency-Key": bad})
            assert r.status_code == 400 and "Idempotency-Key" in r.json()["detail"], (path, bad)
    assert await trades(signed_in) == []


async def test_replay_works_even_when_prices_have_gone_stale(app, signed_in):
    h = key()
    first = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    app.state.prices.set("ETH", Decimal("2000"), at=0)
    again = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    assert again.status_code == 200 and again.json()["trade"] == first.json()["trade"]
    new = await signed_in.post("/api/paper/swap", json=SWAP, headers=key())  # but a new trade is still blocked
    assert new.status_code == 503


async def test_refused_swaps_are_not_remembered(signed_in):
    h = key()
    too_much = {**SWAP, "amount": "500"}
    assert (await signed_in.post("/api/paper/swap", json=too_much, headers=h)).status_code == 400
    ok = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)  # the same ID can be used for a real try
    assert ok.status_code == 200 and "replayed" not in ok.json()


async def test_simultaneous_identical_requests_make_one_fill(signed_in):
    h = key()
    rs = await asyncio.gather(*[signed_in.post("/api/paper/swap", json=SWAP, headers=h) for _ in range(4)])
    assert all(r.status_code == 200 for r in rs), [r.text for r in rs]
    assert len({r.json()["trade"]["id"] for r in rs}) == 1
    assert len(await trades(signed_in)) == 1
    assert sum("replayed" in r.json() for r in rs) == 3


async def test_a_retried_reset_cannot_erase_later_trades(signed_in):
    h = key()
    first = await signed_in.post("/api/paper/reset", json={}, headers=h)
    assert first.status_code == 200 and "replayed" not in first.json()
    await signed_in.post("/api/paper/swap", json=SWAP, headers=key())
    again = await signed_in.post("/api/paper/reset", json={}, headers=h)
    assert again.status_code == 200 and again.json()["replayed"] is True
    assert len(await trades(signed_in)) == 1  # the trade made after the first reset is still there
    assert any(b["asset"] == "ETH" for b in again.json()["balances"])


async def test_receipts_belong_to_one_member(app, signed_in):
    from eth_account import Account

    from .conftest import make_client, sign_in

    h = key()
    mine = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    async with make_client(app) as other:
        assert (await sign_in(other, Account.create())).status_code == 200
        theirs = await other.post("/api/paper/swap", json=SWAP, headers=h)  # same ID, a different member
        assert theirs.status_code == 200 and "replayed" not in theirs.json()
        assert theirs.json()["trade"]["id"] != mine.json()["trade"]["id"]


async def test_the_stored_answer_survives_a_database_roundtrip(app, signed_in):
    h = key()
    r = await signed_in.post("/api/paper/swap", json=SWAP, headers=h)
    async with app.state.sessionmaker() as db:
        n = await db.scalar(select(func.count()).select_from(OperationReceipt))
        t = await db.scalar(select(func.count()).select_from(PaperTrade))
    assert (n, t) == (1, 1)
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers=h)).json()["trade"] == r.json()["trade"]
