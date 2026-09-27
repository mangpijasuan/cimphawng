import os
from decimal import Decimal

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from app.config import Settings
from app.main import create_app
from app.models import Base

# Uses SQLite by default. Set TEST_DATABASE_URL (e.g. postgresql+asyncpg://...) to run against PostgreSQL.
TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
async def app(tmp_path):
    s = Settings(
        database_url=TEST_DB or f"sqlite+aiosqlite:///{tmp_path}/test.db",
        price_feed=False, cookie_secure=False, owner_addresses="",
        site_domain="cimphawng.test", site_uri="https://cimphawng.test",
    )
    from app import auth

    auth._nonce_hits.clear()
    a = create_app(s)
    async with a.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await a.state.init_db()
    a.state.prices.set("ETH", Decimal("2000"))
    a.state.prices.set("cbBTC", Decimal("50000"))
    yield a
    await a.state.engine.dispose()


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def wallet():
    return Account.create()


async def sign_in(client, acct) -> httpx.Response:
    r = await client.get("/api/auth/nonce", params={"address": acct.address})
    assert r.status_code == 200, r.text
    j = r.json()
    sig = acct.sign_message(encode_defunct(text=j["message"])).signature.hex()
    return await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": "0x" + sig.removeprefix("0x")})


@pytest.fixture
async def signed_in(client, wallet):
    r = await sign_in(client, wallet)
    assert r.status_code == 200, r.text
    return client
