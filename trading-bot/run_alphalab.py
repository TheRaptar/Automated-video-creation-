#!/usr/bin/env python3
"""
Statistically test every signal idea on real NSE data and see which ones (if any) carry information.

  python run_alphalab.py --data yahoo --years 10 --macro
  python run_alphalab.py --data synthetic          # dry run
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

from algo.alphalab import event_study, macro_study
from algo.alphalab_report import run_lab
from algo.data import download_yahoo, load_csv_dir, synthetic_panel
from algo.factors import compute_factors, event_signals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="synthetic", help="yahoo | synthetic | csv:FOLDER")
    ap.add_argument("--universe", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=10)
    ap.add_argument("--horizons", default="5,21")
    ap.add_argument("--oos-fraction", type=float, default=0.3)
    ap.add_argument("--macro", action="store_true", help="also download India VIX / USDINR / Brent / US10Y")
    ap.add_argument("--fundamentals-csv", default=None, help="point-in-time CSV (see algo/fundamentals.py)")
    ap.add_argument("--out", default="reports/alphalab")
    a = ap.parse_args()

    start = (date.today() - timedelta(days=int(a.years * 365.25 + 400))).isoformat()
    if a.data == "yahoo":
        syms = [l.strip() for l in Path(a.universe).read_text().splitlines() if l.strip() and not l.startswith("#")]
        panel, label = download_yahoo(syms, start), "Yahoo Finance (adjusted)"
        if a.macro:
            from algo.macro import download_macro
            panel.macro = download_macro(start)
            if panel.macro is not None:
                panel.macro = panel.macro.reindex(panel.dates).ffill()
    elif a.data.startswith("csv:"):
        panel, label = load_csv_dir(a.data[4:]), f"CSV folder {a.data[4:]}"
    else:
        panel, label = synthetic_panel(30, a.years), "SYNTHETIC random data (dry run - nothing real can be found)"
    print(f"Panel: {len(panel.symbols)} stocks, {panel.dates[0].date()} -> {panel.dates[-1].date()}")

    factors = compute_factors(panel)
    if a.fundamentals_csv:
        from algo.fundamentals import load_fundamental_factors
        factors.update(load_fundamental_factors(a.fundamentals_csv, panel))
    horizons = [int(x) for x in a.horizons.split(",")]
    ev = event_study(panel, event_signals(panel))
    macro = macro_study(panel)
    tab = run_lab(panel, factors, horizons, a.oos_fraction, a.out, event_df=ev, macro_df=macro, label=label)
    cand = tab[tab.verdict == "CANDIDATE"]
    print(f"\n{len(cand)} candidate(s) out of {len(tab)} tests.")
    print(tab.head(8)[["factor", "h", "ic", "t", "ic_oos", "top_excess_net", "verdict"]].round(3).to_string(index=False))
    print(f"\nReport: {a.out}/summary.md")


if __name__ == "__main__":
    main()
