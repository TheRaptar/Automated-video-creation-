from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .alphalab import bh_fdr, evaluate_factor, factor_corr, fwd_returns, norm_p
from .factors import FACTOR_INFO


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _f(x, d=3):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def _pc(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def run_lab(p, factors: dict, horizons, oos_fraction, out, events=None, event_df=None, macro_df=None, label=""):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cut = p.dates[int(len(p.dates) * (1 - oos_fraction))]
    rows, results = [], {}
    for h in horizons:
        fwd = fwd_returns(p, h)
        for name, f in factors.items():
            r = evaluate_factor(f, fwd, h, cut)
            results[(name, h)] = r
            rows.append({"factor": name, "h": h, **{k: r[k] for k in ("top_excess_gross", "top_excess_net", "long_short", "turnover")},
                         "ic": r["ic_all"]["mean"], "t": r["ic_all"]["t"], "hit": r["ic_all"]["hit"], "n": r["ic_all"]["n"],
                         "ic_is": r["ic_is"]["mean"], "ic_oos": r["ic_oos"]["mean"], "t_oos": r["ic_oos"]["t"]})
    tab = pd.DataFrame(rows)
    tab["p"] = tab["t"].map(norm_p)
    tab["fdr_pass"] = bh_fdr(tab["p"].to_numpy(), 0.10)
    tab["oos_same_sign"] = np.sign(tab.ic_is.fillna(0)) == np.sign(tab.ic_oos.fillna(0))
    tab["verdict"] = np.where(tab.fdr_pass & tab.oos_same_sign & (tab.top_excess_net > 0) & (tab.ic_oos.abs() > 0.01) & (np.sign(tab.ic) == np.sign(tab.ic_oos)),
                              "CANDIDATE", np.where(tab.fdr_pass & ~tab.oos_same_sign, "faded out-of-sample", "no evidence"))
    tab = tab.reindex(tab.t.abs().sort_values(ascending=False).index)
    tab.to_csv(out / "factor_table.csv", index=False)

    show = pd.DataFrame({
        "factor": tab.factor, "family": tab.factor.map(lambda n: FACTOR_INFO.get(n, ("custom", ""))[0]), "h": tab.h,
        "IC": tab.ic.map(_f), "t": tab.t.map(lambda x: _f(x, 2)), "IC in-sample": tab.ic_is.map(_f), "IC out-of-sample": tab.ic_oos.map(_f),
        "top-quintile excess/yr (after costs)": tab.top_excess_net.map(_pc), "turnover": tab.turnover.map(_pc),
        "survives FDR": tab.fdr_pass.map({True: "yes", False: "no"}), "verdict": tab.verdict})

    # charts
    best = tab.drop_duplicates("factor").head(18)
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(best.factor[::-1], best.ic[::-1], color=["tab:green" if v == "CANDIDATE" else "tab:grey" for v in best.verdict[::-1]])
    ax.axvline(0, color="k", lw=.8); ax.set_xlabel("Rank IC (positive = factor predicts returns the way hypothesised)")
    ax.set_title("Factor information coefficients (green = survives all checks)"); fig.tight_layout(); fig.savefig(out / "ic_bars.png", dpi=110); plt.close(fig)
    top3 = tab.head(3)[["factor", "h"]].itertuples(index=False)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, (n, h) in zip(axes, top3):
        qm = results[(n, h)]["q_means"].fillna(0)
        (1 + qm).cumprod().plot(ax=ax, lw=1.2); ax.set_title(f"{n} ({h}d): growth of quintiles"); ax.set_yscale("log"); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out / "quintiles.png", dpi=110); plt.close(fig)
    corr = factor_corr(factors)
    fig, ax = plt.subplots(figsize=(8, 7)); im = ax.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=90, fontsize=7); ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index, fontsize=7)
    fig.colorbar(im); ax.set_title("How much do the factors overlap?"); fig.tight_layout(); fig.savefig(out / "factor_overlap.png", dpi=110); plt.close(fig)

    n_cand = int((tab.verdict == "CANDIDATE").sum())
    md = [f"# Alpha lab report", "", f"*Data:* {label} - {len(p.symbols)} stocks, {p.dates[0].date()} to {p.dates[-1].date()}. "
          f"Out-of-sample = last {oos_fraction:.0%} (from {cut.date()}). Horizons tested: {list(horizons)} trading days.", "",
          "## How to read this", "",
          "- **IC** = rank correlation between the factor today and the return over the next *h* days, across stocks. "
          "0.02-0.05 is a respectable real-world value; above 0.1 is almost always a bug or look-ahead.",
          "- **t** uses non-overlapping windows. With many factors tested, some pass by luck, so **survives FDR** applies a "
          "false-discovery correction.", "- **CANDIDATE** needs ALL of: survives FDR, same sign in-sample and out-of-sample, "
          "positive after-cost excess return. Everything else is noise or faded.", "",
          f"**{n_cand} of {len(tab)} factor/horizon combinations are candidates.** "
          + ("" if n_cand else "Finding nothing is a normal, useful result: it tells you not to trade on these ideas."), "",
          "![ic](ic_bars.png)", "", md_table(show), "", "![q](quintiles.png)", "", "![overlap](factor_overlap.png)"]
    if event_df is not None and len(event_df):
        ev = event_df.copy(); ev["avg_excess"] = ev.avg_excess.map(_pc); ev["hit_rate"] = ev.hit_rate.map(_pc)
        ev["t"] = ev.t.map(lambda x: _f(x, 2)); ev["p"] = ev.p.map(lambda x: _f(x, 3))
        md += ["", "## Event studies: liquidity sweeps and supply/demand zones", "",
               "Average return *relative to the other stocks that day* after each event. Overlapping windows and clustered events "
               "inflate t-statistics, so only trust |t| above about 3 together with a hit rate clearly away from 50%.", "", md_table(ev)]
    if macro_df is not None and len(macro_df):
        mm = macro_df.copy(); mm["rank_corr_with_next_month"] = mm.rank_corr_with_next_month.map(_f)
        mm["t"] = mm.t.map(lambda x: _f(x, 2)); mm["p"] = mm.p.map(lambda x: _f(x, 3))
        md += ["", "## Macro top-down: do these variables predict the next month's index return?", "",
               "Few independent months, so only large effects are detectable.", "", md_table(mm)]
    md += ["", "## Not testable with free daily data (so NOT included)", "",
           "- Iceberg orders and dark-pool prints: India has no dark pools, and hidden order size is not visible to retail.",
           "- True order flow / liquidity sweeps at tick level: needs level-2/3 or tick history. Start recording it (Phase 2) and test later.",
           "- Fundamentals: need point-in-time data. Use `fundamentals.py` with your own dated CSV; never use today's ratios on past dates.",
           "- Not investment advice. Past statistical relationships can vanish."]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return tab
