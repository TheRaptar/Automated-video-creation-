"""
Alpha lab: does a signal carry information about FUTURE returns - and does it survive costs and luck?

For each factor: rank information coefficient (IC = cross-sectional Spearman correlation between today's factor and the
forward return), measured on NON-overlapping windows so the t-statistic is honest; in-sample vs out-of-sample;
quintile spreads net of trading costs; and a Benjamini-Hochberg false-discovery correction, because testing 18 factors
x 2 horizons will "find" some by pure chance.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import Panel


def fwd_returns(p: Panel, h: int) -> pd.DataFrame:
    """Return from the NEXT open to h days later: what you could actually capture after seeing today's close."""
    return p.open.shift(-(h + 1)) / p.open.shift(-1) - 1


def rank_ic(f: pd.DataFrame, r: pd.DataFrame, min_names: int = 15) -> pd.Series:
    mask = f.notna() & r.notna()
    ic = f.where(mask).rank(axis=1).corrwith(r.where(mask).rank(axis=1), axis=1)
    return ic.where(mask.sum(axis=1) >= min_names)


def _stats(x: pd.Series) -> dict:
    x = x.dropna()
    n = len(x)
    if n < 8:
        return {"n": n, "mean": np.nan, "std": np.nan, "t": np.nan, "hit": np.nan}
    m, s = x.mean(), x.std()
    return {"n": n, "mean": m, "std": s, "t": m / (s / math.sqrt(n)) if s > 0 else np.nan, "hit": float((x > 0).mean())}


def norm_p(t: float) -> float:
    if not np.isfinite(t):
        return 1.0
    return 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))


def bh_fdr(pvals, alpha: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg: which discoveries survive when many hypotheses are tested at once."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    ok = p[order] <= alpha * (np.arange(1, m + 1) / m)
    passed = np.zeros(m, bool)
    if ok.any():
        passed[order[: np.flatnonzero(ok).max() + 1]] = True
    return passed


def evaluate_factor(f: pd.DataFrame, fwd: pd.DataFrame, h: int, cut, cost_rt: float = 0.0025, q: int = 5) -> dict:
    """cost_rt = round-trip cost of replacing a holding (STT both sides + stamp + fees + slippage, about 0.25%)."""
    ic = rank_ic(f, fwd)
    samp = ic.iloc[::h]
    dates = samp.dropna().index
    pct = f.rank(axis=1, pct=True)
    top = ((pct >= 1 - 1 / q) & f.notna()).loc[dates]
    xs = fwd.mean(axis=1).reindex(dates)
    top_ret = fwd.where(top).mean(axis=1).reindex(dates)
    bot_ret = fwd.where((pct <= 1 / q) & f.notna()).mean(axis=1).reindex(dates)
    prev = top.shift(1, fill_value=False)
    turnover = (1 - (top & prev).sum(axis=1) / top.sum(axis=1).replace(0, np.nan)).iloc[1:]
    excess = (top_ret - xs).iloc[1:]
    net = excess - turnover * cost_rt
    ppy = 252 / h
    bucket = np.ceil(pct.loc[dates] * q).clip(1, q)
    q_means = pd.DataFrame({k: fwd.loc[dates].where(bucket == k).mean(axis=1) for k in range(1, q + 1)})
    return {"ic_all": _stats(samp), "ic_is": _stats(samp.loc[:cut]), "ic_oos": _stats(samp.loc[cut:]),
            "top_excess_gross": excess.mean() * ppy, "top_excess_net": net.mean() * ppy,
            "long_short": (top_ret - bot_ret).mean() * ppy, "turnover": turnover.mean(), "q_means": q_means}


def factor_corr(factors: dict, step: int = 21) -> pd.DataFrame:
    ranks = {k: v.rank(axis=1).iloc[::step] for k, v in factors.items()}
    names = list(ranks)
    out = pd.DataFrame(np.eye(len(names)), index=names, columns=names)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            out.loc[a, b] = out.loc[b, a] = ranks[a].corrwith(ranks[b], axis=1).mean()
    return out


def event_study(p: Panel, events: dict, horizons=(5, 10, 21)) -> pd.DataFrame:
    """Average excess return after an event (vs the same-day cross-section). t-stat clusters by date."""
    rows = []
    for name, ev in events.items():
        for h in horizons:
            fwd = fwd_returns(p, h)
            exc = fwd.sub(fwd.mean(axis=1), axis=0).where(ev)
            per_date = exc.mean(axis=1).dropna()
            n_ev = int(exc.notna().sum().sum())
            s = _stats(per_date)
            rows.append({"event": name, "horizon": h, "events": n_ev, "avg_excess": per_date.mean() if len(per_date) else np.nan,
                         "hit_rate": float((exc.stack() > 0).mean()) if n_ev else np.nan, "t": s["t"],
                         "p": norm_p(s["t"])})
    return pd.DataFrame(rows)


def macro_study(p: Panel, horizon: int = 21) -> pd.DataFrame | None:
    """Do macro variables predict the next month's index return? (rank correlation on non-overlapping months)"""
    if p.macro is None or p.macro.empty:
        return None
    m, b = p.macro.reindex(p.dates).ffill(), p.benchmark
    feats = {}
    if "vix" in m:
        feats["india_vix_vs_1y_avg"] = -(m["vix"] - m["vix"].rolling(252).mean()) / m["vix"].rolling(252).std()
    if "usdinr" in m:
        feats["rupee_strength_63d"] = -m["usdinr"].pct_change(63)
    if "brent" in m:
        feats["cheaper_crude_63d"] = -m["brent"].pct_change(63)
    if "us10y" in m:
        feats["falling_us_yields_63d"] = -m["us10y"].diff(63)
    target = b.shift(-(horizon + 1)) / b.shift(-1) - 1
    rows = []
    for name, x in feats.items():
        d = pd.concat([x, target], axis=1).dropna().iloc[::horizon]
        n = len(d)
        r = d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank()) if n > 8 else np.nan
        t = r * math.sqrt((n - 2) / max(1e-9, 1 - r * r)) if np.isfinite(r) else np.nan
        rows.append({"feature (higher = more bullish)": name, "months": n, "rank_corr_with_next_month": r, "t": t, "p": norm_p(t)})
    return pd.DataFrame(rows)
