from decimal import Decimal

from .conftest import sign_in


async def test_new_member_starts_with_100_usdc(signed_in):
    j = (await signed_in.get("/api/paper")).json()
    assert j["balances"] == [{"asset": "USDC", "amount": "100", "price_usd": "1", "value_usd": "100.00"}]
    assert j["total_usd"] == "100.00" and j["prices_fresh"] is True
    assert j["prices"] == {"USDC": "1", "ETH": "2000", "cbBTC": "50000"}


async def test_swap_usdc_to_eth_charges_fee(signed_in):
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "50"})
    assert r.status_code == 200, r.text
    t = r.json()["trade"]
    # $50 minus 0.3% fee = $49.85, at $2000/ETH = 0.024925 ETH
    assert Decimal(t["amount_out"]) == Decimal("0.024925")
    assert Decimal(t["fee_usd"]) == Decimal("0.15")
    bal = {b["asset"]: Decimal(b["amount"]) for b in r.json()["portfolio"]["balances"]}
    assert bal == {"USDC": Decimal("50"), "ETH": Decimal("0.024925")}
    assert r.json()["portfolio"]["total_usd"] == "99.85"


async def test_round_trip_loses_only_fees(signed_in):
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "cbBTC", "amount": "100"})
    btc = next(b for b in (await signed_in.get("/api/paper")).json()["balances"] if b["asset"] == "cbBTC")["amount"]
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "cbBTC", "to_asset": "USDC", "amount": btc})
    usdc = Decimal(r.json()["trade"]["amount_out"])
    assert abs(usdc - Decimal("100") * Decimal("0.997") ** 2) < Decimal("1e-12")


async def test_price_moves_change_value(app, signed_in):
    await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "100"})
    app.state.prices.set("ETH", Decimal("2200"))  # +10%
    assert (await signed_in.get("/api/paper")).json()["total_usd"] == "109.67"


async def test_insufficient_balance(signed_in):
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "100.01"})
    assert r.status_code == 400 and "not enough" in r.json()["detail"]
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "ETH", "to_asset": "USDC", "amount": "1"})
    assert r.status_code == 400


async def test_rejects_bad_input(signed_in):
    for body in [
        {"from_asset": "USDC", "to_asset": "DOGE", "amount": "1"},
        {"from_asset": "USDC", "to_asset": "USDC", "amount": "1"},
    ]:
        assert (await signed_in.post("/api/paper/swap", json=body)).status_code == 400
    for amount in ["0", "-5", "abc"]:
        r = await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": amount})
        assert r.status_code == 422
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "0.001"})
    assert r.status_code == 400 and "minimum" in r.json()["detail"]


async def test_stale_prices_block_swaps(app, signed_in):
    app.state.prices.set("ETH", Decimal("2000"), at=0)  # 1970: very stale
    r = await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "10"})
    assert r.status_code == 503
    j = (await signed_in.get("/api/paper")).json()
    assert j["prices_fresh"] is True  # only USDC held so far, which never goes stale


async def test_trades_history_and_reset(signed_in):
    for amt in ["10", "20"]:
        await signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": amt})
    trades = (await signed_in.get("/api/paper/trades")).json()["trades"]
    assert [t["amount_in"] for t in trades] == ["20", "10"]  # newest first
    r = await signed_in.post("/api/paper/reset", json={})
    assert r.json()["total_usd"] == "100.00"
    assert (await signed_in.get("/api/paper/trades")).json()["trades"] == []


async def test_members_are_isolated(app, client, wallet):
    from eth_account import Account
    import httpx

    await sign_in(client, wallet)
    await client.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "40"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as other:
        await sign_in(other, Account.create())
        j = (await other.get("/api/paper")).json()
        assert j["total_usd"] == "100.00" and len(j["balances"]) == 1
        assert (await other.get("/api/paper/trades")).json()["trades"] == []


async def test_health(client):
    j = (await client.get("/api/health")).json()
    assert j["ok"] is True and j["prices_fresh"] is True


async def test_concurrent_swaps_cannot_overspend(app, signed_in):
    import asyncio

    import pytest

    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("row locking is a PostgreSQL feature; set TEST_DATABASE_URL to run")
    await signed_in.get("/api/paper")  # create the account first
    body = {"from_asset": "USDC", "to_asset": "ETH", "amount": "30"}
    results = await asyncio.gather(*[signed_in.post("/api/paper/swap", json=body) for _ in range(5)])
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 200, 200, 400, 400]
    usdc = next(b for b in (await signed_in.get("/api/paper")).json()["balances"] if b["asset"] == "USDC")
    assert Decimal(usdc["amount"]) == Decimal("10")


async def test_new_member_opening_many_tabs_at_once(app, signed_in):
    import asyncio

    import pytest

    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("concurrency test needs PostgreSQL; set TEST_DATABASE_URL to run")
    results = await asyncio.gather(*[signed_in.get("/api/paper") for _ in range(6)])
    assert [r.status_code for r in results] == [200] * 6
    assert all(r.json()["total_usd"] == "100.00" for r in results)


async def test_reset_while_a_swap_is_mid_way(app, signed_in, monkeypatch):
    """Pause a swap right after it has made sure its balance rows exist, run a reset in that gap,
    then let the swap continue. The swap must still find its rows, and the books must add up."""
    import asyncio
    import sys

    from app import paper

    original = paper.ensure_account

    async def ensure_with_pauses(db, user, s):
        caller = sys._getframe(1).f_code.co_name
        if caller == "reset":
            await asyncio.sleep(0.8)  # hold the reset here, whatever it did before this call
        await original(db, user, s)
        if caller == "swap":
            await asyncio.sleep(0.4)  # hold the swap between "rows exist" and "lock rows"

    monkeypatch.setattr(paper, "ensure_account", ensure_with_pauses)
    await signed_in.get("/api/paper")
    swap = asyncio.create_task(
        signed_in.post("/api/paper/swap", json={"from_asset": "USDC", "to_asset": "ETH", "amount": "7"}))
    await asyncio.sleep(0.1)  # the swap is now paused inside its gap
    reset = await signed_in.post("/api/paper/reset", json={})
    swap_result = await swap
    assert reset.status_code == 200
    assert swap_result.status_code == 200, swap_result.text
    trades = (await signed_in.get("/api/paper/trades")).json()["trades"]
    bal = {b["asset"]: Decimal(b["amount"]) for b in (await signed_in.get("/api/paper")).json()["balances"]}
    assert bal["USDC"] == Decimal(100) - sum(Decimal(t["amount_in"]) for t in trades)
    assert bal.get("ETH", Decimal(0)) == sum(Decimal(t["amount_out"]) for t in trades)
