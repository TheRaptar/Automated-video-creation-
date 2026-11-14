import numpy as np
import pandas as pd
import pytest

from algo.alphalab import bh_fdr, evaluate_factor, fwd_returns
from algo.alphalab_report import run_lab
from algo.data import Panel, synthetic_panel
from algo.engine import Config, run_backtest
from algo.execution import (front_loaded_schedule, impact_bps, intraday_profile, schedule_cost_bps, twap_schedule,
                            vwap_schedule)
from algo.factors import compute_factors, event_signals
from algo.fundamentals import load_fundamental_factors
from algo.macro import smooth_state
from algo.strategies import MultiFactor, Signals, Strategy
from tests.test_algo import Manual, assert_causal, flat_panel, mid_month_cut


# ---------------------------------------------------------------- no look-ahead in the feature library
def test_all_factors_and_events_are_causal():
    p = synthetic_panel(10, 4, seed=4)
    cut = mid_month_cut(p)
    q = p.slice(end=p.dates[cut])
    full, part = compute_factors(p), compute_factors(q)
    for name in full:
        pd.testing.assert_frame_equal(full[name].iloc[:cut + 1], part[name], check_exact=False, rtol=1e-9, obj=name)
    fe, pe = event_signals(p), event_signals(q)
    for name in fe:
        pd.testing.assert_frame_equal(fe[name].iloc[:cut + 1], pe[name], obj=name)


@pytest.mark.parametrize("model", ["equal", "ridge"])
def test_multifactor_is_causal(model):
    assert_causal(MultiFactor(model=model, regime="macro"), synthetic_panel(14, 5, seed=6))


# ---------------------------------------------------------------- statistics: positive and negative controls
def test_bh_fdr_basic():
    assert bh_fdr([0.001, 0.009, 0.5, 0.8], 0.10).tolist() == [True, True, False, False]
    assert not bh_fdr([0.2, 0.3, 0.9], 0.10).any()


def controlled_panel(effect, seed=0, n_sym=40, T=2500):
    """A panel where we KNOW the truth: daily return = effect * (persistent hidden score) + noise."""
    from algo.data import build_panel
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", periods=T)
    phi = 0.97
    F = np.zeros((T, n_sym))
    F[0] = rng.normal(size=n_sym)
    for t in range(1, T):
        F[t] = phi * F[t - 1] + np.sqrt(1 - phi ** 2) * rng.normal(size=n_sym)
    r = np.vstack([np.zeros(n_sym), effect * F[:-1]]) + rng.normal(0, 0.012, (T, n_sym))
    frames = {}
    for j in range(n_sym):
        close = 100 * np.exp(np.cumsum(r[:, j]))
        open_ = np.r_[close[0], close[:-1]]
        frames[f"S{j}"] = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.003, "low": np.minimum(open_, close) * 0.997,
                                        "close": close, "volume": np.full(T, 5e6)}, index=idx)
    return build_panel(frames, None), pd.DataFrame(F, index=idx, columns=list(frames))


def test_lab_detects_a_known_effect():
    p, hidden = controlled_panel(effect=0.0002)
    r = evaluate_factor(hidden, fwd_returns(p, 21), 21, p.dates[int(len(p.dates) * 0.7)])
    assert r["ic_all"]["t"] > 3 and r["ic_oos"]["mean"] > 0 and r["ic_is"]["mean"] > 0


def test_lab_sees_nothing_when_the_effect_is_zero():
    p, hidden = controlled_panel(effect=0.0, seed=3)
    r = evaluate_factor(hidden, fwd_returns(p, 21), 21, p.dates[int(len(p.dates) * 0.7)])
    assert abs(r["ic_all"]["t"]) < 3


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_lab_finds_nothing_in_pure_noise(seed, tmp_path):
    p = synthetic_panel(30, 8, seed=seed, persistent=False)
    tab = run_lab(p, compute_factors(p), [5, 21], 0.3, tmp_path)
    assert (tab.verdict == "CANDIDATE").sum() == 0


# ---------------------------------------------------------------- execution maths
def test_schedules_sum_and_vwap_beats_twap():
    for q in (1, 74, 75, 10_000, 123_457):
        assert twap_schedule(q).sum() == q and vwap_schedule(q).sum() == q and front_loaded_schedule(q).sum() == q
    adv, sigma = 5e6, 0.015
    order = 250_000
    c_vwap = schedule_cost_bps(vwap_schedule(order), adv, sigma)
    c_twap = schedule_cost_bps(twap_schedule(order), adv, sigma)
    c_front = schedule_cost_bps(front_loaded_schedule(order), adv, sigma)
    assert c_vwap < c_twap < c_front            # VWAP is the cost-minimising schedule under a U-shaped volume curve


def test_flat_volume_makes_twap_equal_vwap():
    flat = np.ones(75)
    a = schedule_cost_bps(twap_schedule(100_000), 5e6, 0.015, profile=flat)
    b = schedule_cost_bps(vwap_schedule(100_000, flat), 5e6, 0.015, profile=flat)
    assert abs(a - b) < 1e-6


def test_impact_grows_with_size_and_vol():
    assert impact_bps(1e6, 5e8, 0.015) < impact_bps(1e7, 5e8, 0.015) < impact_bps(1e8, 5e8, 0.015)
    assert impact_bps(1e7, 5e8, 0.01) < impact_bps(1e7, 5e8, 0.03)
    assert abs(intraday_profile().sum() - 1) < 1e-12


# ---------------------------------------------------------------- engine additions
def test_idle_cash_earns_yield():
    p = flat_panel(n=253)
    des = pd.DataFrame(False, index=p.dates, columns=p.symbols)
    r = run_backtest(p, Manual(des), Config(cash_yield=0.06))
    assert abs(r.equity.iloc[-1] / 1_000_000 - 1.06 ** (253 / 252)) < 1e-6 and r.interest > 0


def test_impact_slippage_model_uses_spread():
    p = flat_panel()
    des = pd.DataFrame(False, index=p.dates, columns=p.symbols)
    des.iloc[25:35] = True
    cfg = Config(max_positions=1, min_adv=0, costs=Config().costs, slippage_model="impact", half_spread_bps=50.0)
    r = run_backtest(p, Manual(des), cfg)
    assert abs(r.trades.iloc[0].entry_price / 100.0 - 1.005) < 1e-6


# ---------------------------------------------------------------- fundamentals without look-ahead
def test_fundamentals_respect_reporting_lag(tmp_path):
    p = flat_panel(n=300, symbols=("A", "B"))
    csv = tmp_path / "f.csv"
    pd.DataFrame({"date": ["2024-03-31", "2024-03-31"], "symbol": ["A", "B"], "roe": [10.0, 20.0]}).to_csv(csv, index=False)
    f = load_fundamental_factors(str(csv), p, lag_days=60)["fund_roe"]
    assert f.loc[:"2024-05-29"].isna().all().all()           # period ended 31 Mar: unusable before 30 May
    assert f.loc["2024-06-03", "A"] == 10.0 and f.loc["2024-06-03", "B"] == 20.0


# ---------------------------------------------------------------- hysteresis
def test_smooth_state_cuts_flicker():
    idx = pd.bdate_range("2024-01-01", periods=200)
    rng = np.random.default_rng(0)
    raw = pd.Series(rng.random(200) > 0.4, index=idx)
    sm = smooth_state(raw)
    assert (sm != sm.shift()).sum() < (raw != raw.shift()).sum() / 3
