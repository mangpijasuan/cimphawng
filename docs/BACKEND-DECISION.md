# Backend decision: one writer, one roadmap order

**Status: Accepted · November 14, 2026.** The owner chose option B (FastAPI and PostgreSQL as the single long-term backend). Proposed November 13. The port checklist below is in progress. **Addendum, same day:** Trade work moves to Olbos Trade (see the [addendum](#addendum-november-14-2026-trade-is-built-on-olbos-trade)). Nothing here deploys anything.

## Why this needs deciding

The repository has two paper-trading backends that implement the same browser API, and two roadmaps that each describe the "next" work.

- [ARCHITECTURE.md](ARCHITECTURE.md) (paper core) targets FastAPI and PostgreSQL and says to keep the Worker and D1 only until a rehearsed cutover.
- [TRADING-ARCHITECTURE.md](TRADING-ARCHITECTURE.md) (Cimphawng Trade) says to use "the existing FastAPI/PostgreSQL direction" and to "avoid operating two writers for the same account".
- The first Trade slice, the Alpaca paper pilot, was built on the Worker and D1 ([hosted/lib/alpaca-paper.mjs](../hosted/lib/alpaca-paper.mjs)). It is documented as running only on the standalone Worker, a deployment the paper architecture says still needs its parity with the live Site verified.

So the stated direction and the code on the default branch disagree, and each new feature makes the split harder to undo.

## What each backend does today

Verified by reading the code on the default branch. "Not found" means no matching code in `server/app/`, not that the feature is impossible.

| Capability | Worker + D1 (`hosted/`) | FastAPI + PostgreSQL (`server/`) |
| --- | --- | --- |
| Wallet sign-in (SIWE), sessions, logout | Yes | Yes |
| Paper swaps, reset, history | Yes | Yes |
| Idempotency keys and operation receipts | Yes | Yes (ported Nov 14) |
| Account export, deletion, logout-all | Yes | Yes (ported Nov 14) |
| Scheduled paper bots | No (returns 501) | Yes (`bots.py`) |
| System stats | Yes (no uptime, memory or load) | Yes |
| Alpaca paper pilot | Yes (owner-only, one working order) | No |
| Numeric model | Integer / BigInt, 18 decimals | `Decimal`, 18 decimals |
| Concurrency control | Optimistic version check | Row locks (`SELECT … FOR UPDATE`) |
| Test evidence | 59 tests on SQLite (26 backend, 4 guided, 29 shared cases) | 120 tests on SQLite (3 more run only on PostgreSQL), 123 on PostgreSQL, including the 29 shared cases |
| Deployment evidence | Private Site is live; standalone Worker never deployed | Hetzner files exist; no recorded deployment |

Neither backend is a superset of the other. Each has features the other lacks, and the swap fee, minimum trade and price rules are duplicated in JavaScript and Python.

## Options

**A. Worker + D1 as the long-term backend.** Cheapest to run and already live. But the paper architecture needs a double-entry journal, an outbox, workers for market data and reconciliation, and row-level transactions. D1 has no row locks (writes are batched and version-checked), and background work would have to run as scheduled or queue-driven Workers rather than the long-running worker the design assumes. I haven't prototyped that, so the cost of redesigning around those limits is an estimate, not a measurement. This also contradicts both architecture documents.

**B. FastAPI + PostgreSQL as the single target, with a staged cutover (recommended).** Matches both architecture documents. PostgreSQL supports the planned journal, outbox and reconciliation work directly, and the server already has row locking and a PostgreSQL test run. The cost is real: it means porting the Worker-only features and operating a server.

**C. Keep both indefinitely.** Lowest effort now, but the two keep drifting. Every rule change is made twice, and "which backend is live for this user" stays an open question.

## Decision: option B

FastAPI and PostgreSQL become the only long-term writer. The Worker and D1 remain the private-beta writer until a rehearsed cutover and then retire. The rules below stop the split from growing in the meantime.

1. **Freeze the Worker.** From now on it receives only security fixes, bug fixes, and the existing Alpaca pilot. No new product features.
2. **Port before cutover.** The server must gain the Worker-only features that members rely on before it can replace the Worker (checklist below).
3. **No two writers for one account.** At cutover, pause the old writer, snapshot, import, reconcile, then route to the new one. Follow the cutover steps already in [ARCHITECTURE.md](ARCHITECTURE.md) (slices 3 and 4).
4. **One set of rules.** Until the Worker retires, a change to fee, minimum trade, price freshness or the sign-in message must land in both backends in the same pull request, with a test in each.
5. ~~**New Trade work targets the server.**~~ **Superseded November 14, 2026** by the [addendum](#addendum-november-14-2026-trade-is-built-on-olbos-trade): Trade work is built on Olbos Trade, not on this repository's server. Original text: Stage 2 and later of [TRADING-ARCHITECTURE.md](TRADING-ARCHITECTURE.md) are built on FastAPI and PostgreSQL. The Alpaca pilot is ported as part of the paper-core work, not extended on D1.

### Port checklist (server gains what the Worker has)

Status on November 14, 2026: four of the five items are done. The Alpaca pilot is no longer planned for this server (addendum), so the item left is the general request rate limits (the Worker limits requests per IP and per account; the server only limits sign-in nonces).

- ✅ Idempotency keys with stored receipts and replay, including the 409 on a reused key with a different payload. The key is now required on swap and reset, as on the Worker. A retry is answered from the stored receipt even if prices have since gone stale, and a retried reset never resets again. (`server/app/paper.py`, migration `0003`.)
- ✅ Account export (paginated), account deletion, and logout-all, with the recent-sign-in requirement. (`server/app/account.py`.) One known difference: `trades[].id` is a number on the server and a UUID on the Worker.
- ➖ *(No longer planned, see the addendum.)* The Alpaca paper pilot adapter, with the same one-working-order rule, no-resend rule and operator recovery steps ([hosted/README.md](../hosted/README.md#recovering-an-unresolved-order)).
- ✅ Same-origin checks on writes: a wrong `Origin` or `Sec-Fetch-Site: cross-site` is refused with 403. The allowed origin is `CIMP_SITE_URI` (set from `SITE_DOMAIN` in `infra/docker-compose.yml`), plus `CIMP_EXTRA_ORIGINS` for development.
- ✅ A shared fixture so both backends are tested against the same expected fills, fees and rejections: [shared/paper-fixtures.json](../shared/paper-fixtures.json), 29 cases run by both test suites.

**What the shared fixture found.** Building it showed the two backends already disagreed, and each difference was fixed on the server (the Worker is the live one, so it stayed as it is):

- The server rounded the fee once at the end. The Worker rounds down at each step (dollar value, fee, amount received). A very large swap differed in the last digit. The server now rounds down at each step too, in a wider arithmetic context.
- The server printed `fee_usd` rounded to 4 places. It now prints the exact value.
- The server's number formatting silently rounded any amount of 29 or more digits (Python's default precision). It now formats exactly.
- The server accepted `1e2`, `+5`, `.5`, `5.`, padded and JSON-number amounts. It now accepts only plain digits with up to 18 decimals, like the Worker.

Also ported because the web app and status page need them on the new server: `features` and `backend` on `/api/health`, `/api/ready`, and the wallet's network (`chain_id`) in the sign-in message. A syntax error in an amount is a 400 on the Worker and a 422 on the server; the fixture accepts either.

## Roadmap order

Both roadmaps stay, in this order. Each step needs its exit evidence before the next one starts.

1. **Close the private-beta launch gates** in [LAUNCH-READINESS.md](LAUNCH-READINESS.md) that are owner tasks: real-device wallet QA, an external monitor, spend caps, a D1 restore rehearsal, and legal review. These apply to whatever is live today.
2. **Run the Alpaca paper smoke test** (the pilot is documented as "pending" until a dedicated paper account passes it).
3. **Paper-core slices 0 to 2** from [ARCHITECTURE.md](ARCHITECTURE.md): one reconciled release baseline, market-data provenance, then the PostgreSQL journal and order path in staging.
4. **Port checklist above**, alongside slice 2. (Four of five items done; general rate limits remain. The Alpaca pilot item is withdrawn.)
5. **Paper-core slices 3 and 4:** migration rehearsal, then controlled cutover. The Worker retires after the rollback window.
6. ~~**Trade stage 1 on PostgreSQL**~~ **Moved to Olbos Trade** (addendum): Trade stages are delivered there, each with its own exit evidence, under that repository's rules. They are no longer a step on this repository's roadmap.
7. **Parallel and gated separately:** the CIMP token and DEX track, and any live-money step. Neither is unlocked by completing a paper step.

## Addendum, November 14, 2026: Trade is built on Olbos Trade

The owner decided that Cimphawng Trade will not get its own trading backend. It is a **brand on the Olbos Trade platform**: the same server for Olbos Trade (worldwide) and Cimphawng Trade (Zomi-focused), with shared quantitative research, algo trading and automated execution, and Alpaca for options, crypto and equity. The first slice is [OlbosTrade PR 286](https://github.com/olbos-technologies/OlbosTrade/pull/286).

Why this is consistent with option B: the owner chose FastAPI and PostgreSQL as the single long-term backend, and Olbos Trade already runs on exactly that stack with signals, risk gates, broker adapters and reconciliation. Building a second copy here would recreate the two-writers problem this document exists to prevent.

What changes:

- **Rule 5 is superseded.** Trade stages 1 and later are built in Olbos Trade, not on `server/` here.
- **The Alpaca pilot port is withdrawn.** The Worker keeps its owner-only pilot (rule 1: frozen, bug and security fixes only) until the Worker retires. It is not ported to `server/`.
- **Roadmap step 6 moves** to Olbos Trade. Steps 1 to 5 and 7 are unchanged.
- **Where the standing rules apply.** Work in Olbos Trade follows that repository's `AGENTS.md`, which governs there, including its rules on paper-by-default, risk gates and no unattended deploys.

What does not change:

- This repository's paper-trading core, the Worker and D1 beta, the Python server and its cutover plan, and the CIMP token and DEX track stay as described above. They are not merged into Olbos Trade.
- Nothing here authorizes a domain cutover, an Alpaca account connection, a live order, automation or a deployment.

Open questions this raises (owner decisions, not made here):

1. What is the Python server in this repository *for* once Trade lives elsewhere: the CIMP community paper-trading product only, or should it be retired in favour of Olbos Trade as well? Until decided, keep the checklist's remaining item (general rate limits) and the cutover plan, and add no new features.
2. Should Cimphawng members sign in to the Olbos Trade platform with the wallet sign-in they use here, or with Olbos Trade's own accounts? This repository's wallet-based identity does not carry over automatically.
3. Cimphawng Trade needs its own domain, DNS, server config and Alpaca redirect settings before it can run outside a preview (see OlbosTrade `docs/BRAND_PLATFORM.md`). The `cimphawng.trade` ownership is still unverified.
4. Legal review and Alpaca country eligibility for a worldwide audience with automated execution are owner items, as before.

## What would change this decision

- **The owner wants to stay small and on managed hosting.** Then option A is reasonable, but the journal, outbox and worker parts of the paper architecture must be redesigned around D1, and both architecture documents need rewriting.
- **A production Hetzner deployment is not wanted or not affordable.** Option B needs a server to operate, back up and monitor. The cost and the operator are not yet chosen.
- **The deployed Site differs from GitHub.** The paper architecture already notes that the Site source and GitHub differ. If the differences are large, slice 0 (reconcile first) may take longer than the port.
- **Real user numbers.** The beta is owner-private today, so a short outage during cutover is cheap now. That gets more expensive as members join, which is a reason to cut over early rather than late.

## Open questions

1. Who runs the production server, and what is the budget? ([DEPLOY.md](DEPLOY.md) describes Hetzner but records no deployment.)
2. Is the Alpaca pilot deployed anywhere? If not, porting it costs nothing in migration.
3. How different is the live Site's source from GitHub's `hosted/` and `index.html`?
4. Who owns the decision to retire the Worker and set the cutover date?
