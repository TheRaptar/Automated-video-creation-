import numpy as np
import pandas as pd

from algo.data import synthetic_panel
from algo.phase2 import run_universe
from algo.provenance import Manifest


def test_pipeline_runs_end_to_end_and_never_claims_an_edge(tmp_path):
    p = synthetic_panel(30, 9, seed=7)
    p.benchmark_tr = p.benchmark * (1.00004 ** np.arange(len(p.dates)))
    cash = pd.Series((1.06) ** (1 / 252) - 1, index=p.dates)
    m = Manifest()
    m.add("benchmark TRI", "ASSUMED", "test")
    rows = run_universe(p, m, cash, tmp_path, "SYNTHETIC test", null_runs=20, do_sweep=True)
    assert {r["strategy"] for r in rows} == {"momentum", "donchian", "rsi2", "multifactor_trend", "multifactor_macro"}
    assert all(not r["edge"] for r in rows)                                      # gates 2, 4, 6, 8 can never pass in Phase 2
    assert all(r["gates"][2] == "FAIL" and r["gates"][4] == "NOT_EVALUATED" and r["gates"][8] == "FAIL" for r in rows)
    assert all(r["gates"][5] == "NOT_EVALUATED" for r in rows if not r["strategy"].startswith("multifactor"))
    assert all(r["gates"][5] in ("PASS", "FAIL") for r in rows if r["strategy"].startswith("multifactor"))
    text = (tmp_path / "PHASE2_SUMMARY.md").read_text()
    assert "no edge is claimed" in text and "Data status" in text and "ASSUMED" in text and "Gate matrix" in text
    assert (tmp_path / "momentum" / "gates.md").exists() and (tmp_path / "multifactor_macro" / "summary.md").exists()


def test_macro_variant_is_skipped_without_macro_data(tmp_path):
    p = synthetic_panel(25, 8, seed=8)
    p.macro = None
    p.benchmark_tr = p.benchmark.copy()
    rows = run_universe(p, Manifest(), pd.Series(0.0002, index=p.dates), tmp_path, "t", null_runs=10, do_sweep=False)
    assert "multifactor_macro" not in {r["strategy"] for r in rows} and len(rows) == 4
