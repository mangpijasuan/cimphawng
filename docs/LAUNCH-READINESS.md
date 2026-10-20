# Cimphawng private beta release

Release: **0.2.0-beta.1**. Source base: `8fbadbcf73c7024ad4449cec69b542bf093745ef`.
The deployed audience remains owner-private. No mainnet token, real trading, paid service or scheduled hosted bot is enabled.

## Implemented and verified

- Persistent wallet sign-in and isolated paper balances; secure session cookies and atomic nonce consumption.
- Integer paper accounting, optimistic concurrency, atomic trade receipts, and idempotent swap/reset retries.
- Paginated data export, recent-signature account deletion and logout of all sessions.
- Feed freshness guards, explicit hosted capabilities, readiness diagnostics, request IDs, privacy-conscious structured errors and bounded request/refresh rates.
- Guide, support issue link, account page and service status; navy/emerald styling.
- Immutable migration 0001 adds operation receipts, feed diagnostics and session creation time; 0000 remains unchanged.
- 21 SQLite backend tests, including concurrency, stale feeds, export pagination and a fixture backup/restore integrity drill.
- Compiled Site Worker integration checks cover the new routes/assets plus real signature verification, a session and a fixture-priced paper trade against ephemeral D1.
- Automated ship gate: `node hosted/scripts/ship-check.mjs` (or `npm run ship-check` in `hosted/`) re-checks the release fingerprint, the 21-test suite, beta assets, and an invited-member API journey (sign-in → trade → idempotent retry → export → logout → delete).

## Ship verification log

| When | What | Result |
| --- | --- | --- |
| 2026-10-20 | `node hosted/scripts/release.mjs --check` | Fingerprint `575d324442ec…688d4b` matches `hosted/lib/release.mjs` |
| 2026-10-20 | `npm test` in `hosted/` | 21/21 pass |
| 2026-10-20 | `node hosted/scripts/ship-check.mjs` | Pass (includes invited-beta API journey) |
| 2026-10-20 | Live Site `GET /api/health` (unauthenticated curl) | **401 Sign in required** — audience still owner-private; external monitors need an approved access method |
| 2026-10-20 | Browser/device wallet prompts | Still owner/device QA (not automatable without a connected EOA extension on supported devices) |
| 2026-10-20 | Hosted D1 restore rehearsal | Still pending (local fixture restore only) |

**Private beta ship decision:** code and automated gates are green for owner-private use. Do not widen audience until the public-launch owner gates below are closed.

## Source and release verification

The repository's default branch is `claude/hobby-project-app-webapp-nmtkai`; `main` is older. Use the validated release branch/PR commit, not an assumed `main`.

From the repository root, run `node hosted/scripts/release.mjs --check`. After intentionally changing any release input, regenerate with `node hosted/scripts/release.mjs`, test and review the diff. Before cutting a build, also run `node hosted/scripts/ship-check.mjs`. The Site uses the same release script as `scripts/release.mjs`; the input mapping normalizes the Site's public assets and the repository's root assets. `GET /api/release` must match the generated `hosted/lib/release.mjs` fingerprint. This checks core API/schema/migrations and listed application assets, not the entire hosting infrastructure.

Native Site versions retain exact source and deployment provenance. Publish only the tested source archive and preserve private audience. Do not copy credentials into Git, logs or issue reports.

## Operational runbook

1. Core outage: check `/api/health`, native deployment state and Worker logs, using the request ID shown to the member. Avoid sharing cookies/signatures/wallet payloads.
2. Feed outage: `/api/ready` returns 503/degraded; old timestamps are preserved and stale fills blocked. Wait for provider recovery; never replace failed prices with invented values.
3. Retry/timeouts: preserve the same wallet, key and payload. Check trade history if moving to a different tab/device. Never deliberately rotate a key to bypass an unresolved request.
4. Rollback: redeploy a known-good native Site version with a schema-compatible API, preserve audience and inspect health/readiness. Migration 0001 is additive; do not drop its tables during an application rollback.
5. Security incident: preserve restricted logs, remove unauthorized access through host controls, review sessions, coordinate account revocation and provider response. Do not expose incident credentials in public issues.

## Hosted recovery rehearsal (pending)

Before public launch, the hosting owner must verify backup availability, retention and permissions for the actual production D1 database. Record the database identity, available restore points, recovery owner and approved RPO/RTO.

Perform a non-production rehearsal: restore a provider-supported snapshot/time-travel point into an isolated destination, apply/verify schema history, run integrity and foreign-key checks, then validate account balances, active/archived fills, receipt replay and session revocation using test records. Confirm no notifications or public traffic point at the restored destination. Record restore-point timestamp, restored counts, checks and elapsed recovery time. Protect and clean up copied personal data according to the retention policy.

The automated test restores a generated local fixture only. It does not back up, alter or restore the live account database. Provider backup controls are not exposed by this app.

### Owner fill-in (copy into an ops note; do not commit secrets)

```
Database id / name:
Backup retention / available restore points:
Recovery owner:
RPO / RTO:
Rehearsal date / restore-point timestamp:
Restored account/trade/receipt counts:
Integrity + FK check result:
Elapsed recovery time:
Cleanup of copied personal data completed (yes/no):
```

## Public launch gates still open

Use this checklist. Items marked **automated** are covered by `ship-check` / CI; the rest need the hosting owner.

- [ ] **Device wallet QA (owner):** real EOA sign-in, cancel/reject, network/account changes, refresh after timeout, mobile wallet browser, keyboard/screen reader, real viewports.
- [x] **Invited journey path (automated):** sign-in → trade → retry → export → sign out → deletion is locked by `ship-check`. Still pending: send invitations and run the same path on real test wallets against the live Site.
- [ ] **Ops monitor (owner):** assign an operations owner; configure an external monitor for `/api/health` and `/api/ready` with an approved access method for the private audience; alert after sustained failures; test notification delivery.
- [ ] **Spend caps (owner):** configure and verify hosting spend/error thresholds in the provider account. Request limits alone do not cap billing.
- [ ] **D1 recovery rehearsal (owner):** complete the hosted backup/restore rehearsal above and choose recovery objectives.
- [ ] **Legal/owner review:** beta terms/privacy on `/guide`, lawful price-data use, provider retention, support ownership. Current documents are drafts, not legal approval.
- [ ] **Production domain & audience (owner):** select domain and sharing policy; validate HTTPS, SIWE origin and redirects. Audience changes require an explicit decision. Live Site currently returns 401 to unauthenticated callers.
- [ ] **Mainnet token (separate):** utility, distribution, contract review and user-owned deployment are not part of this paper-trading release.
