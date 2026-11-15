import numpy as np
import pandas as pd

from algo.macro import risk_on
from algo.timing import shuffle_runs, timing_test


def regime_index(T=3000, persistence=0.99, drift=0.0010, vol=0.009, seed=0):
    """Index with real, persistent bull/bear regimes: a trend filter SHOULD find value here."""
    rng = np.random.default_rng(seed)
    state, r = 1, np.zeros(T)
    for t in range(T):
        if rng.random() > persistence:
            state = -state
        r[t] = state * drift + rng.normal(0, vol)
    return pd.Series(100 * np.cumprod(1 + r), index=pd.bdate_range("2012-01-01", periods=T))


def test_shuffle_preserves_exposure_and_switches():
    rng = np.random.default_rng(1)
    g = np.array([1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1], bool)
    for _ in range(20):
        s = shuffle_runs(g, rng)
        assert len(s) == len(g) and s.sum() == g.sum() and (s[1:] != s[:-1]).sum() == (g[1:] != g[:-1]).sum() and s[0] == g[0]


def test_timing_null_is_uninformative_on_a_random_walk():
    ps = []
    for seed in (1, 2, 3, 4, 5, 6):
        b = pd.Series(100 * np.cumprod(1 + np.random.default_rng(seed).normal(0.0003, 0.01, 3000)), index=pd.bdate_range("2012-01-01", periods=3000))
        ps.append(timing_test(b, risk_on(None, b), n=200, seed=3)["p_sharpe"])
    assert sum(p < 0.05 for p in ps) <= 1 and 0.15 < float(np.mean(ps)) < 0.85      # no systematic false "skill"


def test_timing_null_detects_slow_real_regimes_most_of_the_time():
    """Planted regimes ~500 days long (slower than the 200-day filter's lag). Power is limited with few regime changes,
    so we assert on the pattern over 5 samples: mostly detected (chance alone would give about 0.5 of 5) and drawdown always better."""
    detected, dd_better = 0, 0
    for seed in range(5):
        b = regime_index(T=4000, persistence=0.998, drift=0.0008, seed=seed)
        res = timing_test(b, risk_on(None, b), n=300, seed=3)
        detected += res["p_sharpe"] < 0.10
        dd_better += res["real"]["max_drawdown"] > res["buy_hold"]["max_drawdown"]
    assert detected >= 3 and dd_better == 5


def test_timing_is_reproducible():
    b = regime_index(seed=2)
    a, c = timing_test(b, risk_on(None, b), n=100, seed=7), timing_test(b, risk_on(None, b), n=100, seed=7)
    assert a["p_sharpe"] == c["p_sharpe"] and a["null"].equals(c["null"])
