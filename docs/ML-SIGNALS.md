# Machine learning for Guided Trading

The first model is an offline ranker for one equity breakout strategy and one fixed evaluation horizon. Deterministic rules qualify a setup. A simple ridge regression learns to reorder eligible candidates by estimated net outcome. **The rules-only ranking remains the displayed result.** The prototype records a second ranking for comparison; it cannot submit or approve orders.

## Run the prototype

From the repository root, with Python 3.11 or newer:

```sh
python -m unittest research.test_signal_ranker -v
python -m research.signal_ranker
```

The demo uses deliberately invented outcomes and no external packages, market feeds, or credentials. Its output compares the top choice of each ranker at identical decision times. The result demonstrates the mechanics; it provides no evidence of market performance.

## Data and validation contract

- Begin with a small stock/ETF watchlist. Each feature row carries signal ID, strategy version, decision time, expiry and the existing rule-gate result. Retain the source observations and availability timestamps for point-in-time reconstruction. The gate service must supply the same eligible universe to both arms.
- Initial inputs are normalized trigger strength, relative volume, realized volatility and spread, measured using only information available at decision time. Reject expired, blocked, malformed and future observations. A missing or unusable model leaves the deterministic ranking in place.
- Use a fixed, predeclared entry and exit simulation for the same horizon. Record the time the outcome became knowable, gross return, spread, fees, slippage and fill assumptions. Report missed fills explicitly; do not discard hard-to-fill picks when comparing policies. The prototype accepts precomputed net outcome labels and does not simulate fills.
- Split by decision timestamp, keeping all symbols for the same decision together. Exclude training labels that reach into the holdout. In market-data evaluation, tune with walk-forward windows and appropriate embargoes, fit preprocessing on training only, freeze the baseline and model policy, then evaluate once on a sealed period. Forward paper trading is the next independent check.
- Predeclare sample size, window length, minimum improvement after costs and maximum tolerated drawdown, turnover and exposure. Compare the same opportunity set and budget, include uncertainty, and test across sessions and regimes. Treat ambiguous or underpowered results as inconclusive. A mean-return comparison from this prototype is insufficient for promotion.
- Before serving scores, register the data snapshot, features, training window, fitted coefficients, strategy and model versions, evidence, and owner approval. Monitor missing data, drift and post-cost results; fall back to rules on problems. Rank within the same tested strategy and horizon. Do not display the rank as a win probability.

## Product boundary

After validation, Guided Trading can show a plain-language reason such as “This setup ranked higher because trading activity was stronger and the spread was narrower.” Generate reasons from the actual stored inputs and score contributions. If nothing qualifies, show **No qualified setups**. Keep eligibility, account limits, order approvals and execution in the deterministic gateway. Automated execution requires a separate opt-in mandate. A model promotion never turns on live trading.

The next implementation step is to collect permitted point-in-time data, wire the existing eligibility checks to the research input contract and run the two rankers in parallel on the same paper opportunities. Keep the live app unchanged until there is evidence for promotion.
