"""Overfitting checks: pick settings using only the first part of history, then see how they do on the rest."""
import itertools

import numpy as np
import pandas as pd

from .engine import Config, run_backtest
from .metrics import performance
from .strategies import GRIDS, STRATEGIES


def split_perf(equity: pd.Series, cut, rf: float):
    is_eq, oos_eq = equity.loc[:cut], equity.loc[cut:]
    return performance(is_eq, rf), performance(oos_eq, rf)


def sweep(panel, name: str, cfg: Config, cut, rf: float = 0.06) -> pd.DataFrame:
    grid, rows = GRIDS[name], []
    for combo in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), combo))
        res = run_backtest(panel, STRATEGIES[name](**params), cfg)
        i, o = split_perf(res.equity, cut, rf)
        rows.append({**params, "is_cagr": i["cagr"], "is_sharpe": i["sharpe"], "is_maxdd": i["max_drawdown"],
                     "oos_cagr": o["cagr"], "oos_sharpe": o["sharpe"], "oos_maxdd": o["max_drawdown"],
                     "trades": len(res.trades)})
    return pd.DataFrame(rows)
