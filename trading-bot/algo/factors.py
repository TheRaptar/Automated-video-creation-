"""
Factor library computed from daily OHLCV only (the data a retail trader can get for free).
Every factor is causal: the value on day t uses data up to the close of day t.
Sign convention: HIGHER = hypothesised better. The alpha lab then reports whether the data agrees.

"Institutional footprint" proxies (no order-book data needed): Chaikin money flow, OBV slope, up/down volume,
overnight-vs-intraday return split, rolling VWAP distance, volume surges, liquidity-sweep and supply/demand-zone events.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import Panel
from .indicators import atr, sma

FACTOR_INFO = {
    "mom_12_1": ("momentum", "12-month winners keep winning (skip the last month)"),
    "mom_6_1": ("momentum", "6-month winners keep winning (skip the last month)"),
    "high52": ("momentum", "stocks near their 52-week high keep rising"),
    "trend_200": ("momentum", "stocks well above their 200-day average keep rising"),
    "rev_5d": ("reversal", "last week's losers bounce"),
    "rev_21d": ("reversal", "last month's losers bounce"),
    "lowvol_60": ("risk", "low-volatility stocks earn more per unit of risk"),
    "lowbeta_252": ("risk", "low-beta stocks outperform (betting-against-beta)"),
    "lowidio_252": ("risk", "low idiosyncratic volatility outperforms"),
    "max_ret_21": ("risk", "avoid lottery stocks (big recent one-day jump)"),
    "amihud_60": ("liquidity", "illiquid stocks earn a premium"),
    "abn_volume": ("flow", "a volume surge signals new information / institutional interest"),
    "cmf_20": ("flow", "money flow: closes near the high on heavy volume = accumulation"),
    "obv_60": ("flow", "rising on-balance volume = accumulation"),
    "updown_vol_20": ("flow", "more volume on up days than down days = accumulation"),
    "overnight_20": ("flow", "overnight returns (institutional) beat intraday returns (retail)"),
    "intraday_20": ("flow", "strong intraday returns predict continuation"),
    "vwap_rev_20": ("microstructure", "price below its 20-day VWAP reverts upward"),
}


def compute_factors(p: Panel, names=None) -> dict[str, pd.DataFrame]:
    c, o, h, l, vol = p.close, p.open, p.high, p.low, p.volume
    ret = c.pct_change()
    bret = p.benchmark.pct_change()
    f: dict[str, pd.DataFrame] = {}
    f["mom_12_1"] = c.shift(21) / c.shift(252) - 1
    f["mom_6_1"] = c.shift(21) / c.shift(126) - 1
    f["high52"] = c / c.rolling(252, min_periods=252).max()
    f["trend_200"] = c / sma(c, 200) - 1
    f["rev_5d"] = -(c / c.shift(5) - 1)
    f["rev_21d"] = -(c / c.shift(21) - 1)
    f["lowvol_60"] = -ret.rolling(60, min_periods=60).std()
    cov = ret.rolling(252, min_periods=252).cov(bret)
    var_m = bret.rolling(252, min_periods=252).var()
    beta = cov.div(var_m, axis=0)
    f["lowbeta_252"] = -beta
    idio_var = (ret.rolling(252, min_periods=252).var() - beta.pow(2).mul(var_m, axis=0)).clip(lower=0)
    f["lowidio_252"] = -(idio_var ** 0.5)
    f["max_ret_21"] = -ret.rolling(21, min_periods=21).max()
    f["amihud_60"] = (ret.abs() / (c * vol)).rolling(60, min_periods=60).mean()
    f["abn_volume"] = np.log(vol.rolling(5, min_periods=5).mean() / vol.rolling(60, min_periods=60).mean())
    clv = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    f["cmf_20"] = (clv * vol).rolling(20, min_periods=20).sum() / vol.rolling(20, min_periods=20).sum()
    obv = (np.sign(c.diff()) * vol).fillna(0).cumsum()
    f["obv_60"] = (obv - obv.shift(60)) / vol.rolling(60, min_periods=60).sum()
    up = vol.where(c.diff() > 0, 0.0).rolling(20, min_periods=20).sum()
    dn = vol.where(c.diff() < 0, 0.0).rolling(20, min_periods=20).sum()
    f["updown_vol_20"] = np.log((up + 1) / (dn + 1))
    f["overnight_20"] = (o / c.shift(1) - 1).rolling(20, min_periods=20).sum()
    f["intraday_20"] = (c / o - 1).rolling(20, min_periods=20).sum()
    tp = (h + l + c) / 3
    vwap20 = (tp * vol).rolling(20, min_periods=20).sum() / vol.rolling(20, min_periods=20).sum()
    f["vwap_rev_20"] = -(c / vwap20 - 1)
    out = {k: v.replace([np.inf, -np.inf], np.nan) for k, v in f.items()}
    return {k: out[k] for k in names} if names else out


def zone_touches(p: Panel, left: int = 5, right: int = 5, max_age: int = 120, atr_n: int = 14):
    """
    Supply/demand zones from swing pivots (formalising the 'institutional imbalance' idea).
    A pivot low confirmed `right` days later creates a DEMAND zone (its low up to the base candle body);
    a pivot high creates a SUPPLY zone. A zone is broken if price closes through it, and consumed on its first touch.
    Returns two boolean tables: first touch of a demand zone, first touch of a supply zone. Fully causal.
    """
    H, L, O, C = (p.high.to_numpy(float), p.low.to_numpy(float), p.open.to_numpy(float), p.close.to_numpy(float))
    A = atr(p.high, p.low, p.close, atr_n).to_numpy(float)
    T, N = C.shape
    demand, supply = np.zeros((T, N), bool), np.zeros((T, N), bool)
    for j in range(N):
        dz, sz = [], []            # active zones: [low, high, born_t]
        for t in range(T):
            h_, l_, c_ = H[t, j], L[t, j], C[t, j]
            if not (np.isfinite(h_) and np.isfinite(l_) and np.isfinite(c_)):
                continue
            keep = []
            for z in dz:
                if c_ < z[0] or t - z[2] > max_age:
                    continue
                if l_ <= z[1]:
                    demand[t, j] = True
                    continue
                keep.append(z)
            dz = keep
            keep = []
            for z in sz:
                if c_ > z[1] or t - z[2] > max_age:
                    continue
                if h_ >= z[0]:
                    supply[t, j] = True
                    continue
                keep.append(z)
            sz = keep
            k = t - right                                  # pivot candidate, confirmed only now
            if k - left >= 0 and np.isfinite(A[t, j]):
                wl, wh = L[k - left:t + 1, j], H[k - left:t + 1, j]
                if np.isfinite(wl).all() and L[k, j] <= wl.min():
                    dz.append([L[k, j], max(min(O[k, j], C[k, j]), L[k, j] + 0.25 * A[t, j]), t])
                if np.isfinite(wh).all() and H[k, j] >= wh.max():
                    sz.append([min(max(O[k, j], C[k, j]), H[k, j] - 0.25 * A[t, j]), H[k, j], t])
    idx, cols = p.close.index, p.close.columns
    return pd.DataFrame(demand, index=idx, columns=cols), pd.DataFrame(supply, index=idx, columns=cols)


def event_signals(p: Panel, lookback: int = 20, vol_mult: float = 1.5) -> dict[str, pd.DataFrame]:
    """Discrete 'smart money' events. Liquidity sweep = price pokes through the recent extreme (taking the
    stops resting there) on heavy volume, then closes back inside - the classic stop-run pattern."""
    c, o, h, l, vol = p.close, p.open, p.high, p.low, p.volume
    low_prev = l.rolling(lookback, min_periods=lookback).min().shift(1)
    high_prev = h.rolling(lookback, min_periods=lookback).max().shift(1)
    heavy = vol > vol_mult * vol.rolling(20, min_periods=20).mean().shift(1)
    demand, supply = zone_touches(p)
    return {"sweep_bull": (l < low_prev) & (c > low_prev) & (c > o) & heavy,
            "sweep_bear": (h > high_prev) & (c < high_prev) & (c < o) & heavy,
            "demand_touch": demand, "supply_touch": supply}
