# Phase 1 audit of the existing trading research

Scope: ~2,600 lines of Python, 58 automated tests, 13 result reports (3 strategy backtests, alpha lab, 2 multi-factor backtests,
2 Monte Carlo null tests, 2 market-timing tests). Method: read the code, scan for risky constructs, re-derive numbers from the
reports, and run new probes (power study, metric tests). Everything below is either verified or marked as an assumption.

## 1. Headline conclusion
No tested idea shows an edge over passive Nifty 50 investing. But the research was **underpowered** (section 4), so "no edge found"
means "no *large* edge detectable with this data", not "no edge exists". Do not build live trading on the current evidence.

## 2. Why the first three strategies underperformed (evidence from the reports)
| Strategy | Net profit | Costs paid | Gross profit before costs | Costs as share of gross | Win rate | Stop-outs |
|---|---|---|---|---|---|---|
| Momentum + ATR stops | Rs 241k | Rs 189k | ~Rs 430k | 44% | 37.7% | 291 of 682 |
| Donchian breakout | Rs 85k | Rs 211k | ~Rs 296k | 71% | 35.8% | 492 of 924 |
| RSI(2) pullback | Rs 10k | Rs 545k | ~Rs 555k | 98% | 59.2% | 0 |
Reading: each had a small positive gross edge that trading costs (STT 0.1% on each side, stamp duty, fees, slippage) consumed.
Momentum and breakout also lost roughly half their trades to stop-outs (whipsaw). Profit factors of 1.00-1.13 are statistically
indistinguishable from zero edge. These three runs **pre-date the cash-yield fix** (idle cash earned 0%); they must be re-run on
the corrected engine as benchmarks. Multi-factor runs: costs were only ~7% of gross profit, and cash interest supplied 17-23%
of total profit (Rs 401k-523k), i.e. a large part of the result is not stock selection.

## 3. Bias and leakage checklist
| Item | Status | Direction of bias | Action |
|---|---|---|---|
| Look-ahead in indicators/strategies/factors/events | Verified causal by truncation tests (strict, includes a deliberate "cheater" the test must catch) | - | keep tests |
| Look-ahead: `bfill` on benchmark in `data.py` | **BUG FOUND AND FIXED** (back-filled early dates with future values) + regression test | flattered regime/beta features slightly | fixed this phase |
| Forward `shift(-)` elsewhere | Intentional evaluation targets, or ridge training guarded to realised returns only | - | none |
| Survivorship: universe = TODAY's Nifty 50 | **Present, high severity.** Removed constituents are absent | flatters returns, esp. momentum/winners | point-in-time universe (Phase 2) |
| Data quality: Yahoo corporate actions, demergers/mergers, volume split-adjustment | **Unverified** | unknown, could create fake returns | data-audit module (Phase 2) |
| Benchmark | Price-only index (~1.3%/yr dividends missing) in backtests; approximated in timing test | understates the benchmark | use Nifty 50 TRI from NSE |
| Cash yield | constant 6% for 2015-2026 (assumption) | likely overstates 2020-22, flatters cash-heavy/timed strategies | historical rate series |
| Taxes | **Not modelled** (average holding 70-88 days => mostly short-term gains) | flatters active strategies | tax scenarios (Phase 5) |
| Costs | STT, stamp, exchange, SEBI, GST, DP charges + flat 5 bps slippage; no brokerage (delivery is free) | slightly optimistic for slippage | verify against Zerodha calculator; use impact model |
| Liquidity | min 20-day ADV Rs 5 crore, order <= 5% ADV | fine at Rs 10 lakh scale | keep |
| Multiple testing | BH false-discovery control within the 36 lab tests; strategy variants and robustness grids are NOT in one global family | mild optimism | global test registry + deflated Sharpe |
| Researcher degrees of freedom | Many variants tried on the same 2015-2026 sample; **this sample is now "used up"** | biases toward false positives, so negative findings are conservative | new hold-out data needed (earlier history 2005-2015, forward paper trading) |
| Out-of-sample design | one block (last 30%, Jul 2023 onward, ~3 years, no crash) | weak evidence either way | walk-forward + multiple cycles |

## 4. The 36 signals: methodological review
Setup: 18 factors x 2 horizons (5, 21 days), 46 stocks, rank IC on non-overlapping windows, BH false-discovery control.
* **Power is low (verified by simulation).** With 46 stocks and ~138 independent monthly windows, SE(mean IC) = 0.0126, so the smallest IC
  detectable at |t|>3 is 0.038 with 50% power (0.048 with 80%). Planting a real IC of 0.022 (a respectable factor) was found in only 20% of
  simulated worlds at |t|>3; IC 0.036 in 57%; IC 0.049 in 73%. The 5-day horizon is ~2x more sensitive (580 windows).
  => The lab can only rule out large effects. Fix: larger point-in-time universe (SE shrinks with sqrt(stocks)), longer history, pooled tests.
* Quintiles of 46 stocks hold ~9 names each: noisy long-short and top-quintile numbers.
* Hypothesis directions were fixed in advance and not flipped afterwards (correct). Two of the four chosen multi-factor factors
  (low volatility IC -0.035, 52-week high IC -0.035) pointed the opposite way in this sample.
* Only `rev_5d` survived false-discovery control (IC 0.026, t 3.0) but turns over 79% per period and loses 6.5%/yr after costs.
* Event studies (sweeps, zones): overlapping windows and clustered events inflate t-values; none was significant after correction.
* Macro study: ~120 monthly observations, 4 variables: underpowered for anything but large effects.
* Cost model for quintile returns is a flat 0.25% round trip: acceptable, but not tied to the actual impact model.

## 5. Components to retain, revise or retire
| Component | Verdict |
|---|---|
| Backtest engine (accounting, next-open fills, gap-aware stops, cash yield) | **Retain** (unit-tested; metrics now tested against hand calculations) |
| Cost model, execution/impact model | **Retain**, re-verify rates periodically |
| Alpha lab (IC, FDR, event studies) | **Retain**, add power reporting and a global test registry |
| Random-picking null test, timing null test, block bootstrap | **Retain** (calibrated on noise and planted effects) |
| Risk gate and sizing | **Retain** for the paper-trading phase |
| Momentum / Donchian / RSI(2) strategies | **Retire as strategies, keep as benchmarks** |
| Binary trend/VIX filter | Keep as a test object (evidence so far negative); a proper regime engine does not exist yet |
| Universe, benchmark, cash-yield and tax assumptions | **Revise** (Phase 2 / Phase 5) |

## 6. Not yet built (so no claims can be made about them)
Point-in-time universe, data-quality audit, Nifty 50 TRI, sector data, fundamentals, ML models, regime engine, sector/volatility-target
portfolio constraints, walk-forward engine, tax scenarios, paper trading, dashboard.
