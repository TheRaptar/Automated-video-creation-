"""
Multi-factor model: cross-sectionally standardise factors, combine them, and hold the best-ranked stocks with a
turnover buffer (hysteresis) so we don't pay STT every month for tiny rank changes.
Two ways to combine: equal weights (robust, nothing to overfit) or a walk-forward ridge regression
(weights re-learned every month from PAST data only).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import Panel
from .factors import compute_factors
from .macro import risk_on


def zscore(df: pd.DataFrame, clip: float = 3.0) -> pd.DataFrame:
    z = df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)
    return z.clip(-clip, clip)


def composite(factors: dict, names, weights=None) -> pd.DataFrame:
    w = np.ones(len(names)) if weights is None else np.asarray(weights, float)
    zs = [zscore(factors[n]).to_numpy() * wi for n, wi in zip(names, w)]
    ref = factors[names[0]]
    return pd.DataFrame(np.sum(zs, axis=0) / np.abs(w).sum(), index=ref.index, columns=ref.columns)


def ridge_scores(factors: dict, names, p: Panel, horizon: int = 21, train_days: int = 756, step: int = 21,
                 alpha: float = 50.0, sample_every: int = 5, min_rows: int = 400) -> pd.DataFrame:
    """Walk-forward: at each refit date, learn weights from observations whose forward return was already
    realised, then score every stock with them until the next refit."""
    Z = np.stack([zscore(factors[n]).to_numpy() for n in names])                      # K x T x N
    fwd = p.open.shift(-(horizon + 1)) / p.open.shift(-1) - 1
    Y = zscore(fwd).to_numpy()
    K, T, N = Z.shape
    scores = np.full((T, N), np.nan)
    beta = None
    for r in range(T):
        if r % step == 0 and r > horizon + 5:
            lo, hi = max(0, r - train_days), r - horizon - 2
            rows_x, rows_y = [], []
            for d in range(lo, hi + 1, sample_every):
                x, y = Z[:, d, :].T, Y[d]
                ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
                rows_x.append(x[ok]); rows_y.append(y[ok])
            if rows_x:
                X, y = np.vstack(rows_x), np.concatenate(rows_y)
                if len(y) >= min_rows:
                    beta = np.linalg.solve(X.T @ X + alpha * np.eye(K), X.T @ y)
        if beta is not None:
            x = Z[:, r, :].T
            ok = np.isfinite(x).all(axis=1)
            scores[r, ok] = x[ok] @ beta
    return pd.DataFrame(scores, index=p.close.index, columns=p.close.columns)
