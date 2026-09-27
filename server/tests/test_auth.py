from datetime import timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import update

from app.models import AuthNonce, utcnow

from .conftest import sign_in


async def test_sign_in_sets_session_and_me(client, wallet):
    r = await sign_in(client, wallet)
    assert r.status_code == 200
    assert r.json() == {"address": wallet.address.lower(), "display_name": None, "role": "member"}
    cookie = r.headers["set-cookie"].lower()
    assert "cimp_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    me = await client.get("/api/me")
    assert me.status_code == 200 and me.json()["address"] == wallet.address.lower()


async def test_message_is_eip4361_with_domain_chain_and_nonce(client, wallet):
    j = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    lines = j["message"].split("\n")
    assert lines[0] == "cimphawng.test wants you to sign in with your Ethereum account:"
    assert lines[1] == wallet.address  # EIP-55 checksummed
    assert "Chain ID: 8453" in lines and f"Nonce: {j['nonce']}" in lines
    assert "does not send a transaction" in j["message"]


async def test_not_signed_in_is_401(client):
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.get("/api/paper")).status_code == 401


async def test_bad_address_rejected(client):
    assert (await client.get("/api/auth/nonce", params={"address": "0x123"})).status_code == 400


async def test_signature_from_another_wallet_rejected(client, wallet):
    j = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    other = Account.create()
    sig = other.sign_message(encode_defunct(text=j["message"])).signature.hex()
    r = await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": "0x" + sig.removeprefix("0x")})
    assert r.status_code == 401
    assert (await client.get("/api/me")).status_code == 401


async def test_garbage_signature_rejected(client, wallet):
    j = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    r = await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": "0xdeadbeef"})
    assert r.status_code == 401


async def test_nonce_is_single_use(client, wallet):
    j = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    sig = "0x" + wallet.sign_message(encode_defunct(text=j["message"])).signature.hex().removeprefix("0x")
    assert (await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": sig})).status_code == 200
    assert (await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": sig})).status_code == 401


async def test_expired_nonce_rejected(app, client, wallet):
    j = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    async with app.state.sessionmaker() as db:
        await db.execute(update(AuthNonce).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    sig = "0x" + wallet.sign_message(encode_defunct(text=j["message"])).signature.hex().removeprefix("0x")
    assert (await client.post("/api/auth/verify", json={"nonce": j["nonce"], "signature": sig})).status_code == 401


async def test_logout_ends_session(signed_in):
    r = await signed_in.post("/api/auth/logout", json={})
    assert r.status_code == 200
    signed_in.cookies.clear()
    assert (await signed_in.get("/api/me")).status_code == 401


async def test_owner_role_from_settings(app, client, wallet):
    app.state.settings.owner_addresses = wallet.address.upper().replace("0X", "0x")
    r = await sign_in(client, wallet)
    assert r.json()["role"] == "owner"


async def test_writes_require_json_content_type(signed_in):
    r = await signed_in.post("/api/paper/reset", content="x", headers={"content-type": "text/plain"})
    assert r.status_code == 415
    r = await signed_in.post("/api/paper/swap", data={"from_asset": "USDC"})  # form post, like a CSRF attempt
    assert r.status_code == 415


async def test_sign_in_requests_are_rate_limited(client, wallet):
    from app import auth

    auth._nonce_hits.clear()
    codes = [(await client.get("/api/auth/nonce", params={"address": wallet.address})).status_code for _ in range(22)]
    assert codes[:20] == [200] * 20 and codes[20:] == [429, 429]
    auth._nonce_hits.clear()
