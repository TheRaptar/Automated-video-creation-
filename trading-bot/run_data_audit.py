#!/usr/bin/env python3
"""
Audit historical price data for an index universe (free Yahoo data) and write a plain report + a machine-readable exclusion list.
  python run_data_audit.py --index nifty50 --years 16
  python run_data_audit.py --index nifty500 --years 16 --splits
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algo import nse
from algo.audit import audit_frames, write_audit_report
from algo.data import download_frames
from algo.loader import read_universe
from algo.provenance import Manifest


def get_symbols(index, manifest, universe_file):
    df, url = nse.fetch_constituents(index)
    if len(df) and "Symbol" in df.columns:
        manifest.add(f"universe: current {index} list", "VERIFIED", url or "NSE", note="official list as of today (NOT point-in-time)")
        return [s.strip().upper() for s in df["Symbol"]]
    if index == "nifty50":
        manifest.add("universe: current nifty50 list", "ESTIMATED", universe_file, note="hand-maintained file; official list could not be downloaded")
        return read_universe(universe_file)
    manifest.add(f"universe: current {index} list", "UNAVAILABLE", "NSE", note="download failed; cannot audit this universe")
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="nifty50", choices=["nifty50", "nifty200", "nifty500"])
    ap.add_argument("--universe-file", default="universe_nifty50.txt")
    ap.add_argument("--years", type=float, default=16)
    ap.add_argument("--splits", action="store_true", help="also fetch recorded splits to detect unadjusted ones (slower)")
    ap.add_argument("--max-symbols", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or f"reports/data_audit/{a.index}")
    manifest = Manifest()
    symbols = get_symbols(a.index, manifest, a.universe_file)
    if a.max_symbols:
        symbols = symbols[:a.max_symbols]
    if not symbols:
        raise SystemExit("No symbols to audit.")
    start = (date.today() - timedelta(days=int(a.years * 365.25))).isoformat()
    print(f"Downloading {len(symbols)} symbols from {start} (cached for a day)...")
    frames, bench = download_frames(symbols, start)
    missing = [s for s in symbols if s not in frames]
    manifest.add("benchmark price index (^NSEI, Yahoo)", "UNCONFIRMED" if bench is not None else "UNAVAILABLE", "Yahoo Finance", series=None if bench is None else bench["close"])
    splits = {}
    if a.splits:
        import yfinance as yf
        for s in frames:
            try:
                sp = yf.Ticker(s + ".NS").splits
                if len(sp):
                    sp.index = pd.to_datetime(sp.index).tz_localize(None)
                    splits[s] = sp
            except Exception:
                pass
    overrides = json.loads(Path("data/audit_overrides.json").read_text()) if Path("data/audit_overrides.json").exists() else {}
    issues, scores, summary = audit_frames(frames, splits, None if bench is None else bench["close"], overrides)
    clean_share = summary["clean"] / max(1, summary["symbols"])
    cov = len(frames) / max(1, len(symbols))
    status = "UNCONFIRMED" if clean_share >= 0.95 and cov >= 0.95 else "INCOMPLETE"
    manifest.add(f"daily prices {a.index} (Yahoo, adjusted)", status, "Yahoo Finance via yfinance",
                 note=f"{len(frames)} of {len(symbols)} symbols downloaded ({cov:.0%}); {clean_share:.0%} passed every automated check; not reconciled with NSE",
                 series=None, symbols_missing=missing[:50])
    manifest.add("price history of delisted / merged stocks", "UNAVAILABLE",
                 "none free", note=f"{len(missing)} current-list symbols had no Yahoo history; stocks that left the index and no longer trade are not in any current list")
    out.mkdir(parents=True, exist_ok=True)
    write_audit_report(out, issues, scores, summary, manifest, title=f"Historical data audit: {a.index}")
    (out / "missing_symbols.txt").write_text("\n".join(missing), encoding="utf-8")
    excl = scores[scores["class"] == "EXCLUDE"].symbol.tolist()
    Path("data").mkdir(exist_ok=True)
    Path(f"data/audit_exclusions_{a.index}.json").write_text(json.dumps({"index": a.index, "date": str(date.today()), "exclude": excl}, indent=2))
    manifest.save(out / "manifest.json")
    print(f"{summary['clean']} clean / {summary['review']} review / {summary['exclude']} exclude of {summary['symbols']}; {len(missing)} had no data. Report: {out}/summary.md")


if __name__ == "__main__":
    main()
