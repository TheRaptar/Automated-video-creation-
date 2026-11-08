"""Market data: Panel container, Yahoo/CSV loaders (free), and a synthetic generator for tests."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


@dataclass
class Panel:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    benchmark: pd.Series

    @property
    def dates(self):
        return self.close.index

    @property
    def symbols(self):
        return list(self.close.columns)

    def slice(self, start=None, end=None) -> "Panel":
        sl = slice(start, end)
        return Panel(*(getattr(self, c).loc[sl] for c in COLS), benchmark=self.benchmark.loc[sl])


def equal_weight_index(close: pd.DataFrame) -> pd.Series:
    return close.pct_change().mean(axis=1).fillna(0.0).add(1).cumprod() * 100


def build_panel(frames: dict, benchmark: pd.Series | None = None, min_rows: int = 260) -> Panel:
    frames = {s: f for s, f in frames.items() if f is not None and len(f) >= min_rows}
    if not frames:
        raise ValueError("No usable price history (need at least %d rows per symbol)." % min_rows)
    cols = {c: pd.concat({s: f[c] for s, f in frames.items()}, axis=1).sort_index() for c in COLS}
    idx = cols["close"].index
    keep = cols["close"].notna().any(axis=1)
    cols = {c: df.loc[keep].reindex(idx[keep]) for c, df in cols.items()}
    close = cols["close"]
    if benchmark is None or benchmark.dropna().empty:
        bench = equal_weight_index(close)
    else:
        bench = benchmark.reindex(close.index).ffill().bfill()
    return Panel(cols["open"], cols["high"], cols["low"], close, cols["volume"], bench)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[COLS].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated()].dropna(subset=["close"]).sort_index()


def load_csv_dir(path: str, symbols=None, benchmark_file: str | None = None) -> Panel:
    """Folder of SYMBOL.csv files with Date,Open,High,Low,Close,Volume (e.g. exported from Kite)."""
    frames = {}
    for f in sorted(Path(path).glob("*.csv")):
        if symbols and f.stem not in symbols:
            continue
        frames[f.stem] = _clean(pd.read_csv(f, index_col=0, parse_dates=True))
    bench = None
    if benchmark_file and Path(benchmark_file).exists():
        bench = _clean(pd.read_csv(benchmark_file, index_col=0, parse_dates=True))["close"]
    return build_panel(frames, bench)


def _safe(sym: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", sym)


def download_yahoo(symbols, start, end=None, cache_dir="data_cache", benchmark="^NSEI", pause=0.6) -> Panel:
    """Free historical data (adjusted for splits/dividends). Cached for a day."""
    import yfinance as yf
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(ticker: str):
        path = cache / f"{_safe(ticker)}.csv"
        if path.exists() and time.time() - path.stat().st_mtime < 86400:
            return _clean(pd.read_csv(path, index_col=0, parse_dates=True))
        for attempt in range(3):
            try:
                df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
                if not df.empty:
                    df = _clean(df)
                    df.to_csv(path)
                    return df
            except Exception as e:
                print(f"  {ticker}: attempt {attempt + 1} failed ({type(e).__name__})")
            time.sleep(2 * (attempt + 1))
        print(f"  WARNING: no data for {ticker} - skipped")
        return None

    frames = {}
    for s in symbols:
        frames[s] = fetch(f"{s}.NS")
        time.sleep(pause)
    bench = fetch(benchmark)
    return build_panel(frames, None if bench is None else bench["close"])


def synthetic_panel(n_symbols=30, years=8, seed=0) -> Panel:
    """Random but realistic-looking prices with a market factor and slowly drifting stock trends."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2016-01-01", periods=int(252 * years))
    n = len(dates)
    market = rng.normal(0.0004, 0.009, n)
    frames = {}
    for k in range(n_symbols):
        drift = np.zeros(n)
        d = rng.normal(0.0002, 0.0004)
        for t in range(n):                       # persistent (momentum-like) drift
            d = 0.985 * d + rng.normal(0, 0.00012)
            drift[t] = d
        r = drift + rng.uniform(0.6, 1.3) * market + rng.normal(0, 0.012, n)
        close = 100 * np.exp(np.cumsum(r))
        prev = np.r_[close[0], close[:-1]]
        open_ = prev * np.exp(rng.normal(0, 0.003, n))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
        vol = rng.lognormal(np.log(3e6), 0.3, n)    # ~Rs 30 crore a day: liquid
        frames[f"SYN{k:02d}"] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=dates)
    return build_panel(frames, None)
