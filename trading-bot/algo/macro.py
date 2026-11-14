"""Macro series (free, via Yahoo) for regime filters: India VIX, USD/INR, Brent crude, US 10-year yield."""
import time
from pathlib import Path

import numpy as np
import pandas as pd

MACRO_TICKERS = {"vix": "^INDIAVIX", "usdinr": "INR=X", "brent": "BZ=F", "us10y": "^TNX"}


def download_macro(start, end=None, cache_dir="data_cache") -> pd.DataFrame | None:
    import yfinance as yf
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    cols = {}
    for name, ticker in MACRO_TICKERS.items():
        path = cache / f"macro_{name}.csv"
        s = None
        if path.exists() and time.time() - path.stat().st_mtime < 86400:
            s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
        else:
            for attempt in range(3):
                try:
                    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
                    if not df.empty:
                        s = df["Close"]
                        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
                        s.to_csv(path)
                        break
                except Exception:
                    pass
                time.sleep(2 * (attempt + 1))
        if s is not None:
            cols[name] = s[~s.index.duplicated()]
        else:
            print(f"  WARNING: macro series {name} ({ticker}) unavailable")
        time.sleep(0.5)
    return pd.DataFrame(cols).sort_index() if cols else None


def smooth_state(cond: pd.Series, on_days: int = 5, off_days: int = 3) -> pd.Series:
    """Hysteresis: switch ON only after `on_days` consecutive True days, OFF only after `off_days` consecutive False
    days. Stops a flickering filter from selling and re-buying the whole portfolio (and paying STT every time)."""
    c = cond.fillna(False).astype(float)
    turn_on = c.rolling(on_days, min_periods=on_days).min() == 1
    turn_off = (1 - c).rolling(off_days, min_periods=off_days).min() == 1
    state = pd.Series(np.nan, index=c.index).mask(turn_on, 1.0).mask(turn_off, 0.0)
    return state.ffill().fillna(0.0) > 0.5


def risk_on(macro: pd.DataFrame | None, benchmark: pd.Series, vix_quantile: float = 0.8) -> pd.Series:
    """True when the market trend is up AND India VIX is not in its own top quintile of the last year."""
    trend = (benchmark > benchmark.rolling(200, min_periods=200).mean()).fillna(False)
    if macro is None or "vix" not in macro:
        return smooth_state(trend)
    vix = macro["vix"].reindex(benchmark.index).ffill()
    calm = vix < vix.rolling(252, min_periods=126).quantile(vix_quantile)
    return smooth_state(trend & calm.fillna(False))
