# Phase 2: data foundations (free data only)

Mode: RESEARCH and PAPER only. No broker code exists in this project; `tests/test_no_live_trading.py` fails if any is added.
The eight acceptance gates in `RESEARCH_CHARTER.md` are unchanged. No strategy may be called an edge unless all eight pass.

## Run order (GitHub -> Actions; put every file from trading-bot/.github/workflows/ into the repo ROOT .github/workflows/)
1. **Phase 2: data discovery**: tries every free source and reports what really comes back. Send me `summary.md`.
2. **Phase 2: historical data audit** (nifty50 first, then nifty200 / nifty500): flags unadjusted splits, gaps, impossible prices, stale quotes, series that end early.
3. **Phase 2: build point-in-time index membership** (nifty500 / nifty200 / nifty50): official monthly archives, Apr 2013 - Mar 2022.
4. **Phase 2: re-run all strategies**: runs the three jobs above internally, then Momentum, Breakout, RSI(2) and Multi-factor on corrected foundations; writes `PHASE2_SUMMARY.md` per universe.

## What is built (all unit-tested with fake servers and injected defects)
| Item | Module | Status of the real data |
|---|---|---|
| Data audit | `audit.py`, `run_data_audit.py` | runs on Yahoo data; **not yet run on real data** |
| Nifty TRI benchmark | `nse.py`, `benchmark.py` | official source exists; **API access from cloud servers unverified** |
| Cash returns (overnight-rate index; fallback repo-rate estimate; last-resort constant) | `rates.py` | official index exists since 2011; **download unverified** |
| Point-in-time membership + coverage + survivor share | `universe.py`, `run_build_membership.py` | official archives documented for Apr 2013 - Mar 2022; **file formats unverified** |
| Data provenance labels | `provenance.py` | every report prints VERIFIED / UNCONFIRMED / ESTIMATED / ASSUMED / INCOMPLETE / UNAVAILABLE |
| Acceptance gates as code | `acceptance.py` | all 8 gates; 2, 4, 6(sector part) and 8 cannot pass yet |
| Strategy re-runs | `phase2.py`, `run_phase2.py` | cash-return series, TRI benchmark, 2% liquidity cap, point-in-time masks |

## Known limits that no free source fixes
* Delisted/merged stocks: not in any current list and mostly absent from Yahoo -> survivorship bias is reduced, never removed.
* Index membership after Mar 2022 for Nifty 200/500: no free official snapshots found; the test period ends where membership becomes unknown.
* Prices are not reconciled with the exchange (label UNCONFIRMED). Fundamentals, sector data and taxes are not yet available.
