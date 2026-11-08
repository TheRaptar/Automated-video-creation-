"""
Simple, well-known, rules-based end-of-day strategies. Signals on day t use data up to the close of day t only;
the engine trades them at the NEXT open. Few parameters on purpose (fewer knobs = less overfitting).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .data import Panel
from .indicators import rsi, sma


@dataclass
class Signals:
    desired: pd.DataFrame   # bool: do we want to hold this stock after today's close?
    score: pd.DataFrame     # higher = preferred when there are more candidates than free slots


def month_end_flags(idx: pd.DatetimeIndex) -> np.ndarray:
    """True on the last trading day of each month (the final row is False: we cannot know)."""
    per = pd.Series(idx.to_period("M"), index=idx)
    nxt = per.shift(-1)
    return ((nxt != per) & nxt.notna()).to_numpy()


def _gate(df: pd.DataFrame, ok: pd.Series) -> pd.DataFrame:
    return df & ok.reindex(df.index).fillna(False).to_numpy()[:, None]


def regime_ok(p: Panel, n: int = 200) -> pd.Series:
    """Market filter: only be invested while the benchmark is above its n-day average."""
    return (p.benchmark > sma(p.benchmark, n)).fillna(False)


class Strategy:
    name = "base"
    stop_atr_mult: float | None = 3.0     # suggested protective stop (engine can override)
    trailing_stop = True

    def signals(self, p: Panel) -> Signals:
        raise NotImplementedError

    def params(self) -> dict:
        return asdict(self) if hasattr(self, "__dataclass_fields__") else {}


@dataclass
class TrendMomentum(Strategy):
    """Hold the strongest stocks (6-month momentum, skipping the last month) that are in an uptrend.
    Re-ranked on the last trading day of each month; market filter moves to cash in bear markets."""
    top_n: int = 10
    lookback: int = 126
    skip: int = 21
    ma: int = 200
    regime: bool = True
    name = "momentum"

    def signals(self, p):
        c = p.close
        mom = c.shift(self.skip) / c.shift(self.lookback) - 1
        ok = (c > sma(c, self.ma)) & (mom > 0)
        rank = mom.where(ok).rank(axis=1, ascending=False, method="first")
        sel = (rank <= self.top_n).astype(float)
        reb = pd.DataFrame(np.repeat(month_end_flags(c.index)[:, None], c.shape[1], axis=1),
                           index=c.index, columns=c.columns)
        desired = sel.where(reb).ffill().fillna(0.0) > 0.5
        if self.regime:
            desired = _gate(desired, regime_ok(p))
        return Signals(desired, mom)


@dataclass
class Donchian(Strategy):
    """Classic breakout: buy a close above the prior N-day high (in an uptrend), exit below the prior M-day low."""
    entry: int = 55
    exit_n: int = 20
    ma: int = 200
    regime: bool = True
    name = "donchian"

    def signals(self, p):
        c = p.close
        hi = p.high.rolling(self.entry, min_periods=self.entry).max().shift(1)
        lo = p.low.rolling(self.exit_n, min_periods=self.exit_n).min().shift(1)
        enter = (c > hi) & (c > sma(c, self.ma))
        leave = c < lo
        state = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
        state = state.mask(enter, 1.0).mask(leave, 0.0)      # exit wins if both ever happen
        desired = state.ffill().fillna(0.0) > 0.5
        if self.regime:
            desired = _gate(desired, regime_ok(p))
        return Signals(desired, c / c.shift(126) - 1)


@dataclass
class RSI2Pullback(Strategy):
    """Mean reversion: buy short-term dips (RSI(2) very low) in stocks that are above their 200-day average."""
    entry_thr: float = 10.0
    exit_thr: float = 65.0
    ma: int = 200
    rsi_n: int = 2
    regime: bool = True
    name = "rsi2"
    stop_atr_mult = None
    trailing_stop = False

    def signals(self, p):
        c = p.close
        r = rsi(c, self.rsi_n)
        trend = c > sma(c, self.ma)
        enter = trend & (r < self.entry_thr)
        leave = (r > self.exit_thr) | ~trend
        state = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
        state = state.mask(enter, 1.0).mask(leave, 0.0)
        desired = state.ffill().fillna(0.0) > 0.5
        if self.regime:
            desired = _gate(desired, regime_ok(p))
        return Signals(desired, -r)


STRATEGIES = {"momentum": TrendMomentum, "donchian": Donchian, "rsi2": RSI2Pullback}

# Small grids for the robustness check (does the idea work across settings, or only for one lucky setting?)
GRIDS = {
    "momentum": {"top_n": [5, 10, 15], "lookback": [63, 126, 189], "ma": [100, 200]},
    "donchian": {"entry": [20, 55, 100], "exit_n": [10, 20, 40]},
    "rsi2": {"entry_thr": [5, 10, 15], "exit_thr": [60, 70, 80]},
}
