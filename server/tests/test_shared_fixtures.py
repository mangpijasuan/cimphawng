"""Both paper-trading backends must make exactly the same fills. The cases live in shared/paper-fixtures.json
and are also run against the Cloudflare Worker (hosted/tests/shared-fixtures.test.mjs)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import update

from app.models import Balance

FIXTURES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "paper-fixtures.json").read_text())
CASES = FIXTURES["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
async def test_swap_matches_the_shared_fixture(app, signed_in, case):
    for asset, price in {**FIXTURES["prices"], **case.get("prices", {})}.items():
        app.state.prices.set(asset, Decimal(price))
    await signed_in.get("/api/paper")  # creates the account rows
    async with app.state.sessionmaker() as db:
        for asset, amount in (case.get("balances") or FIXTURES["start"]).items():
            await db.execute(update(Balance).where(Balance.asset == asset).values(amount=Decimal(amount)))
        await db.commit()

    expect = case["expect"]
    r = await signed_in.post("/api/paper/swap", json={"from_asset": case["from"], "to_asset": case["to"],
                                                      "amount": case["amount"]})
    allowed = expect["status"] if isinstance(expect["status"], list) else [expect["status"]]
    assert r.status_code in allowed, (r.status_code, r.text)
    if r.status_code == 200:
        t = r.json()["trade"]
        for field in ("amount_out", "fee_usd", "price_in_usd", "price_out_usd"):
            assert t[field] == expect[field], field

    portfolio = (await signed_in.get("/api/paper")).json()
    assert {b["asset"]: b["amount"] for b in portfolio["balances"]} == expect["balances"]
    assert len((await signed_in.get("/api/paper/trades")).json()["trades"]) == expect["trades"]
