import time
from decimal import Decimal

import httpx
import pytest

from app.prices import TOKENS, USDC, GeckoTerminalFeed, PriceBook, StalePrice

ETH_POOL, BTC_POOL, OTHER = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40


def pool(addr, base, quote, reserve):
    return {"attributes": {"address": addr, "reserve_in_usd": str(reserve)},
            "relationships": {"base_token": {"data": {"id": f"base_{base}"}},
                              "quote_token": {"data": {"id": f"base_{quote}"}}}}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if f"/tokens/{TOKENS['ETH']}/pools" in path:  # biggest pool isn't USDC; must be skipped
        return httpx.Response(200, json={"data": [pool(OTHER, TOKENS["ETH"], TOKENS["cbBTC"], 9e8),
                                                  pool(ETH_POOL, TOKENS["ETH"], USDC, 5e7)]})
    if f"/tokens/{TOKENS['cbBTC']}/pools" in path:  # USDC is the base side here
        return httpx.Response(200, json={"data": [pool(BTC_POOL, USDC, TOKENS["cbBTC"], 3e7)]})
    if "/pools/multi/" in path:
        return httpx.Response(200, json={"data": [
            {"attributes": {"address": ETH_POOL, "base_token_price_usd": "3456.78", "quote_token_price_usd": "1"}},
            {"attributes": {"address": BTC_POOL, "base_token_price_usd": "1.0001", "quote_token_price_usd": "97000.5"}},
        ]})
    return httpx.Response(404)


async def test_feed_picks_usdc_pools_and_right_side():
    book = PriceBook(60)
    feed = GeckoTerminalFeed(book, 20, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await feed.discover()
    assert feed.pools == {"ETH": (ETH_POOL, True), "cbBTC": (BTC_POOL, False)}
    await feed.refresh()
    assert book.get("ETH") == Decimal("3456.78") and book.get("cbBTC") == Decimal("97000.5")
    assert book.fresh()


def test_price_book_staleness():
    book = PriceBook(60)
    assert book.get("USDC") == 1
    with pytest.raises(StalePrice):
        book.get("ETH")
    book.set("ETH", Decimal(1), at=time.time() - 61)
    with pytest.raises(StalePrice):
        book.get("ETH")
    assert not book.fresh()
