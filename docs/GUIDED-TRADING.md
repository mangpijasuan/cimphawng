# Guided Trading: quantitative tools without code

**Product design · Proposed · First release: stocks and ETFs in paper mode**

Cimphawng does the scanning, testing and order preparation. A beginner can use the results without writing code, picking indicators or searching for research. They still decide whether to trade and how much to risk. The product promise is **“See what qualified, why it qualified, and what could go wrong.”**

Use the existing red-and-navy design and English/Zomi language switch. Make **Guided** the first screen for new users and retain **Terminal** as the advanced view. Both read the same signal and order records. Show **Paper · No real money** beside the account name and again on the confirmation button. A change of account or mode clears any pending approval.

## The beginner journey

| Screen | What the user sees | Main action |
| --- | --- | --- |
| Start | A short explanation of paper trading, with a preconfigured watchlist and a demo that needs no broker sign-in. | Start practice |
| Qualified setups | One lead card and up to two alternatives, with the watchlist, session and last update visible. An empty state explains when nothing qualifies. | See why it qualifies |
| Setup detail | What the strategy detected, the quote age, entry condition, what invalidates the idea, estimated trading costs, and the main downside. Evidence and test results expand on demand. | Preview paper order |
| Review | Instrument, account, side, shares, limit price, estimated amount, fees and the loss scenario. The user chooses the paper budget or size. | Submit paper order |
| Track | Broker-confirmed state, filled and remaining quantity, and cancel action when supported. “Checking with Alpaca” is distinct from “Failed.” | View status / Request cancel |
| Review outcome | Entry, exit, net result after estimated costs and what changed after the original signal. Distinguish model results from actual paper fills. | Review trade |

On a phone, show one primary action per screen; keep the order context and confirmation visible together. On desktop, place the lead card beside the draft review panel. Use text and icons in addition to color for state. Do not replace familiar terms with trading jargon: **“Price changed—review again,” “Order partly filled,” “Nothing meets the rules,”** and **“This setup expired.”**

### Example card (fictional, for interface design)

> **Example ETF · Price broke above its recent range**  
> **Paper practice · Qualified**  
> **Why it appeared:** The price closed above its recent range, and trading activity was above its usual level.  
> **When the idea no longer applies:** The price falls back below the breakout level, or the setup expires.  
> **What could go wrong:** The breakout can reverse. A limit order may not fill. If the market gaps, an exit may be worse than the example loss estimate.  
> **[See evidence] [Preview paper order]**

The order preview distinguishes an **invalidation level** from a **broker-confirmed protective order**. An invalidation level alone does not place an exit. Show loss at a stated exit price as a scenario, with fees and slippage assumptions; show separate exposure (for a fully funded long equity position, cost can be lost if the asset goes to zero). Never describe a stop or budget as a guaranteed loss cap.

## What “qualified” means

1. **Validate the input.** Quotes and completed bars must be fresh, entitled and usable. Block candidates on outages, stale or indicative-only execution quotes, halted symbols, unsupported assets, or prices outside the tested session. Display a reason rather than filling the gap with a guess.
2. **Require strategy evidence.** Ship versioned rules with time-ordered backtests, a sealed holdout, forward-paper evaluation and a benchmark matched to the strategy's horizon and exposure. Record sample size, test dates, realistic fees, spreads and slippage, net results, drawdown, and failure cases. Freeze promotion thresholds before evaluation; insufficient evidence means research-only. No strategy is assumed to have passed.
3. **Require an executable setup.** Enforce strategy-specific limits for spread, liquidity, quote age, valid entry range and expiry. A good historical strategy can still produce an unusable setup today. Recheck the order conditions and broker eligibility at review and dispatch.
4. **Rank only eligible candidates.** For the initial single strategy and common horizon, use a deterministic ordering: strength of the trigger relative to its approved threshold, then lower estimated execution cost, then fresher valid data, then a stable ID. Store ranking inputs and rule version. Avoid mixing incomparable stocks, options and crypto scores. Label the lead card **“Top qualified setup in this watchlist”** and publish the reason it ranked first. This rank is not a win probability or a forecast of returns.
5. **Make no trade a normal result.** Show actionable reason codes such as market closed, feed delayed, spread too wide, entry no longer valid, or no validated setup. Expire drafts immediately on invalidation; do not fall back to a lower-quality signal to meet a daily quota.

Each card references immutable observations, a strategy version, a ranking policy version and a benchmark report. Copilot explains those facts in English or Zomi and prepares typed draft fields. It cannot fabricate missing values, rank trades itself, alter the strategy, choose a real-money budget, arm automation, or submit an order.

## Execution controls

- **Manual:** user enters the ticket and submits after review.
- **Copilot:** user opens a prefilled draft, checks the amount and risk, and explicitly submits the exact reviewed ticket. Editing material fields, quote expiration or a breached price bound forces a new review.
- **Automated:** later, in paper mode first. The user actively enables a published strategy for a single account, selects allowed assets, time window, per-order and daily limits, and sees what pause does. Automatic execution uses the deterministic rules and the same order gateway; a ranking change alone never grants execution permission. Reconcile before resuming after an outage. Pause blocks new submissions; working orders need separate cancellation.

Live rollout requires separate broker and legal review of recommendations and execution. Do not market a score as certainty, guarantee returns, or rely on a disclaimer as a substitute for reviewing personalized recommendations and discretionary execution. See [FINRA's auto-trading alert](https://syndication.finra.org/content/know-risks-auto-trading-services-offered-unregistered-entities) and the [SEC electronic investment advice risk alert](https://www.sec.gov/files/exams-eia-risk-alert.pdf).

## First implementation slice and acceptance

Build a guided paper screen with demo fixtures, explicit empty/expired/feed-unavailable states, a verified strategy-card schema, and a reviewable limit-order ticket connected to the [Alpaca paper order path](TRADING-ARCHITECTURE.md#delivery-and-promotion-gates). Start with one strategy candidate and a small stock/ETF watchlist. Keep sample signals marked **Example**; with no validated strategy, the real feed says **No qualified setups**. Add options and crypto only after their separate data and risk controls pass. Mainnet CIMP remains a separate venue and launch track.

- **Comprehension:** in a usability session, at least 4 of 5 first-time participants can complete a demo order without help and explain whether it uses real money, why it qualified, what could invalidate it, and whether the order filled. Record observations and revise confusing labels before rollout.
- **Evidence:** every displayed qualified signal can be reproduced from its stored observations, version, gates and tie-breaks. No candidate appears as qualified from a disconnected or delayed feed.
- **Order safety:** stale quotes and changed approval fields cannot submit; timeout plus retry cannot create a second order; partial fills and cancel-pending state match broker updates. Preview works with a fake broker in CI; a dedicated Alpaca paper account is used for the integration smoke test.
- **Access:** the first screen is usable without developer credentials or code; paper and live are visually and technically distinct; keyboard and mobile flows provide the same review and cancellation information.
