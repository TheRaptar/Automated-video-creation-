"""Shared data loading for the command-line tools."""
from datetime import date, timedelta
from pathlib import Path

from .data import download_yahoo, load_csv_dir, synthetic_panel


def read_universe(path):
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def load_panel(data: str, universe: str, years: float, start=None, end=None, macro: bool = False):
    start = start or (date.today() - timedelta(days=int(years * 365.25 + 400))).isoformat()
    if data == "yahoo":
        panel, label = download_yahoo(read_universe(universe), start, end), "Yahoo Finance (adjusted)"
        if macro:
            from .macro import download_macro
            m = download_macro(start, end)
            panel.macro = None if m is None else m.reindex(panel.dates).ffill()
    elif data.startswith("csv:"):
        panel, label = load_csv_dir(data[4:]), f"CSV folder {data[4:]}"
    else:
        panel, label = synthetic_panel(30, years), "SYNTHETIC random data (dry run only - results are meaningless)"
    return panel, label


def load_benchmark(data: str, years: float, macro: bool = False):
    """Just the index (+ optional macro series): fast, no need to download every stock."""
    import pandas as pd
    start = (date.today() - timedelta(days=int(years * 365.25 + 400))).isoformat()
    if data == "yahoo":
        import yfinance as yf
        from .macro import download_macro
        df = yf.Ticker("^NSEI").history(start=start, auto_adjust=True)
        bench = df["Close"]
        bench.index = pd.to_datetime(bench.index).tz_localize(None).normalize()
        bench = bench[~bench.index.duplicated()]
        m = download_macro(start) if macro else None
        return bench, (None if m is None else m.reindex(bench.index).ffill()), "Yahoo Finance ^NSEI (price index)"
    p = synthetic_panel(30, years)
    return p.benchmark, p.macro, "SYNTHETIC data (dry run only - results are meaningless)"
