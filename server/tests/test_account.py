"""Account controls: export, sign out everywhere, delete. Mirrors the Worker's tests so both backends agree."""

from contextlib import asynccontextmanager
from datetime import timedelta

from eth_account import Account
from sqlalchemy import func, select, update

from app.models import (AuthNonce, Balance, OperationReceipt, PaperBot, PaperTrade, Session, User,
                        utcnow)

from .conftest import make_client, sign_in

SWAP = {"from_asset": "USDC", "to_asset": "ETH", "amount": "10"}


@asynccontextmanager
async def logged_in(app, wallet):
    """Another browser, signed in as `wallet`."""
    async with make_client(app) as c:
        assert (await sign_in(c, wallet)).status_code == 200
        yield c


async def count(app, model):
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(func.count()).select_from(model))


async def age_sessions(app, minutes):
    async with app.state.sessionmaker() as db:
        await db.execute(update(Session).values(created_at=utcnow() - timedelta(minutes=minutes)))
        await db.commit()


async def test_export_has_the_account_and_every_trade(signed_in, wallet):
    await signed_in.post("/api/paper/swap", json=SWAP)
    r = await signed_in.get("/api/account/export")
    j = r.json()
    assert r.status_code == 200 and j["format_version"] == 1 and j["next_cursor"] is None
    assert j["account"]["address"] == wallet.address.lower()
    assert j["account"]["balances"] == {"USDC": "90", "ETH": "0.004985", "cbBTC": "0"}
    assert len(j["trades"]) == 1 and j["trades"][0]["archived"] is False
    assert isinstance(j["account"]["created_at"], int) and isinstance(j["account"]["last_seen"], int)
    assert "cimp_session" not in r.text and "token" not in str(j["account"]).lower()


async def test_export_pages_keep_archived_trades_and_stay_private(app, signed_in):
    async with app.state.sessionmaker() as db:
        await signed_in.get("/api/paper")  # creates the account rows
        uid = (await db.scalar(select(User.id)))
        db.add_all([PaperTrade(user_id=uid, from_asset="USDC", to_asset="ETH", amount_in=1, amount_out=1,
                               price_in_usd=1, price_out_usd=1, fee_usd=0, archived=True) for _ in range(205)])
        await db.commit()
    one = (await signed_in.get("/api/account/export")).json()
    assert len(one["trades"]) == 200 and one["next_cursor"]
    assert all(t["archived"] for t in one["trades"])
    two = (await signed_in.get("/api/account/export", params={"cursor": one["next_cursor"]})).json()
    assert len(two["trades"]) == 5 and two["next_cursor"] is None
    assert len({t["id"] for t in one["trades"] + two["trades"]}) == 205  # no repeats, none missing
    async with logged_in(app, Account.create()) as other:
        assert (await other.get("/api/account/export")).json()["trades"] == []  # another member sees none of it


async def test_export_rejects_a_bad_cursor_and_needs_sign_in(client, signed_in):
    for bad in ["abc", "-1", "1; DROP TABLE users", "9" * 25]:
        assert (await signed_in.get("/api/account/export", params={"cursor": bad})).status_code in (400, 422)
    await signed_in.post("/api/auth/logout", json={})
    assert (await client.get("/api/account/export")).status_code == 401


async def test_sensitive_actions_need_a_recent_sign_in(app, signed_in, wallet):
    await age_sessions(app, 11)
    for path, body in [("/api/account/logout-all", {}), ("/api/account/delete", {"confirmation": wallet.address})]:
        r = await signed_in.post(path, json=body)
        assert r.status_code == 403 and "sign in again" in r.json()["detail"]
    assert (await signed_in.get("/api/me")).status_code == 200  # nothing was done
    assert await count(app, User) == 1
    async with logged_in(app, wallet) as fresh:  # signing in again makes the action allowed
        assert (await fresh.post("/api/account/logout-all", json={})).status_code == 200


async def test_logout_all_ends_every_session_and_clears_the_cookie(app, signed_in, wallet):
    async with logged_in(app, wallet) as other, logged_in(app, Account.create()) as third:  # third: someone else
        r = await signed_in.post("/api/account/logout-all", json={})
        assert r.status_code == 200 and "cimp_session=" in r.headers["set-cookie"]
        assert (await signed_in.get("/api/me")).status_code == 401
        assert (await other.get("/api/me")).status_code == 401
        assert (await third.get("/api/me")).status_code == 200


async def test_delete_needs_the_address_typed_back(app, signed_in, wallet):
    for body in [{}, {"confirmation": 42}, {"confirmation": ""}, {"confirmation": "0x" + "0" * 40}]:
        assert (await signed_in.post("/api/account/delete", json=body)).status_code == 400, body
    assert await count(app, User) == 1


async def test_delete_removes_everything_and_every_session(app, signed_in, wallet):
    async with logged_in(app, wallet) as other, logged_in(app, Account.create()) as bystander:
        await signed_in.post("/api/paper/swap", json=SWAP)
        await signed_in.post("/api/bot", json={"strategy": "ma", "asset": "ETH", "size_pct": 50, "enabled": False})
        r = await signed_in.post("/api/account/delete", json={"confirmation": wallet.address.upper().replace("0X", "0x")})
        assert r.status_code == 200 and r.json()["deleted"] == "wallet paper account"
        assert "blockchain" in r.json()["note"]
        assert (await signed_in.get("/api/me")).status_code == 401
        assert (await other.get("/api/me")).status_code == 401  # every session of the deleted member
        assert (await bystander.get("/api/me")).status_code == 200  # and nobody else's
        async with app.state.sessionmaker() as db:
            for model in (OperationReceipt, PaperTrade, PaperBot):
                assert await db.scalar(select(func.count()).select_from(model).where(model.user_id == 1)) == 0
            assert await db.scalar(select(func.count()).select_from(Balance).where(Balance.user_id == 1)) == 0
            assert await db.scalar(select(func.count()).select_from(AuthNonce).where(
                AuthNonce.address == wallet.address.lower())) == 0
        # the same wallet can come back and gets a fresh $100 account
        async with logged_in(app, wallet) as again:
            assert (await again.get("/api/paper")).json()["total_usd"] == "100.00"


async def test_deleted_member_vanishes_from_community_numbers(app, signed_in, wallet):
    app.state.settings.stats_cache_s = 0  # don't let the monitor's 5-second cache hide the change
    await signed_in.post("/api/paper/swap", json=SWAP)
    assert (await signed_in.get("/api/stats")).json()["community"]["members"] == 1
    await signed_in.post("/api/account/delete", json={"confirmation": wallet.address})
    async with make_client(app) as anon:
        c = (await anon.get("/api/stats")).json()["community"]
    assert c["members"] == 0 and c["paper_trades_total"] == 0


async def test_a_running_bot_survives_its_owner_deleting_the_account(app, signed_in, wallet):
    """The runner listed the bot, then the member deleted themselves: it must skip them and carry on."""
    from .test_bots import NOW, UP, feed, start

    feed(app, UP)
    await start(signed_in)
    runner = app.state.bots
    original = runner.run_bot
    deleted = {}

    async def delete_then_run(user_id, asset, cs, now):  # the deletion lands between listing and running
        if not deleted:
            deleted["r"] = await signed_in.post("/api/account/delete", json={"confirmation": wallet.address})
        await original(user_id, asset, cs, now)

    runner.run_bot = delete_then_run
    await runner.tick(NOW)
    assert deleted["r"].status_code == 200
    assert await count(app, PaperTrade) == 0 and await count(app, Balance) == 0 and runner.last_error is None
