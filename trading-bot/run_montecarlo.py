#!/usr/bin/env python3
"""
Does the multi-factor strategy beat RANDOM stock picking with the same timing, turnover and costs?
(Idea adapted from the Time Machine skill: replay many alternative histories, fixed seed, plain verdict.)

  python run_montecarlo.py --data yahoo --macro --set regime=macro --null-runs 300
  python run_montecarlo.py --data synthetic --null-runs 50          # dry run
"""
import argparse

from algo.engine import Config
from algo.loader import load_panel
from algo.montecarlo import null_test, null_verdict
from algo.montecarlo_report import write_mc_report
from run_backtest import build_strategy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="multifactor settings, e.g. regime=macro top_n=15")
    ap.add_argument("--data", default="synthetic")
    ap.add_argument("--universe", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=10)
    ap.add_argument("--macro", action="store_true")
    ap.add_argument("--null-runs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--cash-yield", type=float, default=0.06)
    ap.add_argument("--capital", type=float, default=1_000_000)
    ap.add_argument("--out", default="reports/montecarlo")
    a = ap.parse_args()

    panel, label = load_panel(a.data, a.universe, a.years, macro=a.macro)
    span_years = (panel.dates[-1] - panel.dates[0]).days / 365.25
    if len(panel.symbols) < 20 or span_years < 3:    # like the Time Machine: refuse rather than mislead
        raise SystemExit(f"Refusing: need >= 20 stocks and >= 3 years of history (have {len(panel.symbols)} stocks, {span_years:.1f} years).")
    ref = build_strategy("multifactor", a.set)
    cfg = Config(capital=a.capital, max_positions=ref.top_n, cash_yield=a.cash_yield)
    print(f"Panel: {len(panel.symbols)} stocks, {panel.dates[0].date()} -> {panel.dates[-1].date()}; running {a.null_runs} random-picking replays (seed {a.seed})...")
    res = null_test(panel, ref, cfg, n=a.null_runs, seed=a.seed)
    boot = write_mc_report(a.out, panel, res, ref, cfg, label)
    print(f"\nStrategy Sharpe {res['real']['sharpe']:.2f} | random picking median {res['null'].sharpe.median():.2f} | "
          f"same-timing control {res['control']['sharpe']:.2f} | p = {res['p_sharpe']:.3f}")
    print(null_verdict(res["p_sharpe"]))
    print(f"Report: {a.out}/summary.md")


if __name__ == "__main__":
    main()
