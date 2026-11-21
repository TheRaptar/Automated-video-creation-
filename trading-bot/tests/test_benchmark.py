import numpy as np
import pandas as pd

from algo.benchmark import load_benchmark_tr
from algo.provenance import Manifest

IDX = pd.bdate_range("2012-01-02", periods=2500)
PRICE = pd.Series(100 * np.cumprod(1 + np.random.default_rng(0).normal(0.0004, 0.01, len(IDX))), index=IDX)


def tri_frame(div=0.013):
    return pd.DataFrame({"gross_tri": PRICE * (1 + div / 252) ** np.arange(len(IDX))})


def test_official_tri_is_verified_when_consistent_with_price():
    m = Manifest()
    lvl, status = load_benchmark_tr(PRICE, "NIFTY 50", m, fetch_tri=lambda *a: tri_frame())
    assert status == "VERIFIED" and lvl.iloc[-1] > PRICE.iloc[-1] * 0.99


def test_inconsistent_tri_is_not_trusted():
    bad = pd.DataFrame({"gross_tri": pd.Series(np.random.default_rng(5).normal(1000, 10, len(IDX)), index=IDX)})
    m = Manifest()
    _, status = load_benchmark_tr(PRICE, "NIFTY 50", m, fetch_tri=lambda *a: bad)
    assert status == "INCOMPLETE"


def test_fallback_chain_estimated_then_assumed():
    dy = pd.Series(1.3, index=IDX)
    m = Manifest()
    _, s1 = load_benchmark_tr(PRICE, "NIFTY 50", m, fetch_tri=lambda *a: pd.DataFrame(), fetch_dy=lambda *a: dy)
    assert s1 == "ESTIMATED"
    _, s2 = load_benchmark_tr(PRICE, "NIFTY 50", m, fetch_tri=lambda *a: pd.DataFrame(), fetch_dy=lambda *a: pd.Series(dtype=float))
    assert s2 == "ASSUMED"
    _, s3 = load_benchmark_tr(PRICE, "NIFTY 50", m, fetch_tri=lambda *a: (_ for _ in ()).throw(RuntimeError("blocked")), fetch_dy=lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert s3 == "ASSUMED"


def test_other_index_tri_is_checked_on_correlation_only():
    wide = pd.DataFrame({"gross_tri": PRICE ** 1.0 * (1.0004 ** np.arange(len(IDX)))})       # diverges from the price index
    _, strict = load_benchmark_tr(PRICE, "NIFTY 500", Manifest(), fetch_tri=lambda *a: wide)
    _, relaxed = load_benchmark_tr(PRICE, "NIFTY 500", Manifest(), fetch_tri=lambda *a: wide, same_index=False)
    assert strict == "INCOMPLETE" and relaxed == "VERIFIED"
