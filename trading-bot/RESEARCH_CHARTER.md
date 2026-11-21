# Research charter (proposed - to be confirmed BEFORE any new strategy test is run)

Rules: every strategy needs a written economic hypothesis and fixed parameter ranges before testing. Parameters may not be tuned to
improve results. Every test is logged in a registry (count of all variants tried) so multiple-testing corrections are honest.
Data already used (2015-2026) is considered contaminated; new evidence must come from older history (pre-2015) and forward paper trading.

## Acceptance gates (all must pass; otherwise the verdict is "no reliable edge found")
1. Out-of-sample: positive after-cost excess return over Nifty 50 TRI, and positive in at least 70% of rolling 3-year windows.
2. Economic rationale: written down before testing; cites a known risk premium or behavioural/structural reason.
3. Regimes: positive excess in at least 2 of 3 regime buckets (bull / sideways / bear-or-crisis); no bucket may lose more than the benchmark.
4. Net of realistic costs, slippage AND tax scenarios (short-term vs long-term gains): beats Nifty 50 TRI buy-and-hold.
5. Chance: beats >= 1,000 random-selection / random-schedule runs at p <= 0.01 after adjusting for the number of variants tried
   (deflated Sharpe or equivalent), and pooled factor IC t-statistic > 3.
6. Risk: maximum drawdown not worse than the benchmark's; positions <= 2% of average daily traded value; sector/stock caps respected.
7. Stability: at least 80% of neighbouring parameter settings keep positive excess return.
8. Paper trading: >= 6 months (>= 6 rebalances) within the expected tracking band before any real money; live orders only with explicit human approval.

## Candidate hypotheses for Phase 3 (each must be justified before testing)
* H1 cross-sectional momentum (12-1) on a broad point-in-time universe (Nifty 200/500): documented premium; our 46-stock sample was underpowered.
* H2 low volatility / quality: needs point-in-time fundamentals; documented in many markets.
* H3 short-term reversal as liquidity provision: gross signal existed (rev_5d) but costs dominated; test only a cost-aware implementation.
* H4 time-series trend as RISK reduction (not return enhancement): drawdown reduction was suggestive (p 0.15-0.25); test on pre-2015 data incl. 2008.
Not testable with free data (excluded until data exists): iceberg/dark-pool detection, tick-level order flow, HFT.
