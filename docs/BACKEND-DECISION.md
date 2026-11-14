# Backend decision: one writer, one roadmap order

**Status: Proposed · November 13, 2026 · Needs an owner decision.** Nothing here changes code or deployments.

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
| Idempotency keys and operation receipts | Yes | Not found |
| Account export, deletion, logout-all | Yes | Not found |
| Scheduled paper bots | No (returns 501) | Yes (`bots.py`) |
| System stats | Yes (no uptime, memory or load) | Yes |
| Alpaca paper pilot | Yes (owner-only, one working order) | No |
| Numeric model | Integer / BigInt, 18 decimals | `Decimal`, 18 decimals |
| Concurrency control | Optimistic version check | Row locks (`SELECT … FOR UPDATE`) |
| Test evidence | 30 tests on SQLite | 50 tests on SQLite, plus a PostgreSQL run in CI |
| Deployment evidence | Private Site is live; standalone Worker never deployed | Hetzner files exist; no recorded deployment |

Neither backend is a superset of the other. Each has features the other lacks, and the swap fee, minimum trade and price rules are duplicated in JavaScript and Python.

## Options

**A. Worker + D1 as the long-term backend.** Cheapest to run and already live. But the paper architecture needs a double-entry journal, an outbox, workers for market data and reconciliation, and row-level transactions. D1 has no row locks (writes are batched and version-checked), and background work would have to run as scheduled or queue-driven Workers rather than the long-running worker the design assumes. I haven't prototyped that, so the cost of redesigning around those limits is an estimate, not a measurement. This also contradicts both architecture documents.

**B. FastAPI + PostgreSQL as the single target, with a staged cutover (recommended).** Matches both architecture documents. PostgreSQL supports the planned journal, outbox and reconciliation work directly, and the server already has row locking and a PostgreSQL test run. The cost is real: it means porting the Worker-only features and operating a server.

**C. Keep both indefinitely.** Lowest effort now, but the two keep drifting. Every rule change is made twice, and "which backend is live for this user" stays an open question.

## Decision (proposed): option B

FastAPI and PostgreSQL become the only long-term writer. The Worker and D1 remain the private-beta writer until a rehearsed cutover and then retire. The rules below stop the split from growing in the meantime.

1. **Freeze the Worker.** From now on it receives only security fixes, bug fixes, and the existing Alpaca pilot. No new product features.
2. **Port before cutover.** The server must gain the Worker-only features that members rely on before it can replace the Worker (checklist below).
3. **No two writers for one account.** At cutover, pause the old writer, snapshot, import, reconcile, then route to the new one. Follow the cutover steps already in [ARCHITECTURE.md](ARCHITECTURE.md) (slices 3 and 4).
4. **One set of rules.** Until the Worker retires, a change to fee, minimum trade, price freshness or the sign-in message must land in both backends in the same pull request, with a test in each.
5. **New Trade work targets the server.** Stage 2 and later of [TRADING-ARCHITECTURE.md](TRADING-ARCHITECTURE.md) are built on FastAPI and PostgreSQL. The Alpaca pilot is ported as part of the paper-core work, not extended on D1.

### Port checklist (server gains what the Worker has)

- Idempotency keys with stored receipts and replay, including the 409 on a reused key with a different payload.
- Account export (paginated), account deletion, and logout-all, with the recent-sign-in requirement.
- The Alpaca paper pilot adapter, with the same one-working-order rule, no-resend rule and operator recovery steps ([hosted/README.md](../hosted/README.md#recovering-an-unresolved-order)).
- Same-origin checks on writes (the server currently relies on the JSON content type and `SameSite=Lax`).
- A shared fixture so both backends are tested against the same expected fills, fees and rejections.

## Roadmap order

Both roadmaps stay, in this order. Each step needs its exit evidence before the next one starts.

1. **Close the private-beta launch gates** in [LAUNCH-READINESS.md](LAUNCH-READINESS.md) that are owner tasks: real-device wallet QA, an external monitor, spend caps, a D1 restore rehearsal, and legal review. These apply to whatever is live today.
2. **Run the Alpaca paper smoke test** (the pilot is documented as "pending" until a dedicated paper account passes it).
3. **Paper-core slices 0 to 2** from [ARCHITECTURE.md](ARCHITECTURE.md): one reconciled release baseline, market-data provenance, then the PostgreSQL journal and order path in staging.
4. **Port checklist above**, alongside slice 2.
5. **Paper-core slices 3 and 4:** migration rehearsal, then controlled cutover. The Worker retires after the rollback window.
6. **Trade stage 1 on PostgreSQL** (Alpaca connection, account read, manual limit order), then stage 2 (real-time signals and Copilot) and later, each with its own exit evidence.
7. **Parallel and gated separately:** the CIMP token and DEX track, and any live-money step. Neither is unlocked by completing a paper step.

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
