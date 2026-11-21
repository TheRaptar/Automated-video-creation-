#!/usr/bin/env python3
"""
Discovery: for every free data source Phase 2 depends on, try it for real and record exactly what comes back
(status, columns, coverage, first rows) plus the raw files. Nothing here is assumed: if a source fails, that is the finding.
Run it from GitHub Actions (cloud servers may be blocked by some sites - that is also a finding).
"""
import io
import json
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algo import nse
from algo.universe import index_key_from_filename, parse_monthly_zip

OUT = Path("reports/discovery")
RAW = OUT / "raw"
results = []


def rec(name, ok, detail, **extra):
    results.append({"source": name, "ok": bool(ok), "detail": detail, **extra})
    print(("OK    " if ok else "FAIL  ") + name + " - " + detail)


def preview(df, n=4):
    return df.head(n).to_string(max_colwidth=30)[:900]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    sess = nse.make_session()
    end, start = date.today(), date.today() - timedelta(days=150)

    for nm in ("NIFTY 50", "NIFTY 200", "NIFTY 500"):
        df = nse.fetch_tri(nm, start, end, sess)
        rec(f"Total return index: {nm}", not df.empty,
            f"{len(df)} rows {df.index.min().date() if len(df) else ''} to {df.index.max().date() if len(df) else ''}; columns {list(df.columns)}" if len(df) else "no data returned (blocked, wrong name or changed API)",
            preview=preview(df) if len(df) else "")
    long_start = date(2011, 1, 1)
    df, used = nse.fetch_cash_index(long_start, end, sess)
    rec("Overnight-rate index (cash proxy)", not df.empty,
        f"name accepted: '{used}'; {len(df)} rows from {df.index.min().date()} to {df.index.max().date()}" if len(df) else f"none of the names {nse.CASH_INDEX_NAMES} returned data",
        preview=preview(df) if len(df) else "")
    dy = nse.fetch_dividend_yield("NIFTY 50", date(2012, 1, 1), end, sess)
    rec("Nifty 50 dividend yield history", len(dy) > 0, f"{len(dy)} rows {dy.index.min().date() if len(dy) else ''} to {dy.index.max().date() if len(dy) else ''}")

    for key in ("nifty50", "nifty200", "nifty500"):
        df, url = nse.fetch_constituents(key, sess)
        rec(f"Current constituents: {key}", not df.empty, f"{len(df)} rows from {url}; columns {list(df.columns)}" if len(df) else "download failed")
        if len(df):
            df.to_csv(RAW / f"constituents_{key}.csv", index=False)

    probes = [(2013, 4), (2016, 3), (2019, 3), (2022, 3), (2022, 4), (2024, 3)]
    pats = ["https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/indices_data{Mon}{Y}.zip",
            "https://archives.nseindia.com/content/indices/mcwb_{mon}{yy}.zip"]
    for y, m in probes:
        mon = date(y, m, 1).strftime("%b")
        got = False
        for pat in pats:
            url = pat.format(Mon=mon, mon=mon.lower(), Y=y, yy=str(y)[2:])
            content, status = nse.fetch_bytes(url, sess)
            if content:
                fn = RAW / f"archive_{y}_{m:02d}.zip"
                fn.write_bytes(content)
                try:
                    found, unmatched = parse_monthly_zip(content)
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        names = z.namelist()
                    rec(f"Monthly index archive {mon} {y}", True, f"{url}: {len(content):,} bytes, {len(names)} files; parsed {{{', '.join(f'{k}: {len(v)} symbols' for k, v in found.items())}}}; unmatched: {unmatched[:12]}", files=names[:40])
                except Exception as e:
                    rec(f"Monthly index archive {mon} {y}", False, f"{url}: downloaded {len(content):,} bytes but could not parse ({type(e).__name__}: {e})")
                got = True
                break
        if not got:
            rec(f"Monthly index archive {mon} {y}", False, "not downloadable from any candidate URL (HTTP status/error: " + ", ".join(str(nse.fetch_bytes(p.format(Mon=mon, mon=mon.lower(), Y=y, yy=str(y)[2:]), sess)[1]) for p in pats) + ")")
        time.sleep(1)

    content, status = nse.fetch_bytes("https://archives.nseindia.com/content/indices/IndexInclExcl.xls", sess)
    if content:
        (RAW / "IndexInclExcl.xls").write_bytes(content)
        try:
            xl = pd.read_excel(io.BytesIO(content), sheet_name=None)
            for sn, sdf in xl.items():
                rec(f"Inclusion/exclusion log, sheet '{sn}'", True, f"{sdf.shape[0]} rows, columns {list(sdf.columns)[:10]}", preview=preview(sdf, 6))
        except Exception as e:
            rec("Inclusion/exclusion log", False, f"downloaded {len(content):,} bytes but could not read ({type(e).__name__}: {e}); install xlrd for .xls")
    else:
        rec("Inclusion/exclusion log", False, f"not downloadable (status {status})")

    try:
        import yfinance as yf
        names = ["HDFC", "YESBANK", "ZEEL", "VEDL", "IOC", "GAIL", "BHEL", "UPL", "RCOM", "DHFL", "LAKSHVILAS", "JPASSOCIAT",
                 "RELCAPITAL", "TATAMOTORS", "MINDTREE", "LTI", "IBULHSGFIN", "AMTEKAUTO"]
        have, lost = [], []
        for n in names:
            h = yf.Ticker(n + ".NS").history(period="max", auto_adjust=True)
            (have if len(h) else lost).append((n, len(h), str(h.index.max().date()) if len(h) else ""))
            time.sleep(0.5)
        rec("Yahoo: history for delisted / merged / renamed / demerged names", len(have) > 0,
            f"{len(have)} of {len(names)} have history. With data (rows, last date): {have}. Without: {[n for n, _, _ in lost]}")
    except Exception as e:
        rec("Yahoo delisted-name probe", False, f"{type(e).__name__}: {e}")

    (OUT / "discovery.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    md = ["# Data discovery report", "", "Each row is a real attempt to fetch a free data source. FAIL means the source could not be used as-is.", "",
          "| Source | Result | Detail |", "|---|---|---|"]
    md += [f"| {r['source']} | {'OK' if r['ok'] else '**FAIL**'} | {str(r['detail']).replace('|', '/')[:600]} |" for r in results]
    md += ["", "## Previews", ""]
    for r in results:
        if r.get("preview"):
            md += [f"**{r['source']}**", "```", r["preview"], "```"]
    (OUT / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n{sum(r['ok'] for r in results)} of {len(results)} sources worked. Report: {OUT}/summary.md")


if __name__ == "__main__":
    main()
