"""
Phase 2 pipeline: re-run Momentum, Breakout, RSI(2) and Multi-factor on corrected foundations
(official TRI benchmark, overnight-rate cash returns, liquidity cap 2% of daily value) and judge each against the eight
UNCHANGED acceptance gates. It never states that a strategy has an edge unless all eight gates pass.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from .acceptance import edge_claim_allowed, evaluate_gates, verdict
from .alphalab import evaluate_factor, fwd_returns
from .engine import Config, run_backtest
from .metrics import performance
from .montecarlo import null_test
from .report import write_report
from .robust import sweep
from .strategies import GRIDS, STRATEGIES

VARIANTS = [("momentum", {}), ("donchian", {}), ("rsi2", {}), ("multifactor", {"regime": "trend"}), ("multifactor", {"regime": "macro"})]


def bench_equity(panel, capital: float) -> pd.Series:
    src = panel.benchmark_tr if panel.benchmark_tr is not None else panel.benchmark
    s = src.reindex(panel.dates).ffill()
    return s / s.dropna().iloc[0] * capital


def gates_markdown(gates) -> str:
    rows = ["| # | Gate | Status | Evidence |", "|---|---|---|---|"]
    rows += [f"| {g.id} | {g.name} | **{g.status}** | {g.evidence} |" for g in gates]
    return "\n".join(rows)


def run_universe(panel, manifest, cash_returns, out, label, null_runs: int = 1000, do_sweep: bool = True,
                 max_positions: int | None = None, rf: float = 0.06, extra_md: str = "", capital: float = 1_000_000) -> list:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cut = panel.dates[int(len(panel.dates) * 0.7)]
    bench = bench_equity(panel, capital)
    pb = performance(bench, rf)
    variants = [(n, p) for n, p in VARIANTS if not (p.get("regime") == "macro" and panel.macro is None)]
    n_variants = sum(len(list(itertools.product(*GRIDS[n].values()))) for n, _ in variants)
    years = (panel.dates[-1] - panel.dates[0]).days / 365.25
    rows = []
    for name, params in variants:
        tag = name + (f"_{params['regime']}" if "regime" in params else "")
        strat = STRATEGIES[name](**params)
        cfg = Config(capital=capital, max_positions=max_positions or int(strat.params().get("top_n", 10)), slippage_bps=5.0,
                     max_adv_pct=0.02, cash_returns=cash_returns)
        res = run_backtest(panel, strat, cfg)
        sw = sweep(panel, name, cfg, cut, rf, bench, base=params) if do_sweep else None
        null_p = n_null = ic_t = None
        if name == "multifactor":
            nt = null_test(panel, strat, cfg, n=null_runs)
            null_p, n_null = nt["p_sharpe"], nt["n"]
            score, _ = strat.target(panel)
            ic_t = evaluate_factor(score, fwd_returns(panel, 21), 21, cut)["ic_all"]["t"]
        gates = evaluate_gates(res, bench, panel.benchmark, cfg, cut, sw, null_p, n_null or 0, ic_t, n_variants, False, 0.0, None, rf)
        full, _, _ = write_report(out / tag, res, panel, cut, rf, sw, label, len(panel.symbols), manifest.to_markdown())
        (out / tag / "gates.md").write_text(f"# Acceptance gates: {tag}\n\n**{verdict(gates)}**\n\n" + gates_markdown(gates), encoding="utf-8")
        po, bo = performance(res.equity.loc[cut:], rf), performance(bench.loc[cut:], rf)
        rows.append({"strategy": tag, "cagr": full["cagr"], "bench_cagr": pb["cagr"], "oos_cagr": po["cagr"], "bench_oos_cagr": bo["cagr"],
                     "max_drawdown": full["max_drawdown"], "bench_max_drawdown": pb["max_drawdown"], "trades": len(res.trades),
                     "costs_pct_year": res.total_costs / capital / years, "interest_share": res.interest / max(1.0, res.equity.iloc[-1] - capital),
                     "passed": sum(g.status == "PASS" for g in gates), "verdict": verdict(gates), "edge": edge_claim_allowed(gates),
                     "gates": {g.id: g.status for g in gates}, "null_p": null_p, "ic_t": ic_t})
    write_summary(out, label, rows, manifest, extra_md, years, n_variants)
    return rows


def write_summary(out, label, rows, manifest, extra_md, years, n_variants):
    pc = lambda x: "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"
    md = [f"# Phase 2 summary: {label}", "", f"History used: {years:.1f} years. Strategy variants counted for multiple-testing adjustment: {n_variants}.", "",
          "## Data status", "", manifest.to_markdown(), ""]
    if extra_md:
        md += ["## Universe and survivorship", "", extra_md, ""]
    md += ["## Results versus the total-return benchmark (after costs and slippage; BEFORE tax)", "",
           "| Strategy | CAGR | Benchmark CAGR | Out-of-sample CAGR | Benchmark out-of-sample | Max drawdown | Benchmark max drawdown | Trades | Costs/yr | Cash interest share of profit | Gates passed |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['strategy']} | {pc(r['cagr'])} | {pc(r['bench_cagr'])} | {pc(r['oos_cagr'])} | {pc(r['bench_oos_cagr'])} | {pc(r['max_drawdown'])} | {pc(r['bench_max_drawdown'])} | {r['trades']} | {pc(r['costs_pct_year'])} | {pc(r['interest_share'])} | {r['passed']} of 8 |" for r in rows]
    md += ["", "## Gate matrix (the eight gates of RESEARCH_CHARTER.md, unchanged)", "",
           "| Strategy | " + " | ".join(f"G{i}" for i in range(1, 9)) + " | Verdict |", "|---|" + "---|" * 9]
    short = {"PASS": "PASS", "FAIL": "FAIL", "NOT_EVALUATED": "n/e"}
    md += [f"| {r['strategy']} | " + " | ".join(short[r["gates"][i]] for i in range(1, 9)) + f" | {r['verdict']} |" for r in rows]
    md += ["", "n/e = not evaluated (counts as not passed). Gate 2 fails by construction for these four strategies: they were tested before the charter existed.", "",
           "## What this does and does not show", "",
           "- An edge may only be claimed if all eight gates pass. " + ("**At least one strategy passed all eight gates: independent validation is still required.**" if any(r["edge"] for r in rows) else "**No strategy passed all eight gates, so no edge is claimed.**"),
           "- Tax scenarios (gate 4), sector limits (gate 6) and paper trading (gate 8) are not yet available.",
           "- Prices are from a secondary source and were not reconciled with the exchange (see Data status).",
           "- Results are not a prediction. Not investment advice."]
    (Path(out) / "PHASE2_SUMMARY.md").write_text("\n".join(md), encoding="utf-8")
