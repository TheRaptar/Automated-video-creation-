# Zerodha trading bot - Phase 1: research & backtesting

Tests rules-based end-of-day strategies on liquid NSE stocks, with realistic Zerodha delivery costs
(STT, stamp duty, exchange fees, GST, DP charges), slippage, protective stops and an out-of-sample check.
**It places no orders and needs no Zerodha login.**

## Run it without installing anything
1. Put this `trading-bot/` folder in your repo root. Put `.github/workflows/backtest.yml` in the repo's root `.github/workflows/`.
2. Actions tab -> "Backtest strategy" -> Run workflow -> choose a strategy.
3. Open the run: the report is in the summary, and charts/CSVs are in the downloadable artifact.

Locally: `pip install -r requirements.txt && pytest -q && python run_backtest.py --strategy momentum --data yahoo --robust`

## Strategies (deliberately simple)
- `momentum` - hold the strongest stocks (6-month momentum), re-ranked monthly; goes to cash when the market is below its 200-day average.
- `donchian` - breakout above the 55-day high, exit below the 20-day low.
- `rsi2` - buy short-term dips in uptrends (trades a lot, so costs bite hard).

## How to read a report
Look at the **out-of-sample** column and the **Reality checks** section first, not the headline CAGR.
A strategy that only works in-sample, only for one parameter setting, or does not beat buy-and-hold after costs is not a strategy.

## Known limitations (read these)
- **Survivorship bias:** the stock list is today's large caps; stocks that fell out of the index are missing, which flatters results.
- Yahoo data is free but imperfect. For serious validation use Kite Connect historical data (Rs 500/month) exported to CSV (`--data csv:FOLDER`).
- No taxes in the numbers. No guarantee of future results.

## Next phases
2. Paper trading: a simulated broker on live data with the same strategy code.
3. Live with a tiny budget. Needs: an India-hosted server with a static IP registered in Kite Connect (required for API orders), a daily manual login (2FA), hard risk limits and a kill switch.
4. Scale only after months of profit after costs.
