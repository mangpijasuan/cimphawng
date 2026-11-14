# Cimphawng API

Python (FastAPI) server for wallet sign-in and paper trading at real Base DEX prices.
See the [architecture](../docs/ARCHITECTURE.md) for how this server differs from the hosted private beta. Deployment: [docs/DEPLOY.md](../docs/DEPLOY.md).

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Server status and price freshness, plus `features` (what this server can do; the web app sends request IDs when `idempotency` is on) |
| GET | `/api/ready` | For the status page and uptime monitors: 200 when the database answers and prices are fresh, 503 when degraded or the database is down |
| GET | `/api/auth/nonce?address=0x…&chain_id=` | Returns a Sign-In with Ethereum message to sign (free, no transaction). `chain_id` is the wallet's network: 1, 8453, 84532 or 11155111 (default 8453) |
| POST | `/api/auth/verify` | `{nonce, signature}`: checks the signature and sets a session cookie |
| POST | `/api/auth/logout` | Ends the session |
| GET | `/api/me` | The signed-in member: address, role (`owner` or `member`) |
| GET | `/api/paper` | Paper portfolio: balances valued at live prices (starts with 100 pretend USDC), plus the live price of every tradable asset |
| POST | `/api/paper/swap` | `{from_asset, to_asset, amount}` among USDC, ETH, cbBTC at live prices, with a 0.3% fee. `amount` is a string of plain digits with up to 18 decimals. Needs an `Idempotency-Key` header (see below) |
| GET | `/api/paper/trades` | Trade history, newest first |
| POST | `/api/paper/reset` | Back to 100 USDC. Needs an `Idempotency-Key` header |
| GET | `/api/account/export?cursor=` | The member's account and every trade (archived too), newest first, 200 per page; follow `next_cursor` for more |
| POST | `/api/account/logout-all` | Ends every session of this member. Needs a sign-in from the last 10 minutes |
| POST | `/api/account/delete` | `{confirmation: <your wallet address>}`: deletes the paper account, trades, receipts, bot and sessions. Needs a sign-in from the last 10 minutes |
| GET | `/api/bot` | The member's paper bot (strategy, coin, buy size, running or not, what it did last), the current signal, and its last 10 trades |
| POST | `/api/bot` | `{strategy: "ma" or "rsi", asset: "ETH" or "cbBTC", size_pct: 10–100, enabled}`: set up, start, change or stop the bot |
| GET | `/api/stats` | Public System monitor numbers: uptime, memory, load, API requests per minute (30 min), responses by status, price ages and feed refresh counts, database ping and size, member and paper-trade counts. No personal data; database figures are cached for 5s |

Interactive docs: `/api/docs`. Every write must be sent as `application/json`, and from the site's own address: a write whose `Origin` isn't `CIMP_SITE_URI` (or listed in `CIMP_EXTRA_ORIGINS`, comma-separated, e.g. `http://localhost:8000` while developing), or that a browser marks `Sec-Fetch-Site: cross-site`, is refused with 403. In `infra/`, `CIMP_SITE_URI` is built from `SITE_DOMAIN`.

**Request IDs.** Every swap and reset carries an `Idempotency-Key` header (16–80 letters, digits, `-` or `_`; the web app uses a UUID). If the answer is lost and the app retries with the same ID, it gets the original answer back (with `replayed: true`) and nothing is repeated; a retried reset can never erase later trades. Reusing an ID for a different request is a 409. A refused request isn't remembered.

## Safety built in

- **Sign-in:** members sign a server-written message in their own wallet. The server only checks signatures and never sees keys or seed phrases.
- **Sign-in nonces** are single-use and expire after 10 minutes.
- **Sessions:** the random session token lives in an HttpOnly, Secure, SameSite=Lax cookie. The database stores only its SHA-256 hash.
- **Stale-data guard:** swaps are refused if live prices are more than 2 minutes old.
- **Swaps lock both balance rows** until they finish, so simultaneous swaps can't spend the same balance twice.
- **Rounding is down at every step** (dollar value, fee, amount received), the same on this server and on the Cloudflare Worker, so a fill is identical on both.
- **Exact decimal maths** everywhere (no floating point), with 18 decimal places like ERC-20 tokens.
- **Paper bots** use the same swap code and guards, act only on fully closed 1-hour candles (once per candle, under a row
  lock), and pause instead of trading when candles are missing or behind, or prices are stale.

## Paper bots

Each member can run one bot on ETH or cbBTC, against USDC. The rules are the web app's backtest rules, in `app/bots.py`:

- **MA cross:** be in the coin while MA20 is above MA50, in USDC while it's below.
- **RSI 30/70:** buy when RSI 14 drops below 30, sell when it rises above 70, otherwise hold.

A bot buys (with its buy size of the USDC balance) only when it holds none of its coin, and always sells all of it. Trades
are marked `"source": "bot"` in `/api/paper/trades`. The runner checks every `CIMP_BOT_CHECK_S` seconds (default 60);
set `CIMP_BOTS_ENABLED=false` to turn it off.

## Database migrations

The API applies Alembic migrations (`migrations/`) on start-up, so a deploy only needs a restart. A database created
before migrations existed is recognised and upgraded in place. After changing `app/models.py`:

```bash
alembic revision --autogenerate -m "what changed"   # uses CIMP_DATABASE_URL, like the API
```

`tests/test_migrations.py` fails if the migrations and the models ever disagree.

## Run locally

```bash
cd server
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest pytest-asyncio
CIMP_COOKIE_SECURE=false uvicorn app.main:app --reload     # http://localhost:8000/api/docs
```

It uses a local SQLite file by default. Settings are environment variables prefixed with `CIMP_` (see `app/config.py`).

## Tests

```bash
python -m pytest -q                                   # SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/cimp_test python -m pytest -q   # PostgreSQL
```

`shared/paper-fixtures.json` holds swaps that this server and the Cloudflare Worker (`hosted/`) must both fill identically, to the last digit. Change a rule (fee, minimum, rounding) in both and update that file once.

The PostgreSQL run also covers concurrency: parallel swaps can't overspend, a new member opening many tabs at once is handled,
and two bot runners never trade the same candle twice.
GitHub Actions runs both on every pull request that touches `server/`.

Dependencies are pinned in `requirements.txt`, generated from `pyproject.toml` with `uv pip compile pyproject.toml --python-version 3.12 -o requirements.txt`.
