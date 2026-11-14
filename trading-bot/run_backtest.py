#!/usr/bin/env python3
"""
Backtest a strategy on NSE large caps (free Yahoo data, your own CSVs, or synthetic data for a dry run).

  python run_backtest.py --strategy multifactor --data yahoo --years 10 --robust
  python run_backtest.py --strategy multifactor --data yahoo --macro --set regime=macro model=ridge
  python run_backtest.py --strategy momentum --data csv:my_kite_exports
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


def build_strategy(name, sets):
    cls, kwargs = STRATEGIES[name], {}
    for kv in sets or []:
        k, v = kv.split("=", 1)
        default = cls.__dataclass_fields__[k].default
        kwargs[k] = (v.lower() in ("1", "true", "yes") if isinstance(default, bool) else int(v) if isinstance(default, int)
                     else float(v) if isinstance(default, float) else tuple(v.split(",")) if isinstance(default, tuple) else v)
    return cls(**kwargs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="multifactor")
    ap.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="strategy settings, e.g. top_n=20 model=ridge regime=macro")
    ap.add_argument("--data", default="synthetic", help="yahoo | synthetic | csv:FOLDER")
    ap.add_argument("--universe", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=10)
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--macro", action="store_true", help="download India VIX / USDINR / Brent / US10Y (for regime=macro)")
    ap.add_argument("--capital", type=float, default=1_000_000)
    ap.add_argument("--max-positions", type=int, default=None, help="default: the strategy's top_n, else 10")
    ap.add_argument("--slippage-bps", type=float, default=5)
    ap.add_argument("--slippage-model", choices=["flat", "impact"], default="flat")
    ap.add_argument("--cash-yield", type=float, default=0.06, help="annual yield on idle cash (liquid fund)")
    ap.add_argument("--no-stops", action="store_true")
    ap.add_argument("--rf", type=float, default=0.06)
    ap.add_argument("--oos-fraction", type=float, default=0.3)
    ap.add_argument("--robust", action="store_true", help="also run the parameter-robustness sweep (slower)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    start = a.start or (date.today() - timedelta(days=int(a.years * 365.25 + 400))).isoformat()   # + indicator warm-up
    if a.data == "yahoo":
        syms = read_universe(a.universe)
        print(f"Downloading {len(syms)} stocks from Yahoo (cached for a day)...")
        panel, label = download_yahoo(syms, start, a.end), "Yahoo Finance (adjusted)"
        if a.macro:
            from algo.macro import download_macro
            m = download_macro(start, a.end)
            panel.macro = None if m is None else m.reindex(panel.dates).ffill()
    elif a.data.startswith("csv:"):
        panel, label = load_csv_dir(a.data[4:]), f"CSV folder {a.data[4:]}"
    else:
        panel, label = synthetic_panel(30, a.years), "SYNTHETIC random data (dry run only - results are meaningless)"
    print(f"Panel: {len(panel.symbols)} stocks, {panel.dates[0].date()} -> {panel.dates[-1].date()}")

    strat = build_strategy(a.strategy, a.set)
    cfg = Config(capital=a.capital, max_positions=a.max_positions or int(strat.params().get("top_n", 10)),
                 slippage_bps=a.slippage_bps, slippage_model=a.slippage_model, cash_yield=a.cash_yield,
                 use_stops=not a.no_stops)
    cut = panel.dates[int(len(panel.dates) * (1 - a.oos_fraction))]
    res = run_backtest(panel, strat, cfg)
    robust_df = sweep(panel, a.strategy, cfg, cut, a.rf) if a.robust else None
    out = a.out or f"reports/{a.strategy}"
    full, bench, flags = write_report(out, res, panel, cut, a.rf, robust_df, label, len(panel.symbols))

    print(f"\n{a.strategy} {strat.params()}\n  CAGR {full['cagr']:.1%} | max drawdown {full['max_drawdown']:.1%} | Sharpe {full['sharpe']:.2f} "
          f"|| index CAGR {bench['cagr']:.1%} | trades {len(res.trades)} | costs Rs {res.total_costs:,.0f} | cash interest Rs {res.interest:,.0f}")
    for f in flags:
        print("  !", f)
    print(f"Report: {out}/summary.md")


if __name__ == "__main__":
    main()
