"""
Point-in-time index membership (the cure for survivorship bias) and tools to measure how much of it we really have.

Membership is stored as intervals: (start_date, frozenset(symbols)); a date belongs to the last interval starting on or before it.
Sources, best first:  official monthly snapshots  >  reconstruction backwards from today's list using an inclusion/exclusion log.
Parsers for the NSE files are UNVERIFIED against real files (sandbox cannot reach NSE): run_data_discovery.py reports what the
real files look like, and every membership object carries a status per interval so unknown periods are never silently filled.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MIN_DATE = pd.Timestamp("1900-01-01")
EXPECTED_SIZE = {"nifty50": 50, "nifty200": 200, "nifty500": 500}


def norm_symbol(s) -> str:
    return str(s).strip().upper()


def parse_constituent_csv(df: pd.DataFrame) -> set:
    col = next((c for c in df.columns if str(c).strip().lower() in ("symbol", "security symbol")), None)
    if col is None:
        raise ValueError(f"no Symbol column in {list(df.columns)}")
    return {norm_symbol(x) for x in df[col].dropna()}


def index_key_from_filename(name: str):
    stem = re.sub(r"[^a-z0-9]", "", name.lower().rsplit("/", 1)[-1].rsplit(".", 1)[0])
    m = re.match(r"^(?:ind)?(?:nifty|cnx)(50|200|500)(?:list)?$", stem)
    if m:
        return f"nifty{m.group(1)}"
    if re.match(r"^(?:ind)?cnxnifty(?:list)?$", stem):
        return "nifty50"
    return None


def parse_monthly_zip(content: bytes):
    """One monthly archive -> ({index_key: set(symbols)}, [file names that could not be matched]). UNVERIFIED format."""
    found, unmatched = {}, []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for n in z.namelist():
            if n.endswith("/"):
                continue
            key = index_key_from_filename(n)
            if key is None:
                unmatched.append(n)
                continue
            raw = z.read(n)
            try:
                df = pd.read_excel(io.BytesIO(raw)) if n.lower().endswith(("xls", "xlsx")) else pd.read_csv(io.BytesIO(raw))
                found[key] = parse_constituent_csv(df)
            except Exception:
                unmatched.append(n)
    return found, unmatched


def parse_incl_excl(df: pd.DataFrame, index_key: str | None = None) -> pd.DataFrame:
    """Defensive parser for an inclusion/exclusion log. Returns columns: date, symbol, action. UNVERIFIED format."""
    cols = {str(c).strip().lower(): c for c in df.columns}
    find = lambda *ks: next((cols[c] for c in cols if any(k in c for k in ks)), None)
    dcol, scol, acol = find("date", "effective"), find("symbol"), find("action", "inclusion/exclusion", "type")
    if not (dcol and scol and acol):
        raise ValueError(f"cannot find date/symbol/action columns in {list(df.columns)}")
    out = pd.DataFrame({"date": pd.to_datetime(df[dcol], errors="coerce", dayfirst=True), "symbol": df[scol].map(norm_symbol),
                        "action": df[acol].astype(str).str.upper().str.strip().map(
                            lambda a: "INCLUDE" if a.startswith("INCL") or a.startswith("ADD") else "EXCLUDE" if a.startswith("EXCL") or a.startswith("REM") or a.startswith("DEL") else None)})
    if index_key is not None and find("index") is not None:
        ic = find("index")
        key = re.sub(r"[^a-z0-9]", "", index_key.lower())
        out = out[df[ic].astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True).str.contains(key).to_numpy()]
    return out.dropna().sort_values("date").reset_index(drop=True)


@dataclass
class Membership:
    index: str
    intervals: list = field(default_factory=list)       # [(start Timestamp, frozenset, status)] ascending
    valid_until: pd.Timestamp | None = None             # membership is UNKNOWN after this date: nothing is eligible

    def members_on(self, date) -> frozenset:
        date, cur = pd.Timestamp(date), frozenset()
        for start, s, _ in self.intervals:
            if start <= date:
                cur = s
            else:
                break
        return cur

    def status_on(self, date) -> str:
        date, st = pd.Timestamp(date), "UNKNOWN"
        for start, _, status in self.intervals:
            if start <= date:
                st = status
        return st

    def mask(self, dates, symbols) -> pd.DataFrame:
        out = pd.DataFrame(False, index=dates, columns=list(symbols))
        for k, (start, s, _) in enumerate(self.intervals):
            end = self.intervals[k + 1][0] if k + 1 < len(self.intervals) else pd.Timestamp.max
            rows = (dates >= start) & (dates < end)
            if self.valid_until is not None:
                rows = rows & (dates <= self.valid_until)         # never carry stale membership forward
            cols = [c for c in out.columns if c in s]
            if rows.any() and cols:
                out.loc[rows, cols] = True
        return out

    def size_check(self, tol: int = 2) -> pd.DataFrame:
        exp = EXPECTED_SIZE.get(self.index)
        rows = [{"start": s, "size": len(m), "status": st, "expected": exp,
                 "ok": exp is None or abs(len(m) - exp) <= tol} for s, m, st in self.intervals]
        return pd.DataFrame(rows)

    def survivor_share(self, current: set) -> pd.DataFrame:
        """Share of each period's members that are still members today: how biased a 'current members' universe is."""
        return pd.DataFrame([{"start": s, "members": len(m), "still_members_today": len(m & current),
                              "share": len(m & current) / len(m) if m else np.nan} for s, m, _ in self.intervals])

    def coverage(self, price_symbols: set) -> pd.DataFrame:
        """For each period: how many members do we actually have prices for? Missing ones are delisted/renamed/not on the feed."""
        rows = []
        for s, m, st in self.intervals:
            have = m & price_symbols
            rows.append({"start": s, "members": len(m), "with_prices": len(have), "share": len(have) / len(m) if m else np.nan,
                         "status": st, "missing_examples": ", ".join(sorted(m - price_symbols)[:12])})
        return pd.DataFrame(rows)


def from_snapshots(index: str, snaps: dict) -> Membership:
    """snaps: {date: set(symbols)} (official monthly snapshots)."""
    return Membership(index, [(pd.Timestamp(d), frozenset(norm_symbol(x) for x in s), "SNAPSHOT") for d, s in sorted(snaps.items())])


def reconstruct_backwards(index: str, current: set, as_of, changes: pd.DataFrame) -> Membership:
    """Start from today's list and undo every logged inclusion/exclusion, newest first."""
    state = frozenset(norm_symbol(x) for x in current)
    ch = changes.sort_values("date")
    dates = sorted(ch["date"].unique())
    intervals = [(max(pd.Timestamp(as_of), dates[-1]) if len(dates) and False else (dates[-1] if len(dates) else MIN_DATE), state, "RECONSTRUCTED")]
    if not len(dates):
        return Membership(index, [(MIN_DATE, state, "SNAPSHOT")])
    for k in range(len(dates) - 1, -1, -1):
        sub = ch[ch["date"] == dates[k]]
        s = set(state)
        for r in sub.itertuples():
            if r.action == "INCLUDE":
                s.discard(r.symbol)
            else:
                s.add(r.symbol)
        state = frozenset(s)
        intervals.append((dates[k - 1] if k > 0 else MIN_DATE, state, "RECONSTRUCTED"))
    intervals.sort(key=lambda t: t[0])
    return Membership(index, intervals)


def save_membership_csv(m: Membership, path) -> None:
    """Long format, one row per (interval start, symbol); the last line of metadata goes in a sidecar-free header comment."""
    rows = [{"date": s.date(), "symbol": x, "status": st} for s, mem, st in m.intervals for x in sorted(mem)]
    pd.DataFrame(rows).to_csv(path, index=False)
    if m.valid_until is not None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"#valid_until,{m.valid_until.date()},\n")


def load_membership_csv(path, index: str) -> Membership:
    raw = open(path, encoding="utf-8").read().splitlines()
    valid = next((pd.Timestamp(l.split(",")[1]) for l in raw if l.startswith("#valid_until")), None)
    df = pd.read_csv(path, comment="#", parse_dates=["date"])
    ivs = [(d, frozenset(g["symbol"].map(norm_symbol)), g["status"].iloc[0]) for d, g in df.groupby("date")]
    return Membership(index, sorted(ivs, key=lambda t: t[0]), valid)
