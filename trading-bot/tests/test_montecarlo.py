import numpy as np
import pandas as pd

from algo.data import synthetic_panel
from algo.engine import Config
from algo.montecarlo import RandomPicks, block_bootstrap, null_test
from algo.strategies import MultiFactor, rebalance_starts
from tests.test_quant import controlled_panel


def _setup(seed=1, regime="trend"):
    p = synthetic_panel(25, 6, seed=seed)
    ref = MultiFactor(regime=regime)
    score, d_ref = ref.target(p)
    return p, ref, score, d_ref


def test_random_picks_copy_the_timing_and_turnover_of_the_reference():
    p, ref, score, d_ref = _setup()
    gate = ref.gate(p)
    null = RandomPicks(ref, score, d_ref, gate, seed=5).signals(p).desired
    S = score.to_numpy(float)
    starts = rebalance_starts(S, ref.rebalance_days, ref.top_n)
    D, R = d_ref.to_numpy(bool), null.to_numpy(bool)
    gate_on = gate.reindex(null.index).fillna(False).to_numpy()
    for k in range(1, len(starts)):
        i, j = starts[k], starts[k - 1]
        assert (D[i] & ~D[j]).sum() == (R[i] & ~R[j] & gate_on[i] & gate_on[j]).sum() or not (gate_on[i] and gate_on[j])
        assert R[i].sum() <= ref.top_n
    assert not R[~gate_on].any()                    # nothing held while the regime filter says cash


def test_random_picks_are_reproducible_but_differ_by_seed():
    p, ref, score, d_ref = _setup()
    a = RandomPicks(ref, score, d_ref, None, 1).signals(p).desired
    b = RandomPicks(ref, score, d_ref, None, 1).signals(p).desired
    c = RandomPicks(ref, score, d_ref, None, 2).signals(p).desired
    assert a.equals(b) and not a.equals(c)


def test_bootstrap_is_reproducible_and_ordered():
    eq = pd.Series(np.cumprod(1 + np.random.default_rng(0).normal(0.0004, 0.01, 1500)), index=pd.bdate_range("2018-01-01", periods=1500))
    a, b = block_bootstrap(eq, n=300, seed=7), block_bootstrap(eq, n=300, seed=7)
    assert a == b and a["cagr"][0] < a["cagr"][1] < a["cagr"][2] and a["max_drawdown"][0] < a["max_drawdown"][2]


def test_null_test_is_uninformative_on_pure_noise():
    pcts = []
    for seed in (21, 22, 23, 24, 25):
        p = synthetic_panel(20, 5, seed=seed, persistent=False)
        r = null_test(p, MultiFactor(regime="trend", top_n=10), Config(max_positions=10, cash_yield=0.06), n=30)
        pcts.append(r["pct_sharpe"])
    assert 0.15 < float(np.mean(pcts)) < 0.85 and max(pcts) < 0.99        # no systematic false "skill"


def test_null_test_detects_real_stock_selection_skill():
    p, _ = controlled_panel(effect=0.0004, seed=2, n_sym=40, T=1800)
    ref = MultiFactor(regime="none", top_n=10, factors=("mom_12_1", "mom_6_1"))
    r = null_test(p, ref, Config(max_positions=10), n=30)
    assert r["pct_sharpe"] >= 0.95 and r["p_sharpe"] < 0.10
