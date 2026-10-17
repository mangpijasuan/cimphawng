"""Database tables."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text, types
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamps, so SQLite and PostgreSQL behave the same."""
    return datetime.now(UTC).replace(tzinfo=None)


class Amount(types.TypeDecorator):
    """Exact decimal amounts: NUMERIC on PostgreSQL, a decimal string on SQLite (which has no exact decimals)."""

    impl = String(80)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(types.Numeric(38, 18))
        return dialect.type_descriptor(String(80))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = Decimal(value)
        return value if dialect.name == "postgresql" else format(value, "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True)  # lowercase 0x address
    display_name: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)  # last signed-in use, updated at most every 5 min


class AuthNonce(Base):
    """A sign-in message waiting to be signed. Single use, short-lived."""

    __tablename__ = "auth_nonces"

    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    address: Mapped[str] = mapped_column(String(42))
    message: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime]
    used: Mapped[bool] = mapped_column(default=False)


class Session(Base):
    """A signed-in browser. Only a SHA-256 hash of the cookie token is stored."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class Balance(Base):
    """Paper (pretend) balance of one asset for one member."""

    __tablename__ = "paper_balances"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    asset: Mapped[str] = mapped_column(String(16), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Amount)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    from_asset: Mapped[str] = mapped_column(String(16))
    to_asset: Mapped[str] = mapped_column(String(16))
    amount_in: Mapped[Decimal] = mapped_column(Amount)
    amount_out: Mapped[Decimal] = mapped_column(Amount)
    price_in_usd: Mapped[Decimal] = mapped_column(Amount)
    price_out_usd: Mapped[Decimal] = mapped_column(Amount)
    fee_usd: Mapped[Decimal] = mapped_column(Amount)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    source: Mapped[str] = mapped_column(String(8), default="manual", server_default="manual")  # "manual" or "bot"
    # A reset hides a member's trades from their history but keeps them, so community totals don't drop.
    archived: Mapped[bool] = mapped_column(default=False)


class PaperBot(Base):
    """A member's paper bot: one strategy on one coin, trading their paper wallet on closed 1-hour candles."""

    __tablename__ = "paper_bots"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(16))  # "ma" or "rsi", the same rules as the web app's backtest
    asset: Mapped[str] = mapped_column(String(16))  # the coin it trades against USDC
    size_pct: Mapped[int] = mapped_column(Integer, default=100)  # share of the USDC balance a buy uses
    enabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
    # The newest closed candle (its open time, Unix seconds) the bot has acted on; each candle is used once.
    last_candle_at: Mapped[int] = mapped_column(Integer, default=0)
    last_signal: Mapped[str | None] = mapped_column(String(8))  # "in", "out" or "hold"
    last_run_at: Mapped[datetime | None]
    last_note: Mapped[str | None] = mapped_column(String(200))  # what it did last, or why it couldn't
