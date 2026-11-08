#!/usr/bin/env python3
"""
Backtest a strategy on NSE large caps (free Yahoo data, your own CSVs, or synthetic data for a dry run).

  python run_backtest.py --strategy momentum --data yahoo --years 10 --robust
  python run_backtest.py --strategy donchian --data csv:my_kite_exports
  python run_backtest.py --strategy rsi2 --data synthetic
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

from algo.data import download_yahoo, load_csv_dir, synthetic_panel
from algo.engine import Config, run_backtest
from algo.report import write_report
from algo.robust import sweep
from algo.strategies import STRATEGIES


def read_universe(path):
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="momentum")
    ap.add_argument("--data", default="synthetic", help="yahoo | synthetic | csv:FOLDER")
    ap.add_argument("--universe", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=10)
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--capital", type=float, default=1_000_000)
    ap.add_argument("--max-positions", type=int, default=10)
    ap.add_argument("--slippage-bps", type=float, default=5)
    ap.add_argument("--no-stops", action="store_true")
    ap.add_argument("--rf", type=float, default=0.06, help="annual risk-free rate for Sharpe/Sortino")
    ap.add_argument("--oos-fraction", type=float, default=0.3, help="share of history held out as out-of-sample")
    ap.add_argument("--robust", action="store_true", help="also run the parameter-robustness sweep (slower)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    start = a.start or (date.today() - timedelta(days=int(a.years * 365.25 + 330))).isoformat()  # +warm-up
    if a.data == "yahoo":
        syms = read_universe(a.universe)
        print(f"Downloading {len(syms)} stocks from Yahoo (cached for a day)...")
        panel, label = download_yahoo(syms, start, a.end), "Yahoo Finance (adjusted)"
    elif a.data.startswith("csv:"):
        panel, label = load_csv_dir(a.data[4:]), f"CSV folder {a.data[4:]}"
    else:
        panel, label = synthetic_panel(30, a.years), "SYNTHETIC random data (dry run only - results are meaningless)"
    print(f"Panel: {len(panel.symbols)} stocks, {panel.dates[0].date()} -> {panel.dates[-1].date()}")

    cfg = Config(capital=a.capital, max_positions=a.max_positions, slippage_bps=a.slippage_bps, use_stops=not a.no_stops)
    cut = panel.dates[int(len(panel.dates) * (1 - a.oos_fraction))]
    res = run_backtest(panel, STRATEGIES[a.strategy](), cfg)
    robust_df = sweep(panel, a.strategy, cfg, cut, a.rf) if a.robust else None
    out = a.out or f"reports/{a.strategy}"
    full, bench, flags = write_report(out, res, panel, cut, a.rf, robust_df, label, len(panel.symbols))

    print(f"\n{a.strategy}: CAGR {full['cagr']:.1%} | max drawdown {full['max_drawdown']:.1%} | Sharpe {full['sharpe']:.2f} "
          f"|| benchmark CAGR {bench['cagr']:.1%} | trades {len(res.trades)} | costs Rs {res.total_costs:,.0f}")
    for f in flags:
        print("  !", f)
    print(f"Report: {out}/summary.md")


if __name__ == "__main__":
    main()
