# Hosted paper-trading API adapter

The private Cimphawng preview now runs the wallet/paper API on Cloudflare Workers with D1 storage.
The Python/PostgreSQL implementation in `server/` is preserved for Hetzner. Both implement the same
browser API: health, SIWE challenge/verify/logout, member, paper portfolio, swaps, history, reset and stats.
No API can submit a real trade, approve token spending, redeem paper gains or move wallet funds.

## Verify locally

Use Node >=22.13 (Node 24 recommended for the built-in SQLite test adapter):

```sh
cd hosted
npm test
npm run ship-check   # fingerprint + tests + invited-beta API journey
```

No npm installation is needed for these tests: the exact ethers 6.15 browser-compatible ESM build
is vendored in `lib/ethers-server.mjs`. Its MIT license is in `../token/web/ethers-LICENSE.md`.
Tests use real SQLite and ephemeral signing wallets. The 21 tests cover single-use/expired/wrong
signatures, secure session flags, persisted account isolation, concurrent spending and reset conflicts,
stale feeds, bad input, logout, rate limiting, and oversized requests.

The live Site uses the supplied Vinext runtime and the same API module, schema and SQL. Built-worker
integration checks additionally validated routing, a D1 migration, signatures, sessions and a paper swap
using fixture prices in an ephemeral database. These tests do not deploy an on-chain token. Browser
wallet prompts and actual-device behavior still require user testing.

## Optional independent Cloudflare hosting

The existing private Site is already provisioned; do not create another database for it.
For a separate deployment in your own Cloudflare account, the included `worker.mjs` is a standalone
adapter and `prepare-assets.mjs` copies only the intended public assets. Review hosting access controls
before exposing a new deployment: Sites' owner-private boundary does not automatically transfer to an
independent Cloudflare account.

1. Run `node prepare-assets.mjs` from `hosted/`.
2. Provision a D1 database and replace the explicit placeholder in `wrangler.jsonc`.
3. Set `vars.SITE_ORIGIN` to the exact intended HTTPS origin. It defines the SIWE domain and write-origin guard.
4. Apply all pending `drizzle/*.sql` migrations, in order, using the normal Wrangler D1 migration mechanism. Never edit an applied migration.
5. Deploy through your Cloudflare account with Wrangler. Do not commit credentials.

No deployment command has been run against an independent Cloudflare account. The placeholder config
is deliberately not usable without choosing a real database and origin.

## Storage and safeguards

Sign-in messages use the selected Ethereum, Base, Base Sepolia or Ethereum Sepolia wallet network.
Nonces are consumed atomically before signature verification and expire after ten minutes. Session
cookies are HttpOnly, Secure and SameSite=Lax; only token hashes are stored. Each wallet has its own
persistent portfolio. Wallet ownership does not grant platform administration. Contract-wallet EIP-1271
signatures and social-login wallets are not implemented; use an ordinary EOA browser wallet initially.

Amounts and prices use 18-place integer arithmetic. Paper swaps charge a simulated 0.3% fee. Optimistic
version checks and atomic D1 batches protect spending and history during parallel requests. Conflicts
return 409. A reset archives trades rather than deleting the audit history. The starting 100 USDC is
pretend money; paper balances are never converted to CIMP.

The API reads GeckoTerminal's deepest matching USDC pools on Base, with a shared cache and refresh
lease. Prices older than 120 seconds cannot fill a trade. Source failures preserve old timestamps;
there is no synthetic fallback. USDC is modeled as $1. Public stats expose aggregate counts and D1
latency, not wallet records. Worker CPU, memory and uptime are marked unavailable rather than invented.

The platform checklist is at `/setup.html`. Mainnet token purpose, distribution and launch remain
undecided; `docs/CIMP-UTILITY-PROPOSAL.md` is a draft for review.


## Private beta safeguards (0.2.0-beta.1)

The hosted adapter now requires an `Idempotency-Key` (16–80 alphanumeric, underscore or hyphen characters) for each paper swap/reset. Retry an uncertain operation with its original key and exact JSON values. Replays return the original fill and current portfolio. Reusing a key with a different payload returns 409. Receipts remain until account deletion. The browser retains an unresolved request in session storage scoped to the wallet; keep the tab open until resolved. Changing tabs/devices creates a separate intent, so review history first.

`GET /api/release` reports the content fingerprint and supported features. `GET /api/health` checks core database connectivity; `GET /api/ready` also checks live prices and returns 503 when degraded. `GET /api/bot` explicitly returns 501; scheduled Python bots do not run on the hosted Worker.

Account routes provide paginated private exports, logout of all sessions and deletion of active paper records. Logout-all/deletion require a signature within ten minutes. Deletion requires the wallet address typed by the member. A reset only archives history. Provider backups are separate and may retain copies.

The general API limit is 180 requests/IP/minute (excluding health/release), nonce 20/IP/minute, verification 40/IP/minute, paper mutations 60/wallet/minute, exports 30/wallet/minute. The shared price refresh lease bounds upstream calls. These limits are safeguards, not a DDoS or hosting-spend guarantee. Monitoring and platform budget controls still need an owner.

See [launch operations](../docs/LAUNCH-READINESS.md) for release, rollback, recovery and remaining public-launch gates. The Python server has a different feature set; do not assume these hosted safeguards are implemented there.
