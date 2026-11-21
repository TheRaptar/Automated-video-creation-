import numpy as np
import pandas as pd

from algo.acceptance import edge_claim_allowed, evaluate_gates, regime_buckets, rolling_excess_share, verdict
from algo.engine import Config


class R:
    def __init__(self, eq):
        self.equity = eq


def curves(edge_daily=0.0003, years=11, seed=0):
    idx = pd.bdate_range("2012-01-02", periods=int(252 * years))
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0004, 0.01, len(idx))
    price = pd.Series(100 * np.cumprod(1 + r), index=idx)
    bench = 1_000_000 * price / price.iloc[0]
    strat = bench * np.exp(edge_daily * np.arange(len(idx)))
    return R(strat), bench, price, idx[int(len(idx) * 0.7)]


def gates_for(res, bench, price, cut, **kw):
    return {g.id: g for g in evaluate_gates(res, bench, price, Config(max_adv_pct=0.02), cut, **kw)}


def test_regime_labels_are_causal_and_cover_all_three_buckets():
    _, _, price, _ = curves()
    lab = regime_buckets(price)
    assert set(lab.dropna()) == {"bull", "sideways", "bear"}
    short = regime_buckets(price.iloc[:1500])
    assert (lab.iloc[:1500].fillna("x") == short.fillna("x")).all()


def test_outperformer_passes_gate_1_underperformer_fails():
    res, bench, price, cut = curves(edge_daily=0.0003)
    assert gates_for(res, bench, price, cut)[1].status == "PASS"
    res2, bench2, price2, cut2 = curves(edge_daily=-0.0003)
    assert gates_for(res2, bench2, price2, cut2)[1].status == "FAIL"


def test_gate_5_uses_bonferroni_and_minimum_runs():
    res, bench, price, cut = curves()
    g = gates_for(res, bench, price, cut, null_p=0.004, n_null=1000, ic_t=3.5, n_variants=5)[5]
    assert g.status == "FAIL"                                           # 0.004 > 0.01/5
    assert gates_for(res, bench, price, cut, null_p=0.001, n_null=1000, ic_t=3.5, n_variants=5)[5].status == "PASS"
    assert gates_for(res, bench, price, cut, null_p=0.001, n_null=300, ic_t=3.5, n_variants=5)[5].status == "FAIL"   # too few runs
    assert gates_for(res, bench, price, cut)[5].status == "NOT_EVALUATED"


def test_gate_6_and_7_and_8():
    res, bench, price, cut = curves()
    g = gates_for(res, bench, price, cut)
    assert g[6].status == "NOT_EVALUATED"                               # sector caps cannot be checked
    big = evaluate_gates(res, bench, price, Config(max_adv_pct=0.05), cut)
    assert {x.id: x for x in big}[6].status == "FAIL"
    sweep = pd.DataFrame({"oos_excess_cagr": [0.01] * 9 + [-0.01]})
    assert gates_for(res, bench, price, cut, sweep_df=sweep)[7].status == "PASS"
    assert gates_for(res, bench, price, cut, sweep_df=pd.DataFrame({"oos_excess_cagr": [0.01, -0.01]}))[7].status == "FAIL"
    assert g[8].status == "FAIL" and gates_for(res, bench, price, cut, paper_months=6)[8].status == "PASS"


def test_no_edge_can_be_claimed_in_phase_2():
    res, bench, price, cut = curves(edge_daily=0.0005)                  # even a strong outperformer
    gates = evaluate_gates(res, bench, price, Config(max_adv_pct=0.02), cut)
    assert not edge_claim_allowed(gates) and verdict(gates).startswith("NOT PASSED")
    assert {g.id: g for g in gates}[2].status == "FAIL" and {g.id: g for g in gates}[4].status == "NOT_EVALUATED"


def test_rolling_windows_need_three_years():
    idx = pd.bdate_range("2020-01-01", periods=500)
    a = pd.Series(np.linspace(100, 120, 500), index=idx)
    assert rolling_excess_share(a, a)[1] == 0
