#!/usr/bin/env python3
"""
Build point-in-time membership for an index from the OFFICIAL monthly archives (best effort; formats verified by discovery).
Rule against look-ahead: the file for month M is applied from the FIRST DAY OF MONTH M+1. Membership is declared valid only
until the end of the month after the last archive found; after that it is UNKNOWN (nobody is eligible), never carried forward.
Output: data/membership_<index>.csv and reports/membership_<index>/summary.md (coverage, size checks, unmatched files).
"""
import argparse
import time
from datetime import date
from pathlib import Path

import pandas as pd

from algo import nse
from algo.universe import EXPECTED_SIZE, Membership, parse_monthly_zip, save_membership_csv

PATS = ["https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/indices_data{Mon}{Y}.zip",
        "https://archives.nseindia.com/content/indices/mcwb_{mon}{yy}.zip"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="nifty500", choices=["nifty50", "nifty200", "nifty500"])
    ap.add_argument("--from", dest="first", default="2013-04")
    ap.add_argument("--to", dest="last", default="2022-03")
    a = ap.parse_args()
    sess = nse.make_session()
    months = pd.period_range(a.first, a.last, freq="M")
    snaps, missing, unmatched_all = {}, [], set()
    for p in months:
        mon = p.to_timestamp().strftime("%b")
        content = None
        for pat in PATS:
            content, _ = nse.fetch_bytes(pat.format(Mon=mon, mon=mon.lower(), Y=p.year, yy=str(p.year)[2:]), sess)
            if content:
                break
        if not content:
            missing.append(str(p)); continue
        try:
            found, unmatched = parse_monthly_zip(content)
            unmatched_all.update(unmatched)
            if a.index in found:
                snaps[(p + 1).to_timestamp()] = found[a.index]       # applies from the first day of the NEXT month
            else:
                missing.append(f"{p} (index file not matched)")
        except Exception:
            missing.append(f"{p} (unreadable)")
        time.sleep(0.4)
    out = Path(f"reports/membership_{a.index}")
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# Membership build: {a.index}", "", f"Months requested: {len(months)}; snapshots obtained: {len(snaps)}; missing/unusable: {len(missing)}.", ""]
    if not snaps:
        md += ["**No snapshots could be built.** Point-in-time membership is UNAVAILABLE from these sources; research on this index must be labelled survivorship-biased.",
               "", "Missing: " + ", ".join(missing[:60])]
        (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
        print("no snapshots built"); return
    m = Membership(a.index, [(d, frozenset(s), "SNAPSHOT") for d, s in sorted(snaps.items())])
    m.valid_until = (max(snaps) + pd.offsets.MonthEnd(1))
    Path("data").mkdir(exist_ok=True)
    save_membership_csv(m, f"data/membership_{a.index}.csv")
    sc = m.size_check(tol=max(2, int(0.01 * EXPECTED_SIZE[a.index])))
    md += [f"Membership valid from {min(snaps).date()} to {m.valid_until.date()} (UNKNOWN afterwards).",
           f"Snapshots with the expected size (+/-{max(2, int(0.01 * EXPECTED_SIZE[a.index]))} of {EXPECTED_SIZE[a.index]}): {int(sc['ok'].sum())} of {len(sc)}.", "",
           "Months missing or unusable: " + (", ".join(missing[:60]) or "none"), "",
           "Files in the archives that were not matched to nifty50/200/500 (check whether they matter): " + (", ".join(sorted(unmatched_all)[:40]) or "none"), "",
           "Size check (periods where the member count looks wrong):", ""]
    bad = sc[~sc["ok"]]
    md += ["none"] if bad.empty else ["| from | members | expected |", "|---|---|---|"] + [f"| {r.start.date()} | {r.size} | {r.expected} |" for r in bad.itertuples()]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:6]))


if __name__ == "__main__":
    main()
