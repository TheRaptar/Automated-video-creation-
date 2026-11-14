"""
Execution maths: market-impact model and TWAP / VWAP slicing.

Square-root impact law: moving a fraction `part` of a day's volume costs about  coeff * sigma_daily * sqrt(part).
Slicing: with per-bin impact  eta*sigma*sqrt(q_t / V_t)  the total cost is  sum q_t^1.5 * V_t^-0.5 .
Minimising that subject to  sum q_t = Q  gives  q_t proportional to V_t  (Lagrange condition 1.5*q^0.5*V^-0.5 = lambda),
i.e. VWAP-style participation is the cost-optimal schedule when volatility is constant. TWAP is only optimal if volume is flat.
"""
import numpy as np


def impact_bps(order_value, adv_value, sigma_daily, coeff=0.8, half_spread_bps=3.0) -> float:
    """Expected one-way cost in basis points: half the spread plus square-root market impact."""
    if adv_value <= 0:
        return half_spread_bps + 100.0
    part = max(order_value, 0.0) / adv_value
    return half_spread_bps + coeff * sigma_daily * np.sqrt(part) * 1e4


def intraday_profile(n_bins: int = 75) -> np.ndarray:
    """Typical U-shaped intraday volume curve (busy open and close). 75 five-minute bins = 9:15-15:30 NSE."""
    x = np.linspace(-1, 1, n_bins)
    w = 1 + 2.2 * x ** 2
    return w / w.sum()


def twap_schedule(total_shares: int, n_bins: int = 75) -> np.ndarray:
    base, rem = divmod(int(total_shares), n_bins)
    return np.array([base + (1 if i < rem else 0) for i in range(n_bins)])


def vwap_schedule(total_shares: int, profile=None) -> np.ndarray:
    w = intraday_profile() if profile is None else np.asarray(profile, float) / np.sum(profile)
    raw = total_shares * w
    out = np.floor(raw).astype(int)
    short = int(total_shares - out.sum())
    for k in np.argsort(-(raw - out))[:short]:
        out[k] += 1
    return out


def front_loaded_schedule(total_shares: int, bins_used: int = 3, n_bins: int = 75) -> np.ndarray:
    """The naive way: dump everything in the first few bins (e.g. the first 15 minutes)."""
    out = np.zeros(n_bins, dtype=int)
    out[:bins_used] = twap_schedule(total_shares, bins_used)
    return out


def schedule_cost_bps(schedule, adv_shares: float, sigma_daily: float, profile=None, coeff=0.8, half_spread_bps=3.0) -> float:
    """Average per-share cost (bps) of a schedule: spread + sum_t q_t * coeff*sigma*sqrt(q_t/V_t) / sum q."""
    q = np.asarray(schedule, float)
    w = intraday_profile(len(q)) if profile is None else np.asarray(profile, float) / np.sum(profile)
    v = adv_shares * w
    part = np.divide(q, v, out=np.zeros_like(q), where=v > 0)
    return half_spread_bps + float((q * coeff * sigma_daily * np.sqrt(part)).sum() / q.sum() * 1e4)
