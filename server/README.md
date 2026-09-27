# Cimphawng API

Python (FastAPI) server for wallet sign-in and paper trading at real Base DEX prices.
Part of step 3 in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Deployment: [docs/DEPLOY.md](../docs/DEPLOY.md).

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Server status and price freshness |
| GET | `/api/auth/nonce?address=0x…` | Returns a Sign-In with Ethereum message to sign (free, no transaction) |
| POST | `/api/auth/verify` | `{nonce, signature}`: checks the signature and sets a session cookie |
| POST | `/api/auth/logout` | Ends the session |
| GET | `/api/me` | The signed-in member: address, role (`owner` or `member`) |
| GET | `/api/paper` | Paper portfolio: balances valued at live prices (starts with 100 pretend USDC) |
| POST | `/api/paper/swap` | `{from_asset, to_asset, amount}` among USDC, ETH, cbBTC at live prices, with a 0.3% fee |
| GET | `/api/paper/trades` | Trade history, newest first |
| POST | `/api/paper/reset` | Back to 100 USDC |

Interactive docs: `/api/docs`. Every write must be sent as `application/json`, which blocks cross-site form attacks.

## Safety built in

- **Sign-in:** members sign a server-written message in their own wallet. The server only checks signatures and never sees keys or seed phrases.
- **Sign-in nonces** are single-use and expire after 10 minutes.
- **Sessions:** the random session token lives in an HttpOnly, Secure, SameSite=Lax cookie. The database stores only its SHA-256 hash.
- **Stale-data guard:** swaps are refused if live prices are more than 2 minutes old.
- **Swaps lock both balance rows** until they finish, so simultaneous swaps can't spend the same balance twice.
- **Exact decimal maths** everywhere (no floating point), with 18 decimal places like ERC-20 tokens.

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

The PostgreSQL run also covers concurrency: parallel swaps can't overspend, and a new member opening many tabs at once is handled.
GitHub Actions runs both on every pull request that touches `server/`.

Dependencies are pinned in `requirements.txt`, generated from `pyproject.toml` with `uv pip compile pyproject.toml --python-version 3.12 -o requirements.txt`.
