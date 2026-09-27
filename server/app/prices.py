"""Live USD prices for paper trading, from each token's most liquid USDC pool on Base (via GeckoTerminal).

The same approach as the web app's Base DEX panel, but run once on the server for everyone, so all
members share one set of API calls.
"""

import asyncio
import logging
import time
from decimal import Decimal

import httpx

log = logging.getLogger("cimphawng.prices")

GT = "https://api.geckoterminal.com/api/v2"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TOKENS = {  # asset -> token address on Base
    "ETH": "0x4200000000000000000000000000000000000006",  # WETH
    "cbBTC": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
}
ASSETS = ("USDC", *TOKENS)


class StalePrice(Exception):
    pass


class PriceBook:
    """Latest price per asset. USDC is treated as exactly $1."""

    def __init__(self, max_age_s: int):
        self.max_age_s = max_age_s
        self._prices: dict[str, tuple[Decimal, float]] = {}

    def set(self, asset: str, price: Decimal, at: float | None = None) -> None:
        self._prices[asset] = (price, time.time() if at is None else at)

    def get(self, asset: str) -> Decimal:
        if asset == "USDC":
            return Decimal(1)
        if asset not in self._prices:
            raise StalePrice(f"no price for {asset} yet")
        price, at = self._prices[asset]
        if time.time() - at > self.max_age_s:
            raise StalePrice(f"{asset} price is {int(time.time() - at)}s old")
        return price

    def fresh(self) -> bool:
        try:
            return all(self.get(a) > 0 for a in TOKENS)
        except StalePrice:
            return False

    def snapshot(self) -> dict[str, dict]:
        return {a: {"price_usd": str(p), "age_s": round(time.time() - t)} for a, (p, t) in self._prices.items()}


class GeckoTerminalFeed:
    """Background task: find the pools once, then refresh prices every refresh_s seconds."""

    def __init__(self, book: PriceBook, refresh_s: int, client: httpx.AsyncClient | None = None):
        self.book = book
        self.refresh_s = refresh_s
        self.client = client or httpx.AsyncClient(timeout=12, headers={"Accept": "application/json"})
        self.pools: dict[str, tuple[str, bool]] = {}  # asset -> (pool address, token is base side)

    async def _json(self, url: str) -> dict:
        r = await self.client.get(url)
        r.raise_for_status()
        return r.json()

    async def discover(self) -> None:
        for asset, token in TOKENS.items():
            j = await self._json(f"{GT}/networks/base/tokens/{token}/pools?page=1")
            best = None
            for p in j.get("data", []):
                a, rel = p.get("attributes", {}), p.get("relationships", {})
                base = str(rel.get("base_token", {}).get("data", {}).get("id", "")).lower()
                quote = str(rel.get("quote_token", {}).get("data", {}).get("id", "")).lower()
                if f"base_{USDC}" not in (base, quote):
                    continue
                reserve = Decimal(a.get("reserve_in_usd") or 0)
                if best is None or reserve > best[0]:
                    best = (reserve, str(a["address"]).lower(), base == f"base_{token}")
            if best is None:
                raise RuntimeError(f"no USDC pool found for {asset}")
            self.pools[asset] = (best[1], best[2])
        log.info("price pools: %s", self.pools)

    async def refresh(self) -> None:
        addrs = ",".join(p for p, _ in self.pools.values())
        j = await self._json(f"{GT}/networks/base/pools/multi/{addrs}")
        by_pool = {str(p["attributes"]["address"]).lower(): p["attributes"] for p in j.get("data", [])}
        for asset, (pool, is_base) in self.pools.items():
            a = by_pool.get(pool)
            if not a:
                continue
            price = Decimal(a["base_token_price_usd" if is_base else "quote_token_price_usd"])
            if price > 0:
                self.book.set(asset, price)

    async def run(self) -> None:
        backoff = self.refresh_s
        while True:
            try:
                if not self.pools:
                    await self.discover()
                await self.refresh()
                backoff = self.refresh_s
            except asyncio.CancelledError:
                raise
            except Exception as e:  # keep running: stale prices simply block swaps
                backoff = min(backoff * 2, 300)
                log.warning("price refresh failed (%s); retrying in %ss", e, backoff)
            await asyncio.sleep(backoff)
