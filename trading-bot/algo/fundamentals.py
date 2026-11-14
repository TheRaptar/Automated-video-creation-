"""
Bring-your-own fundamentals WITHOUT look-ahead bias.
CSV columns: date, symbol, <metric>, <metric>, ...   where `date` is the fiscal PERIOD END.
Results are only published weeks later, so each value is made usable `lag_days` after its period end (default 60).
Using fundamentals without such a lag is the most common way backtests fool themselves.
"""
import pandas as pd

from .data import Panel


def load_fundamental_factors(csv_path: str, panel: Panel, lag_days: int = 60) -> dict[str, pd.DataFrame]:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    out = {}
    for metric in [c for c in df.columns if c not in ("date", "symbol")]:
        wide = df.pivot_table(index="date", columns="symbol", values=metric)
        wide.index = wide.index + pd.Timedelta(days=lag_days)
        full = wide.reindex(panel.dates.union(wide.index)).ffill().reindex(panel.dates)
        out[f"fund_{metric}"] = full.reindex(columns=panel.symbols)
    return out
