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
    macro: pd.DataFrame | None = None   # optional: vix, usdinr, brent, us10y
    benchmark_tr: pd.Series | None = None   # total-return index (dividends included), when available
    members: pd.DataFrame | None = None     # point-in-time membership mask (dates x symbols, bool), when available

    @property
    def dates(self):
        return self.close.index

    @property
    def symbols(self):
        return list(self.close.columns)

    def slice(self, start=None, end=None) -> "Panel":
        sl = slice(start, end)
        return Panel(*(getattr(self, c).loc[sl] for c in COLS), benchmark=self.benchmark.loc[sl],
                     macro=None if self.macro is None else self.macro.loc[sl],
                     benchmark_tr=None if self.benchmark_tr is None else self.benchmark_tr.loc[sl],
                     members=None if self.members is None else self.members.loc[sl])


def equal_weight_index(close: pd.DataFrame) -> pd.Series:
    return close.pct_change().mean(axis=1).fillna(0.0).add(1).cumprod() * 100


def build_panel(frames: dict, benchmark: pd.Series | None = None, min_rows: int = 260,
                macro: pd.DataFrame | None = None, benchmark_tr: pd.Series | None = None) -> Panel:
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
        bench = benchmark.reindex(close.index).ffill()      # no bfill: back-filling would copy FUTURE values into early dates
    if macro is not None:
        macro = macro.reindex(close.index).ffill()
    if benchmark_tr is not None:
        benchmark_tr = benchmark_tr.reindex(close.index).ffill()
    return Panel(cols["open"], cols["high"], cols["low"], close, cols["volume"], bench, macro, benchmark_tr)


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


def download_frames(symbols, start, end=None, cache_dir="data_cache", benchmark="^NSEI", pause=0.6):
    """Free historical data from Yahoo (adjusted for splits/dividends where Yahoo does so). Cached for a day.
    Returns ({symbol: OHLCV frame}, benchmark OHLCV frame or None). Symbols with no data are simply absent (and listed)."""
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
    for sym in symbols:
        df = fetch(f"{sym}.NS")
        if df is not None:
            frames[sym] = df
        time.sleep(pause)
    return frames, fetch(benchmark)


def download_yahoo(symbols, start, end=None, cache_dir="data_cache", benchmark="^NSEI", pause=0.6) -> Panel:
    frames, bench = download_frames(symbols, start, end, cache_dir, benchmark, pause)
    return build_panel(frames, None if bench is None else bench["close"])


def synthetic_panel(n_symbols=30, years=8, seed=0, persistent=True) -> Panel:
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
            drift[t] = d if persistent else 0.0002   # persistent=False -> pure noise, nothing to find
        r = drift + rng.uniform(0.6, 1.3) * market + rng.normal(0, 0.012, n)
        close = 100 * np.exp(np.cumsum(r))
        prev = np.r_[close[0], close[:-1]]
        open_ = prev * np.exp(rng.normal(0, 0.003, n))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
        vol = rng.lognormal(np.log(3e6), 0.3, n)    # ~Rs 30 crore a day: liquid
        frames[f"SYN{k:02d}"] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=dates)
    vix = pd.Series(16 + np.cumsum(rng.normal(0, 0.4, n)) * 0.2 + 3 * np.abs(market) * 100, index=dates).clip(9, 80)
    macro = pd.DataFrame({"vix": vix, "usdinr": 70 * np.exp(np.cumsum(rng.normal(0.0001, 0.003, n))),
                          "brent": 60 * np.exp(np.cumsum(rng.normal(0, 0.02, n))),
                          "us10y": 2 + np.cumsum(rng.normal(0, 0.03, n)) * 0.2}, index=dates)
    return build_panel(frames, None, macro=macro)
