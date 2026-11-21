import numpy as np
import pandas as pd

from algo.data import build_panel
from algo.metrics import performance, trade_stats, yearly_returns


def test_cagr_and_zero_drawdown_for_constant_growth():
    idx = pd.bdate_range("2020-01-01", periods=253)
    eq = pd.Series(1_000_000 * 1.0005 ** np.arange(253), index=idx)
    p = performance(eq)
    years = (idx[-1] - idx[0]).days / 365.25
    assert abs(p["cagr"] - ((1.0005 ** 252) ** (1 / years) - 1)) < 1e-9
    assert p["max_drawdown"] == 0 and p["total_return"] > 0


def test_max_drawdown_known_path():
    eq = pd.Series([100.0, 120.0, 90.0, 110.0], index=pd.bdate_range("2020-01-01", periods=4))
    assert abs(performance(eq)["max_drawdown"] - (90 / 120 - 1)) < 1e-12


def test_sharpe_matches_hand_calculation():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0006, 0.01, 1000)
    eq = pd.Series(100 * np.cumprod(1 + r), index=pd.bdate_range("2018-01-01", periods=1000))
    rets = eq.pct_change().dropna()
    expected = (rets.mean() * 252 - 0.06) / (rets.std() * np.sqrt(252))
    assert abs(performance(eq, rf=0.06)["sharpe"] - expected) < 1e-12


def test_trade_stats_known_values():
    t = pd.DataFrame({"net_pnl": [100.0, -50.0, -50.0, 200.0], "return": [0.1, -0.05, -0.05, 0.2],
                      "days_held": [10, 20, 30, 40], "reason": ["signal", "stop", "stop", "signal"]})
    s = trade_stats(t)
    assert s["trades"] == 4 and s["win_rate"] == 0.5 and abs(s["profit_factor"] - 3.0) < 1e-12
    assert s["avg_days_held"] == 25 and s["stop_exits"] == 2


def test_yearly_returns_known_values():
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    eq = pd.Series(np.nan, index=idx)
    eq.iloc[0], eq.loc["2020-12-31"], eq.loc["2021-12-31"] = 100.0, 110.0, 121.0
    y = yearly_returns(eq.interpolate())
    assert abs(y.iloc[0] - 0.10) < 0.01 and abs(y.iloc[1] - 0.10) < 0.01


def test_benchmark_is_never_back_filled_with_future_values():
    idx = pd.bdate_range("2020-01-01", periods=300)
    mk = lambda v: pd.DataFrame({"A": np.full(300, v)}, index=idx)
    frames = {"A": pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1e7}, index=idx)}
    late_bench = pd.Series(range(100, 200), index=idx[200:])           # benchmark only starts on day 200
    p = build_panel(frames, late_bench)
    assert p.benchmark.iloc[:200].isna().all()                          # early dates stay unknown, not filled from the future
