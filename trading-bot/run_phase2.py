#!/usr/bin/env python3
"""
Phase 2 on real (free) data. Research and paper-trading mode only: this script never talks to a broker.

  python run_phase2.py --index nifty50
  python run_phase2.py --index nifty500 --null-runs 300 --no-sweep
Uses data/membership_<index>.csv (built by run_build_membership.py) when present; otherwise the universe is TODAY's
constituents and every report is labelled survivorship-biased.
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algo import nse
from algo.audit import audit_frames, write_audit_report
from algo.benchmark import load_benchmark_tr
from algo.data import build_panel, download_frames
from algo.loader import read_universe
from algo.phase2 import run_universe
from algo.provenance import Manifest
from algo.rates import load_cash_returns
from algo.universe import load_membership_csv

INDEX_NAMES = {"nifty50": "NIFTY 50", "nifty200": "NIFTY 200", "nifty500": "NIFTY 500"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="nifty50", choices=list(INDEX_NAMES))
    ap.add_argument("--universe-file", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=16)
    ap.add_argument("--null-runs", type=int, default=1000)
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("--keep-excluded", action="store_true", help="do not drop symbols the data audit says to exclude")
    ap.add_argument("--no-macro", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or f"reports/phase2/{a.index}")
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest()

    df, url = nse.fetch_constituents(a.index)
    if len(df) and "Symbol" in df.columns:
        current = {s.strip().upper() for s in df["Symbol"]}
        manifest.add(f"universe: current {a.index} list", "VERIFIED", url, note="official list as of today (not point-in-time)")
    elif a.index == "nifty50":
        current = set(read_universe(a.universe_file))
        manifest.add("universe: current nifty50 list", "ESTIMATED", a.universe_file, note="hand-maintained file; official list could not be downloaded")
    else:
        raise SystemExit(f"Cannot obtain the {a.index} constituent list: nothing to research.")

    mpath = Path(f"data/membership_{a.index}.csv")
    member = load_membership_csv(mpath, a.index) if mpath.exists() else None
    needed = set(current)
    if member:
        for _, s, _ in member.intervals:
            needed |= set(s)
    start = (date.today() - timedelta(days=int(a.years * 365.25 + 400))).isoformat()
    print(f"Downloading {len(needed)} symbols (cached for a day)...")
    frames, bench_df = download_frames(sorted(needed), start)
    if bench_df is None:
        raise SystemExit("Benchmark price index (^NSEI) unavailable.")
    bench_close = bench_df["close"]
    issues, scores, summary = audit_frames(frames, None, bench_close)
    write_audit_report(out / "data_audit", issues, scores, summary, manifest, title=f"Data audit: {a.index}")
    excl = set(scores[scores["class"] == "EXCLUDE"].symbol)
    if excl and not a.keep_excluded:
        frames = {k: v for k, v in frames.items() if k not in excl}
    clean_share = summary["clean"] / max(1, summary["symbols"])
    cov = len([s for s in current if s in frames]) / max(1, len(current))
    manifest.add(f"daily prices {a.index} (Yahoo, adjusted)", "UNCONFIRMED" if clean_share >= 0.95 and cov >= 0.95 else "INCOMPLETE", "Yahoo Finance via yfinance",
                 note=f"{len(frames)} symbols used; {len(excl)} excluded by the audit{'' if not a.keep_excluded else ' (kept by request)'}; {cov:.0%} of today's list available; {clean_share:.0%} clean; not reconciled with NSE")
    manifest.add("price history of delisted / merged stocks", "UNAVAILABLE", "none free", note="stocks that no longer trade are absent from Yahoo and from every current list")

    macro = None
    if not a.no_macro:
        from algo.macro import download_macro
        macro = download_macro(start)
        manifest.add("macro series (India VIX, USDINR, Brent, US10Y)", "UNCONFIRMED" if macro is not None else "UNAVAILABLE", "Yahoo Finance",
                     note="" if macro is not None else "download failed; the macro-filter variant is skipped")
    panel = build_panel(frames, bench_close, macro=macro)
    if panel.macro is not None:
        panel.macro = panel.macro.reindex(panel.dates).ffill()

    idx_name = INDEX_NAMES[a.index]
    tri, st = load_benchmark_tr(panel.benchmark.dropna(), idx_name, manifest, same_index=(a.index == "nifty50"))
    panel.benchmark_tr = tri.reindex(panel.dates).ffill()
    cash, cst = load_cash_returns(panel.dates, manifest, fetch_cash=nse.fetch_cash_index)

    if member:
        if member.valid_until is not None and member.valid_until < panel.dates[-1]:
            panel = panel.slice(end=member.valid_until)
            cash = cash.reindex(panel.dates)
        panel.members = member.mask(panel.dates, panel.symbols)
        cov_df = member.coverage(set(frames))
        cov_df.to_csv(out / "membership_coverage.csv", index=False)
        ss = member.survivor_share(current)
        manifest.add(f"point-in-time membership {a.index}", "UNCONFIRMED", "NSE monthly index archives (built by run_build_membership.py)",
                     note=f"valid {member.intervals[0][0].date()} to {member.valid_until.date() if member.valid_until is not None else 'n/a'}; unknown afterwards, so the test period ends there")
        extra = [f"Point-in-time membership from {member.intervals[0][0].date()} to {member.valid_until.date() if member.valid_until is not None else 'n/a'}; the evaluation period ends there.",
                 f"Average share of members for which we have prices: {cov_df['share'].mean():.0%} (lowest {cov_df['share'].min():.0%}). The missing ones are delisted, merged, renamed or absent from Yahoo, so survivorship bias is REDUCED but NOT removed.",
                 f"Share of the earliest period's members that are still members today: {ss.iloc[0]['share']:.0%}: a 'current members' universe would have missed the rest."]
        label = f"{a.index}, point-in-time membership (partial price coverage)"
    else:
        manifest.add(f"point-in-time membership {a.index}", "UNAVAILABLE", "none built", note="run_build_membership.py found no usable snapshots; the universe is today's list")
        extra = ["Universe = TODAY's constituents. Stocks that left the index (including delisted ones) are absent: results are SURVIVORSHIP-BIASED and flattering."]
        label = f"{a.index}, CURRENT constituents (survivorship-biased)"
    manifest.save(out / "manifest.json")
    rows = run_universe(panel, manifest, cash, out, label, null_runs=a.null_runs, do_sweep=not a.no_sweep, extra_md="\n\n".join(extra))
    print(f"\nSummary: {out}/PHASE2_SUMMARY.md")
    for r in rows:
        print(f"  {r['strategy']:20s} CAGR {r['cagr']:.1%} vs benchmark {r['bench_cagr']:.1%} | gates {r['passed']}/8 | {r['verdict']}")


if __name__ == "__main__":
    main()
