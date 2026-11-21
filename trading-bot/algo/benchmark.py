"""Benchmark total-return series with explicit provenance: official TRI > estimate from dividend yield > assumed constant."""
from __future__ import annotations

import pandas as pd

from . import nse


def load_benchmark_tr(price: pd.Series, index_name: str, manifest=None, fetch_tri=None, fetch_dy=None, const_div: float = 0.013, same_index: bool = True):
    """Returns (TRI level aligned to the price dates, status). `price` is the price index used for the same dates."""
    fetch_tri = fetch_tri or nse.fetch_tri
    fetch_dy = fetch_dy or nse.fetch_dividend_yield
    dates = price.index
    label = f"{index_name} total return index"
    try:
        df = fetch_tri(index_name, dates[0] - pd.Timedelta(days=5), dates[-1])
    except Exception:
        df = pd.DataFrame()
    if df is not None and len(df) and df["gross_tri"].notna().sum() > 100:
        tri = df["gross_tri"].dropna()
        lvl = tri.reindex(dates.union(tri.index)).ffill().reindex(dates)
        cover = len(tri.index.intersection(dates)) / len(dates)
        corr = lvl.pct_change().corr(price.pct_change())
        years = (dates[-1] - dates[0]).days / 365.25
        uplift = ((lvl.iloc[-1] / lvl.iloc[0]) / (price.iloc[-1] / price.iloc[0])) ** (1 / years) - 1
        # same_index=False (e.g. Nifty 500 TRI vs the Nifty 50 price series): prices legitimately diverge, so only check coverage and correlation
        ok = cover >= 0.97 and ((corr >= 0.98 and 0.0 <= uplift <= 0.05) if same_index else corr >= 0.95)
        status = "VERIFIED" if ok else "INCOMPLETE"
        if manifest is not None:
            manifest.add(label, status, f"NSE Indices ({index_name} gross TRI)",
                         note=f"coverage {cover:.0%}; daily correlation with price index {corr:.3f}; implied dividend uplift {uplift:.2%}/yr",
                         series=tri)
        return lvl, status
    try:
        dy = fetch_dy(index_name, dates[0] - pd.Timedelta(days=5), dates[-1])
    except Exception:
        dy = pd.Series(dtype=float)
    if dy is not None and len(dy) > 100:
        dyd = dy.reindex(dates.union(dy.index)).ffill().reindex(dates)
        ret = price.pct_change().fillna(0.0) + dyd.fillna(const_div * 100) / 100 / 252
        lvl = price.iloc[0] * (1 + ret).cumprod()
        if manifest is not None:
            manifest.add(label, "ESTIMATED", f"price index + NSE dividend-yield history ({index_name})",
                         note="official TRI not downloadable; daily yield/252 added to the price return", series=dy)
        return lvl, "ESTIMATED"
    ret = price.pct_change().fillna(0.0) + const_div / 252
    lvl = price.iloc[0] * (1 + ret).cumprod()
    if manifest is not None:
        manifest.add(label, "ASSUMED", f"price index + constant {const_div:.1%} dividend yield", note="no TRI or dividend-yield data could be downloaded")
    return lvl, "ASSUMED"
