"""
Machine-checkable version of the eight acceptance gates in RESEARCH_CHARTER.md (unchanged).
A gate is PASS, FAIL or NOT_EVALUATED. NOT_EVALUATED counts as not passed: a strategy only "has an edge" if ALL eight pass.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import performance


@dataclass
class Gate:
    id: int
    name: str
    status: str            # PASS | FAIL | NOT_EVALUATED
    evidence: str


GATE_NAMES = {1: "Out-of-sample excess return vs Nifty 50 TRI", 2: "Economic rationale registered before testing",
              3: "Works in at least 2 of 3 regimes", 4: "Beats TRI after costs, slippage AND tax", 5: "Not explained by chance",
              6: "Risk and liquidity limits", 7: "Parameter stability", 8: "Paper trading evidence (>= 6 months)"}


def regime_buckets(price: pd.Series) -> pd.Series:
    """Provisional causal regime label per day (Phase 3 replaces this with the full regime engine)."""
    sma = price.rolling(200, min_periods=200).mean()
    slope = sma.pct_change(63)
    lab = pd.Series("sideways", index=price.index, dtype=object)
    lab[(price > sma) & (slope > 0)] = "bull"
    lab[(price < sma) & (slope < 0)] = "bear"
    lab[sma.isna() | slope.isna()] = np.nan
    return lab


def _cagr(eq: pd.Series) -> float:
    return performance(eq)["cagr"]


def rolling_excess_share(strat: pd.Series, bench: pd.Series, window: int = 756, step: int = 21):
    wins = []
    for i in range(0, len(strat) - window, step):
        s, b = strat.iloc[i:i + window], bench.iloc[i:i + window]
        wins.append(_cagr(s) > _cagr(b))
    return (float(np.mean(wins)), len(wins)) if wins else (np.nan, 0)


def evaluate_gates(res, bench_eq: pd.Series, price_index: pd.Series, cfg, cut, sweep_df=None, null_p=None, n_null=0,
                   ic_t=None, n_variants: int = 1, rationale_registered: bool = False, paper_months: float = 0.0,
                   sector_limits_ok=None, rf: float = 0.06) -> list:
    eq = res.equity
    bench = bench_eq.reindex(eq.index).ffill()
    gates = []

    # 1. out-of-sample excess + rolling 3-year windows
    o_s, o_b = _cagr(eq.loc[cut:]), _cagr(bench.loc[cut:])
    share, n_w = rolling_excess_share(eq, bench)
    if n_w == 0:
        gates.append(Gate(1, GATE_NAMES[1], "NOT_EVALUATED", "less than 3 years of data for rolling windows"))
    else:
        ok = (o_s > o_b) and share >= 0.70
        gates.append(Gate(1, GATE_NAMES[1], "PASS" if ok else "FAIL",
                          f"out-of-sample CAGR {o_s:.1%} vs TRI {o_b:.1%}; strategy ahead in {share:.0%} of {n_w} rolling 3-year windows (need >= 70%)"))

    # 2. rationale
    gates.append(Gate(2, GATE_NAMES[2], "PASS" if rationale_registered else "FAIL",
                      "rationale registered in the charter before testing" if rationale_registered else
                      "this strategy was tested before the charter existed, so a rationale cannot count as pre-registered"))

    # 3. regimes (labels known at the previous close, applied to the next day's return)
    lab = regime_buckets(price_index).reindex(eq.index).ffill().shift(1)
    sr, br = eq.pct_change(), bench.pct_change()
    rows, ev, viol = [], 0, False
    pos = 0
    for b in ("bull", "sideways", "bear"):
        m = lab == b
        if m.sum() < 252:
            rows.append(f"{b}: only {int(m.sum())} days (insufficient)")
            continue
        s_cum, b_cum = (1 + sr[m].fillna(0)).prod() - 1, (1 + br[m].fillna(0)).prod() - 1
        ev += 1
        pos += s_cum > b_cum
        viol |= (s_cum < 0) and (s_cum < b_cum)
        rows.append(f"{b}: strategy {s_cum:+.0%} vs TRI {b_cum:+.0%} over {int(m.sum())} days")
    if ev < 2:
        gates.append(Gate(3, GATE_NAMES[3], "NOT_EVALUATED", "; ".join(rows)))
    else:
        gates.append(Gate(3, GATE_NAMES[3], "PASS" if pos >= 2 and not viol else "FAIL", "; ".join(rows) + (" (a bucket lost more than the benchmark)" if viol else "")))

    # 4. tax
    gates.append(Gate(4, GATE_NAMES[4], "NOT_EVALUATED", "costs and slippage are in the numbers; short-/long-term tax scenarios are not implemented until Phase 5"))

    # 5. chance
    if null_p is None or ic_t is None:
        gates.append(Gate(5, GATE_NAMES[5], "NOT_EVALUATED", "random-selection null test and pooled IC test exist only for the multi-factor strategy"))
    else:
        thr = 0.01 / max(1, n_variants)
        ok = n_null >= 1000 and null_p <= thr and ic_t > 3
        gates.append(Gate(5, GATE_NAMES[5], "PASS" if ok else "FAIL",
                          f"null-test p = {null_p:.4f} from {n_null} runs (need <= {thr:.5f} after adjusting for {n_variants} variants, and >= 1000 runs); pooled IC t = {ic_t:.2f} (need > 3)"))

    # 6. risk and liquidity
    mdd_s, mdd_b = performance(eq, rf)["max_drawdown"], performance(bench, rf)["max_drawdown"]
    dd_ok, adv_ok = abs(mdd_s) <= abs(mdd_b), cfg.max_adv_pct <= 0.02
    ev6 = f"max drawdown {mdd_s:.1%} vs TRI {mdd_b:.1%}; order size cap {cfg.max_adv_pct:.0%} of daily traded value (limit 2%)"
    if not (dd_ok and adv_ok):
        gates.append(Gate(6, GATE_NAMES[6], "FAIL", ev6))
    elif sector_limits_ok is None:
        gates.append(Gate(6, GATE_NAMES[6], "NOT_EVALUATED", ev6 + "; sector exposure caps cannot be checked without sector data"))
    else:
        gates.append(Gate(6, GATE_NAMES[6], "PASS" if sector_limits_ok else "FAIL", ev6))

    # 7. parameter stability
    if sweep_df is None or "oos_excess_cagr" not in sweep_df or sweep_df["oos_excess_cagr"].isna().all():
        gates.append(Gate(7, GATE_NAMES[7], "NOT_EVALUATED", "no parameter sweep with benchmark-relative results"))
    else:
        frac = float((sweep_df["oos_excess_cagr"] > 0).mean())
        gates.append(Gate(7, GATE_NAMES[7], "PASS" if frac >= 0.80 else "FAIL",
                          f"{frac:.0%} of {len(sweep_df)} neighbouring settings keep positive out-of-sample excess return over TRI (need >= 80%)"))

    # 8. paper trading
    gates.append(Gate(8, GATE_NAMES[8], "PASS" if paper_months >= 6 else "FAIL", f"paper trading: {paper_months:g} of 6 required months"))
    return gates


def edge_claim_allowed(gates: list) -> bool:
    return len(gates) == 8 and all(g.status == "PASS" for g in gates)


def verdict(gates: list) -> str:
    if edge_claim_allowed(gates):
        return "ALL EIGHT GATES PASSED - still requires independent validation before any real capital"
    p = sum(g.status == "PASS" for g in gates)
    return f"NOT PASSED ({p} of 8 gates passed): no reliable edge can be claimed"
