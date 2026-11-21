"""
Free official data from NSE Indices (niftyindices.com): total-return indices, the overnight-rate index, dividend
yields and constituent lists. UNVERIFIED against live servers when written (sandbox has no access): the discovery job
(run_data_discovery.py) records exactly what each request returns, and every caller labels the result accordingly.
The site is protected by Cloudflare and may refuse cloud servers; callers must handle failure.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE = "https://niftyindices.com"
SLEEP = 1.5        # seconds between retries (tests set it to 0)
TRI_PATH = "/Backpage.aspx/getTotalReturnIndexString"
PEPB_PATH = "/Backpage.aspx/getpepbHistoricaldataDBtoString"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": BASE,
    "Referer": BASE + "/reports/historical-data",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}
CASH_INDEX_NAMES = ["NIFTY 1D RATE INDEX", "Nifty 1D Rate Index", "NIFTY 1D RATE", "Nifty 1D Rate"]
LIST_URLS = {
    "nifty50": ["https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
                "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"],
    "nifty200": ["https://niftyindices.com/IndexConstituent/ind_nifty200list.csv",
                 "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"],
    "nifty500": ["https://niftyindices.com/IndexConstituent/ind_nifty500list.csv",
                 "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"],
}


def make_session():
    try:                                   # optional: gets past some Cloudflare checks
        import cloudscraper
        return cloudscraper.create_scraper()
    except Exception:
        return requests.Session()


def _fmt(d) -> str:
    return pd.Timestamp(d).strftime("%d-%b-%Y")


def _chunks(start, end, days: int = 330):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    while s <= e:
        c = min(s + pd.Timedelta(days=days), e)
        yield s, c
        s = c + pd.Timedelta(days=1)


def _post_rows(session, path: str, name: str, s, e, retries: int = 3) -> list:
    cinfo = {"name": name, "startDate": _fmt(s), "endDate": _fmt(e), "indexName": name}
    for attempt in range(retries):
        for body in ({"cinfo": json.dumps(cinfo)}, {"cinfo": str(cinfo)}):      # double-quoted JSON, then python-style
            try:
                r = session.post(BASE + path, json=body, headers=HEADERS, timeout=60)
                if getattr(r, "status_code", 200) == 200:
                    payload = r.json()
                    d = payload.get("d") if isinstance(payload, dict) else payload
                    rows = json.loads(d) if isinstance(d, str) else d
                    if rows:
                        return rows
            except Exception:
                pass
        time.sleep(SLEEP * (attempt + 1))
    return []


def _find(cols, *keys, avoid=()):
    for c in cols:
        lc = c.lower().replace(" ", "").replace("_", "")
        if all(k in lc for k in keys) and not any(a in lc for a in avoid):
            return c
    return None


def parse_rows(rows: list, value_keys: dict) -> pd.DataFrame:
    """value_keys: {output_name: (keywords..., )}. Date column located by name."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    dcol = _find(df.columns, "date")
    out = pd.DataFrame({"date": pd.to_datetime(df[dcol].astype(str).str.strip(), format="%d %b %Y", errors="coerce")})
    mask_bad = out["date"].isna()
    if mask_bad.any():
        out.loc[mask_bad, "date"] = pd.to_datetime(df.loc[mask_bad, dcol], errors="coerce", dayfirst=True)
    for name, spec in value_keys.items():
        keys, avoid = spec if isinstance(spec[0], tuple) else (spec, ())
        col = _find(df.columns, *keys, avoid=avoid)
        out[name] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce") if col else float("nan")
    return out.dropna(subset=["date"]).drop_duplicates("date").set_index("date").sort_index()


def fetch_tri(index_name: str, start, end, session=None) -> pd.DataFrame:
    """Gross and net total-return index levels. Columns: gross_tri, net_tri (net may be NaN)."""
    session = session or make_session()
    frames = []
    for s, e in _chunks(start, end):
        rows = _post_rows(session, TRI_PATH, index_name, s, e)
        if rows:
            frames.append(parse_rows(rows, {"gross_tri": (("total", "return"), ("net",)), "net_tri": ("net", "return")}))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index().loc[lambda d: ~d.index.duplicated()]


def fetch_dividend_yield(index_name: str, start, end, session=None) -> pd.Series:
    session = session or make_session()
    frames = []
    for s, e in _chunks(start, end, 1000):
        rows = _post_rows(session, PEPB_PATH, index_name, s, e)
        if rows:
            frames.append(parse_rows(rows, {"div_yield": ("div",)}))
    if not frames:
        return pd.Series(dtype=float)
    return pd.concat(frames).sort_index()["div_yield"].loc[lambda s: ~s.index.duplicated()]


def fetch_cash_index(start, end, session=None):
    """Nifty 1D Rate Index (overnight TREPS lending, a total-return index). Returns (frame, name_that_worked)."""
    session = session or make_session()
    for name in CASH_INDEX_NAMES:
        df = fetch_tri(name, start, end, session)
        if not df.empty and df["gross_tri"].notna().sum() > 100:
            return df, name
    return pd.DataFrame(), None


def fetch_constituents(key: str, session=None):
    """Current constituents (CSV with Company Name, Industry, Symbol, Series, ISIN Code). Returns (frame, url)."""
    session = session or requests.Session()
    for url in LIST_URLS[key]:
        try:
            r = session.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=60)
            if r.status_code == 200 and "Symbol" in r.text[:500]:
                from io import StringIO
                return pd.read_csv(StringIO(r.text)), url
        except Exception:
            continue
    return pd.DataFrame(), None


def fetch_bytes(url: str, session=None, timeout: int = 90):
    session = session or requests.Session()
    try:
        r = session.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=timeout)
        return (r.content if r.status_code == 200 else None), r.status_code
    except Exception as e:
        return None, type(e).__name__
