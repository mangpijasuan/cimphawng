"""Settings, read from environment variables prefixed with CIMP_ (or a .env file)."""

from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIMP_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./cimphawng.db"

    # Sign-in with Ethereum (EIP-4361) message details
    site_domain: str = "cimphawng.com"
    site_uri: str = "https://cimphawng.com"
    chain_id: int = 8453  # Base mainnet
    nonce_minutes: int = 10

    # Comma-separated wallet addresses that get the "owner" role
    owner_addresses: str = ""

    # Session cookie
    cookie_secure: bool = True
    session_days: int = 30

    # Paper trading
    paper_start_usdc: Decimal = Decimal("100")
    swap_fee: Decimal = Decimal("0.003")  # 0.3% per swap, like a typical DEX pool
    min_trade_usd: Decimal = Decimal("0.01")

    # Live prices (GeckoTerminal). Swaps are refused if prices are older than price_max_age_s.
    price_feed: bool = True
    price_refresh_s: int = 20
    price_max_age_s: int = 120

    @property
    def owners(self) -> set[str]:
        return {a.strip().lower() for a in self.owner_addresses.split(",") if a.strip()}
