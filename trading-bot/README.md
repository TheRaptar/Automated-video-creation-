# Zerodha trading bot - research lab (Phase 1)

Tests rules-based and multi-factor end-of-day strategies on liquid NSE stocks with realistic Zerodha delivery costs,
slippage, idle-cash yield and an out-of-sample check. **It places no orders and needs no Zerodha login.**

**Start here:** `AUDIT.md` (Phase 1), `PHASE2.md` (data foundations and run order) and `RESEARCH_CHARTER.md` (acceptance criteria, unchanged).

## Run without installing anything (GitHub Actions)
Put `trading-bot/` in your repo root and both files from `trading-bot/.github/workflows/` into the repo's ROOT `.github/workflows/`.
1. **Alpha lab** - which signals carry any information? (factors, liquidity sweeps, supply/demand zones, macro variables)
2. **Monte Carlo test** - does the strategy beat random stock picking with identical timing and costs?
3. **Market-filter timing test** - is the trend / India VIX filter better than random timing on the index?
4. **Backtest strategy** - pick `multifactor`, `momentum`, `donchian` or `rsi2`; tick *macro* to use India VIX in the market filter.
Reports appear in the run summary; charts and CSVs are in the downloadable artifact.

Locally: `pip install -r requirements.txt && pytest -q && python run_alphalab.py --data yahoo --macro`

## What is inside
| Idea | What exists | Notes |
|---|---|---|
| Multi-factor models | `factors.py`, `multifactor.py` | 18 daily-data factors; equal-weight or walk-forward ridge; turnover buffer; hysteresis regime filter |
| Statistical testing | `alphalab.py` | rank IC, non-overlapping t-stats, in/out-of-sample, after-cost quintiles, false-discovery correction |
| Institutional-footprint proxies | `factors.py` | money flow, OBV, up/down volume, overnight-vs-intraday returns, VWAP distance, volume surges |
| Liquidity sweeps, supply/demand zones | `factors.py` event signals + event study | formalised from daily OHLC, causal |
| Macro top-down | `macro.py`, `macro_study` | India VIX, USDINR, Brent, US 10y |
| Fundamentals | `fundamentals.py` | bring a point-in-time CSV; reporting lag enforced |
| VWAP / TWAP / impact model | `execution.py`, `run_execution_demo.py` | cost-optimal slicing maths; sqrt-law impact usable in the backtest (`--slippage-model impact`) |

| Is it stock selection or just timing/cash? | `montecarlo.py`, `run_montecarlo.py` | random-picking null test (same timing, turnover, costs), same-timing control, block bootstrap error bars; idea from the Time Machine skill |
| Is the market filter skilful? | `timing.py`, `run_timing_test.py` | random on/off schedules with the same exposure and switches, on the index alone |
| Pre-trade risk checks (Phase 3) | `risk_gate.py` | PASS/BLOCK with reasons, risk-based sizing, kill switch; idea from trader-risk / trader-budget |

## Not possible with free retail data (deliberately not faked)
Iceberg/dark-pool detection (India has no dark pools; hidden size is invisible), tick-level order flow and sweeps
(needs level-2/3 history; start recording it in Phase 2), and HFT (latency, order-rate limits, static-IP rules).

## How to read results
Look at out-of-sample numbers, the *Reality checks* list and the equal-weight-universe column first. Known limits:
survivorship bias (today's large caps), imperfect Yahoo data, taxes excluded, index benchmark is price-only.
Not investment advice; no result guarantees future profit.

See `NOTICE.md` for credits.
