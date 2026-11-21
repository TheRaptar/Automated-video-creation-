"""
Cash returns for idle money, replacing the old constant-6% assumption.
Priority: (1) Nifty 1D Rate Index (official overnight-lending total-return index)            -> VERIFIED
          (2) RBI repo rate history minus an overnight-fund cost allowance                  -> ESTIMATED
          (3) constant yield                                                                 -> ASSUMED
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# RBI policy repo rate (% p.a.), effective dates. Hand-compiled: the 2014-15, 2019-20 and 2025 entries were cross-checked
# against a published history during Phase 2; the others come from memory and MUST be treated as ESTIMATED.
REPO_HISTORY = [
    ("2010-01-01", 4.75), ("2010-03-19", 5.00), ("2010-04-20", 5.25), ("2010-07-02", 5.50), ("2010-07-27", 5.75),
    ("2010-09-16", 6.00), ("2010-11-02", 6.25), ("2011-01-25", 6.50), ("2011-03-17", 6.75), ("2011-05-03", 7.25),
    ("2011-06-16", 7.50), ("2011-07-26", 8.00), ("2011-09-16", 8.25), ("2011-10-25", 8.50), ("2012-04-17", 8.00),
    ("2013-01-29", 7.75), ("2013-03-19", 7.50), ("2013-05-03", 7.25), ("2013-09-20", 7.50), ("2013-10-29", 7.75),
    ("2014-01-28", 8.00), ("2015-01-15", 7.75), ("2015-03-04", 7.50), ("2015-06-02", 7.25), ("2015-09-29", 6.75),
    ("2016-04-05", 6.50), ("2016-10-04", 6.25), ("2017-08-02", 6.00), ("2018-06-06", 6.25), ("2018-08-01", 6.50),
    ("2019-02-07", 6.25), ("2019-04-04", 6.00), ("2019-06-06", 5.75), ("2019-08-07", 5.40), ("2019-10-04", 5.15),
    ("2020-03-27", 4.40), ("2020-05-22", 4.00), ("2022-05-04", 4.40), ("2022-06-08", 4.90), ("2022-08-05", 5.40),
    ("2022-09-30", 5.90), ("2022-12-07", 6.25), ("2023-02-08", 6.50), ("2025-02-07", 6.25), ("2025-04-09", 6.00),
    ("2025-06-06", 5.50), ("2025-12-05", 5.25),
]
OVERNIGHT_COST_ALLOWANCE = 0.40     # % p.a. below repo: overnight lending sits a little under repo, plus fund expenses


def repo_series(dates: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series({pd.Timestamp(d): r for d, r in REPO_HISTORY}).sort_index()
    return s.reindex(s.index.union(dates)).ffill().reindex(dates)


def daily_from_yield(annual_pct: pd.Series) -> pd.Series:
    """Annual yield in % -> daily return (252 trading days a year)."""
    return (1 + annual_pct / 100.0) ** (1 / 252) - 1


def returns_from_tri(tri: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    lvl = tri.reindex(tri.index.union(dates)).ffill().reindex(dates)
    return lvl.pct_change().fillna(0.0)


def load_cash_returns(dates: pd.DatetimeIndex, manifest=None, fetch_cash=None, constant: float = 0.06):
    """Returns (daily cash return Series aligned to `dates`, status string)."""
    if fetch_cash is not None:
        try:
            df, used = fetch_cash(dates[0] - pd.Timedelta(days=5), dates[-1])
        except Exception:
            df, used = pd.DataFrame(), None
        if df is not None and len(df) and df["gross_tri"].notna().sum() > 100:
            tri = df["gross_tri"].dropna()
            have = tri.index.intersection(dates)
            cover = len(have) / len(dates)
            ret = returns_from_tri(tri, dates)
            first_tri = tri.index[0]
            repo_fill = daily_from_yield(repo_series(dates) - OVERNIGHT_COST_ALLOWANCE)
            pre = dates < first_tri
            ret[pre] = repo_fill[pre]                       # before the index starts, fall back to the estimate
            status = "VERIFIED" if cover >= 0.97 and not pre.any() else "INCOMPLETE"
            if manifest is not None:
                manifest.add("cash returns (overnight rate)", status, f"NSE Indices '{used}' total-return index",
                             note=f"covers {cover:.0%} of trading days" + (f"; {int(pre.sum())} earlier days use the repo-rate estimate" if pre.any() else ""),
                             series=tri)
            return ret, status
    repo = repo_series(dates)
    if repo.notna().all():
        ret = daily_from_yield(repo - OVERNIGHT_COST_ALLOWANCE)
        if manifest is not None:
            manifest.add("cash returns (overnight rate)", "ESTIMATED", "RBI repo-rate history (hand-compiled) minus 0.40% allowance",
                         note="the official overnight-rate index could not be downloaded", series=repo)
        return ret, "ESTIMATED"
    ret = pd.Series((1 + constant) ** (1 / 252) - 1, index=dates)
    if manifest is not None:
        manifest.add("cash returns (overnight rate)", "ASSUMED", f"constant {constant:.1%}", note="no rate data available")
    return ret, "ASSUMED"
