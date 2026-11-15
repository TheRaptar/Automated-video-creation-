from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import equal_weight_index
from .metrics import performance
from .montecarlo import block_bootstrap, null_verdict


def _pc(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def _n(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def write_mc_report(out, panel, res: dict, ref, cfg, label, rf=0.06, boot_n=2000):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cfg.capital
    real, ctrl, null = res["real"], res["control"], res["null"]
    idx = res["real_result"].equity.index
    bench = (panel.benchmark.reindex(idx).ffill() / panel.benchmark.dropna().iloc[0])
    bench = bench / bench.iloc[0] * cap
    ew = equal_weight_index(panel.close).reindex(idx).ffill()
    ew = ew / ew.iloc[0] * cap
    pidx, pew = performance(bench, rf), performance(ew, rf)
    boot = block_bootstrap(res["real_result"].equity, {"equal-weight universe, always invested": ew,
                                                       "same-timing equal-weight control": res["control_result"].equity},
                           n=boot_n, seed=res["seed"], rf=rf)

    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    for a, key, title, fmt in ((ax[0], "sharpe", "Sharpe ratio", "{:.2f}"), (ax[1], "cagr", "CAGR", "{:.1%}")):
        a.hist(null[key], bins=30, color="tab:grey", alpha=.8)
        a.axvline(real[key], color="tab:green", lw=2, label="our strategy " + fmt.format(real[key]))
        a.axvline(ctrl[key], color="tab:blue", lw=1.5, ls="--", label="all stocks, same timing " + fmt.format(ctrl[key]))
        a.set_title(f"{title}: {res['n']} random-stock-picking runs"); a.legend(fontsize=8); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out / "null_distribution.png", dpi=110); plt.close(fig)
    null.to_csv(out / "null_runs.csv", index=False)

    md = [f"# Monte Carlo report: {ref.name}", "",
          f"*Data:* {label} - {len(panel.symbols)} stocks, {idx[0].date()} to {idx[-1].date()}. *Params:* `{ref.params()}`. "
          f"*Seed:* {res['seed']} (re-run with the same seed to get identical numbers).", "",
          "## 1. Is it stock selection, or just timing and cash? (null test)", "",
          f"We ran the strategy **{res['n']} times picking stocks at random** - same regime filter, same number of holdings, same turnover, "
          f"same costs. Where does the real strategy rank?", "",
          "| | Strategy | Random picking: median | 5th-95th percentile | Beats random in |", "|---|---|---|---|---|",
          f"| Sharpe | {_n(real['sharpe'])} | {_n(null.sharpe.median())} | {_n(null.sharpe.quantile(.05))} to {_n(null.sharpe.quantile(.95))} | {res['pct_sharpe']:.0%} of runs |",
          f"| CAGR | {_pc(real['cagr'])} | {_pc(null.cagr.median())} | {_pc(null.cagr.quantile(.05))} to {_pc(null.cagr.quantile(.95))} | {res['pct_cagr']:.0%} of runs |",
          f"| Max drawdown | {_pc(real['max_drawdown'])} | {_pc(null.max_drawdown.median())} | {_pc(null.max_drawdown.quantile(.05))} to {_pc(null.max_drawdown.quantile(.95))} | |", "",
          f"**Verdict:** {null_verdict(res['p_sharpe'])}", "",
          f"One-sided p-values: Sharpe {res['p_sharpe']:.3f}, CAGR {res['p_cagr']:.3f}. Costs paid: strategy Rs {res['real_costs']:,.0f} vs random median Rs {null.costs.median():,.0f}.", "",
          "![null](null_distribution.png)", "",
          "## 2. Reference points", "",
          "| | CAGR | Volatility | Sharpe | Max drawdown |", "|---|---|---|---|---|"]
    for name, d in (("Our strategy", real), ("All stocks equal-weight, same timing + cash (control)", ctrl),
                    ("Equal-weight universe, always invested", pew), ("Index, price only", pidx)):
        md.append(f"| {name} | {_pc(d['cagr'])} | {_pc(d['volatility'])} | {_n(d['sharpe'])} | {_pc(d['max_drawdown'])} |")
    md += ["", "The control isolates what *timing + cash* alone earn. The equal-weight universe is flattered by survivorship bias "
           "(today's winners), but random picks and our picks come from that same list, so the null test is fair.", "",
           "## 3. Error bars (block bootstrap of daily returns)", "",
           f"{boot['n']} resamples in {boot['block']}-day blocks (keeps volatility clustering), seed {boot['seed']}.", "",
           "| | 5th percentile | median | 95th percentile |", "|---|---|---|---|",
           f"| CAGR | {_pc(boot['cagr'][0])} | {_pc(boot['cagr'][1])} | {_pc(boot['cagr'][2])} |",
           f"| Sharpe | {_n(boot['sharpe'][0])} | {_n(boot['sharpe'][1])} | {_n(boot['sharpe'][2])} |",
           f"| Max drawdown | {_pc(boot['max_drawdown'][0])} | {_pc(boot['max_drawdown'][1])} | {_pc(boot['max_drawdown'][2])} |", ""]
    for k, v in boot["p_beats"].items():
        md.append(f"- Probability its CAGR beats the {k}: **{v:.0%}** (50% would mean no real difference).")
    md += ["", "## Read this before trusting any number", "",
           "- This is a simulation built from past data, not a prediction. It cannot see regime changes, new rules or crises.",
           "- Passing the null test means 'better than random picking in this sample', not 'will make money'.",
           "- Not investment advice."]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return boot
