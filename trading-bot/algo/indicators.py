"""Causal indicators: the value on day t uses data up to and including day t only."""
import numpy as np
import pandas as pd


def sma(x, n):
    return x.rolling(n, min_periods=n).mean()


def rsi(close, n=2):
    delta = close.diff()
    up, dn = delta.clip(lower=0), -delta.clip(upper=0)
    avg_up = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_dn = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_up / avg_dn
    out = 100 - 100 / (1 + rs)
    return out.where(avg_dn != 0, 100.0).where(avg_up.notna())


def atr(high, low, close, n=14):
    pc = close.shift(1)
    tr = np.maximum.reduce([(high - low).to_numpy(), (high - pc).abs().to_numpy(), (low - pc).abs().to_numpy()])
    tr = pd.DataFrame(tr, index=close.index, columns=close.columns)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
