"""The parts of the API contract the web app and status page rely on, shared with the Cloudflare Worker."""

from decimal import Decimal

import pytest
from eth_account.messages import encode_defunct

from app.config import Settings
from app.main import features


SWAP = {"from_asset": "USDC", "to_asset": "ETH", "amount": "10"}
SITE = "https://cimphawng.test"  # the site_uri the test app is configured with


# ---- writes only from our own site ----------------------------------------------------------

async def test_writes_from_another_site_are_refused(signed_in):
    for origin in ["https://evil.example", "http://cimphawng.test", "null", "https://cimphawng.test.evil.example"]:
        r = await signed_in.post("/api/paper/swap", json=SWAP, headers={"Origin": origin})
        assert r.status_code == 403 and "Cross-origin" in r.json()["detail"], origin
    for path, body in [("/api/paper/reset", {}), ("/api/auth/logout", {}), ("/api/account/logout-all", {}),
                       ("/api/bot", {"strategy": "ma", "asset": "ETH", "enabled": False})]:
        r = await signed_in.post(path, json=body, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403, path
    assert (await signed_in.get("/api/paper/trades")).json()["trades"] == []  # nothing happened
    assert (await signed_in.get("/api/me")).status_code == 200  # and the session is still good


async def test_browsers_that_say_cross_site_are_refused(signed_in):
    r = await signed_in.post("/api/paper/swap", json=SWAP, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and "Cross-site" in r.json()["detail"]
    for ok in ["same-origin", "same-site", "none"]:
        assert (await signed_in.post("/api/paper/swap", json=SWAP, headers={"Sec-Fetch-Site": ok})).status_code == 200


async def test_our_own_origin_and_callers_without_one_are_allowed(signed_in):
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers={"Origin": SITE})).status_code == 200
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers={"Origin": SITE + "/"})).status_code == 200
    assert (await signed_in.post("/api/paper/swap", json=SWAP)).status_code == 200  # scripts and tests send none


async def test_extra_origins_are_allowed_when_configured(app, signed_in):
    dev = {"Origin": "http://localhost:8000"}
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers=dev)).status_code == 403
    app.state.settings.extra_origins = "http://localhost:8000, https://www.cimphawng.test"
    assert (await signed_in.post("/api/paper/swap", json=SWAP, headers=dev)).status_code == 200
    assert (await signed_in.post("/api/paper/swap", json=SWAP,
                                 headers={"Origin": "https://www.cimphawng.test"})).status_code == 200
    assert (await signed_in.post("/api/paper/swap", json=SWAP,
                                 headers={"Origin": "https://evil.example"})).status_code == 403


async def test_reads_are_not_origin_checked(signed_in):
    assert (await signed_in.get("/api/me", headers={"Origin": "https://evil.example"})).status_code == 200


# ---- features and readiness -------------------------------------------------------------------

async def test_health_says_what_this_server_can_do(client):
    j = (await client.get("/api/health")).json()
    assert j["ok"] is True and j["mode"] == "paper-only" and j["backend"] == "fastapi"
    f = j["features"]
    assert f["idempotency"] is True and f["account_export"] is True and f["account_delete"] is True
    assert f["real_trading"] is False and f["wallet_signin"] is True and f["paper_trading"] is True
    assert f["paper_bots"] is False  # the test app runs without the price feed, so there is no bot runner


def test_paper_bots_are_advertised_only_when_the_runner_will_exist():
    assert features(Settings(price_feed=True, bots_enabled=True))["paper_bots"] is True
    assert features(Settings(price_feed=True, bots_enabled=False))["paper_bots"] is False
    assert features(Settings(price_feed=False, bots_enabled=True))["paper_bots"] is False


async def test_ready_is_200_with_fresh_prices_and_503_without(app, client):
    r = await client.get("/api/ready")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["status"] == "ready" and j["database"] == "reachable"
    assert {f["asset"] for f in j["feed"]} == {"ETH", "cbBTC"} and j["features"]["idempotency"] is True
    app.state.prices.set("ETH", Decimal("2000"), at=0)  # the feed has gone quiet
    r = await client.get("/api/ready")
    assert r.status_code == 503 and r.json()["status"] == "degraded" and r.json()["ok"] is False


async def test_ready_reports_a_dead_database(app, client):
    class Broken:
        def __call__(self):
            raise ConnectionError("db down")

    app.state.sessionmaker = Broken()
    r = await client.get("/api/ready")
    assert r.status_code == 503 and r.json()["status"] == "unavailable" and r.json()["database"] == "unreachable"


# ---- the network named in the sign-in message ---------------------------------------------------

@pytest.mark.parametrize("chain", [1, 8453, 84532, 11155111])
async def test_sign_in_message_names_the_wallets_network_and_still_verifies(client, wallet, chain):
    n = (await client.get("/api/auth/nonce", params={"address": wallet.address, "chain_id": chain})).json()
    assert f"Chain ID: {chain}\n" in n["message"]
    sig = wallet.sign_message(encode_defunct(text=n["message"])).signature.hex()
    r = await client.post("/api/auth/verify", json={"nonce": n["nonce"], "signature": "0x" + sig.removeprefix("0x")})
    assert r.status_code == 200 and r.json()["address"] == wallet.address.lower()


async def test_without_a_network_the_configured_one_is_used(client, wallet):
    n = (await client.get("/api/auth/nonce", params={"address": wallet.address})).json()
    assert "Chain ID: 8453\n" in n["message"]


@pytest.mark.parametrize("bad", ["999", "abc", "-1", "0", "1.5", "8453abc", "", "9" * 30])
async def test_unsupported_networks_are_refused(client, wallet, bad):
    r = await client.get("/api/auth/nonce", params={"address": wallet.address, "chain_id": bad})
    assert r.status_code in (400, 422), (bad, r.text)
    assert (await client.get("/api/me")).status_code == 401
