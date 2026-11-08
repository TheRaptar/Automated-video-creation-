import numpy as np
import pandas as pd


def performance(equity: pd.Series, rf: float = 0.06) -> dict:
    """rf = annual risk-free rate used for Sharpe/Sortino (about 6% for Indian T-bills/liquid funds)."""
    eq = equity.dropna()
    ret = eq.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    vol = ret.std() * np.sqrt(252)
    down = ret[ret < 0].std() * np.sqrt(252)
    dd = eq / eq.cummax() - 1
    ex = ret.mean() * 252 - rf
    return {"total_return": eq.iloc[-1] / eq.iloc[0] - 1, "cagr": cagr, "volatility": vol,
            "sharpe": ex / vol if vol > 0 else np.nan, "sortino": ex / down if down > 0 else np.nan,
            "max_drawdown": dd.min(), "calmar": cagr / abs(dd.min()) if dd.min() < 0 else np.nan,
            "years": years}


def trade_stats(trades: pd.DataFrame) -> dict:
    if trades is None or trades.empty:
        return {"trades": 0}
    w, lo = trades[trades.net_pnl > 0], trades[trades.net_pnl <= 0]
    gl = abs(lo.net_pnl.sum())
    return {"trades": len(trades), "win_rate": len(w) / len(trades),
            "avg_win": w["return"].mean() if len(w) else 0.0, "avg_loss": lo["return"].mean() if len(lo) else 0.0,
            "profit_factor": w.net_pnl.sum() / gl if gl > 0 else np.inf,
            "avg_days_held": trades.days_held.mean(), "stop_exits": int((trades.reason == "stop").sum())}


def yearly_returns(equity: pd.Series) -> pd.Series:
    y = equity.resample("YE").last()
    first = equity.iloc[0]
    return pd.concat([pd.Series([first], index=[equity.index[0] - pd.Timedelta(days=1)]), y]).pct_change().dropna()
