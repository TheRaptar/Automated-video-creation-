#!/usr/bin/env python3
"""
Is the market filter (trend or trend + India VIX) skilful on the INDEX, or just lucky?
  python run_timing_test.py --data yahoo --regime trend
  python run_timing_test.py --data yahoo --regime macro
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from algo.loader import load_benchmark
from algo.macro import risk_on
from algo.timing import timing_test, timing_verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="synthetic")
    ap.add_argument("--regime", choices=["trend", "macro"], default="trend")
    ap.add_argument("--years", type=float, default=15)
    ap.add_argument("--null-runs", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--cash-yield", type=float, default=0.06)
    ap.add_argument("--div-yield", type=float, default=0.013, help="approximate index dividend yield added to the price index")
    ap.add_argument("--switch-cost", type=float, default=0.001, help="cost of one switch in/out (fees, spread); check your ETF's STT/charges")
    ap.add_argument("--out", default="reports/timing")
    a = ap.parse_args()

    bench, macro, label = load_benchmark(a.data, a.years, macro=(a.regime == "macro"))
    gate = risk_on(macro if a.regime == "macro" else None, bench)
    res = timing_test(bench, gate, a.null_runs, a.seed, a.cash_yield, a.div_yield, a.switch_cost)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    r, b, nl = res["real"], res["buy_hold"], res["null"]
    pc = lambda x: f"{x * 100:.1f}%"
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for a_, k, t in ((ax[0], "sharpe", "Sharpe"), (ax[1], "cagr", "CAGR"), (ax[2], "max_drawdown", "Max drawdown")):
        a_.hist(nl[k], bins=40, color="tab:grey", alpha=.8); a_.axvline(r[k], color="tab:green", lw=2, label="real filter")
        a_.axvline(b[k], color="tab:red", lw=1.5, ls="--", label="buy & hold index"); a_.set_title(f"{t}: random timing vs real"); a_.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "timing_null.png", dpi=110); plt.close(fig)
    md = [f"# Market-filter timing test ({a.regime})", "",
          f"*Data:* {label}, {bench.index[0].date()} to {bench.index[-1].date()}. Index held when risk-on, cash at {a.cash_yield:.1%} when off; "
          f"dividends approximated at {a.div_yield:.1%}/yr; {a.switch_cost:.2%} cost per switch. *Seed:* {a.seed}. "
          f"The filter was invested {res['exposure']:.0%} of the time with {res['switches']} switches.", "",
          "| | CAGR | Volatility | Sharpe | Max drawdown |", "|---|---|---|---|---|",
          f"| Index with the filter | {pc(r['cagr'])} | {pc(r['volatility'])} | {r['sharpe']:.2f} | {pc(r['max_drawdown'])} |",
          f"| Index buy & hold | {pc(b['cagr'])} | {pc(b['volatility'])} | {b['sharpe']:.2f} | {pc(b['max_drawdown'])} |",
          f"| Random timing, median (5th-95th) | {pc(nl.cagr.median())} ({pc(nl.cagr.quantile(.05))} to {pc(nl.cagr.quantile(.95))}) | | "
          f"{nl.sharpe.median():.2f} ({nl.sharpe.quantile(.05):.2f} to {nl.sharpe.quantile(.95):.2f}) | {pc(nl.max_drawdown.median())} ({pc(nl.max_drawdown.quantile(.05))} to {pc(nl.max_drawdown.quantile(.95))}) |", "",
          f"**Verdict:** {timing_verdict(res)}", "",
          f"p-values (random timing does at least as well): Sharpe {res['p_sharpe']:.3f}, CAGR {res['p_cagr']:.3f}, drawdown {res['p_drawdown']:.3f}.", "",
          "![null](timing_null.png)", "",
          "Few independent regime changes means low statistical power: a 'no evidence' result does not prove the filter is useless, and a good one can still be luck. Not investment advice."]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(timing_verdict(res)); print(f"Report: {a.out}/summary.md")


if __name__ == "__main__":
    main()
