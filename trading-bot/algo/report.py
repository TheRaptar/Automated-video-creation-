import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .metrics import performance, trade_stats, yearly_returns


def _pct(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def _num(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def write_report(out, res, panel, cut, rf, robust_df, data_label, universe_n):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cap = res.config.capital
    bench = (panel.benchmark.reindex(res.equity.index).ffill() / panel.benchmark.dropna().iloc[0]) * cap
    bench = bench / bench.iloc[0] * cap
    full, bfull = performance(res.equity, rf), performance(bench, rf)
    i_eq, o_eq = res.equity.loc[:cut], res.equity.loc[cut:]
    i_p, o_p = performance(i_eq, rf), performance(o_eq, rf)
    b_o = performance(bench.loc[cut:], rf)
    ts = trade_stats(res.trades)

    # ---- charts
    fig, ax = plt.subplots(2, 1, figsize=(11, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(res.equity.index, res.equity / cap, label=f"{res.strategy} (after costs)", lw=1.6)
    ax[0].plot(bench.index, bench / cap, label="Benchmark buy & hold", lw=1.2, alpha=.8)
    ax[0].axvline(cut, color="grey", ls="--", lw=1); ax[0].text(cut, ax[0].get_ylim()[1] * .95, " out-of-sample ->", color="grey")
    ax[0].set_yscale("log"); ax[0].set_ylabel("Growth of 1 (log)"); ax[0].legend(); ax[0].grid(alpha=.3)
    dd = res.equity / res.equity.cummax() - 1
    ax[1].fill_between(dd.index, dd * 100, 0, color="tab:red", alpha=.4); ax[1].set_ylabel("Drawdown %"); ax[1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(out / "equity.png", dpi=110); plt.close(fig)

    res.trades.to_csv(out / "trades.csv", index=False)
    res.open_positions.to_csv(out / "open_positions.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(
        {"full": full, "in_sample": i_p, "out_of_sample": o_p, "benchmark": bfull, "trades": ts,
         "total_costs": res.total_costs}, indent=2, default=float), encoding="utf-8")

    # ---- reality checks
    years = full["years"]
    flags = []
    if ts.get("trades", 0) < 100:
        flags.append(f"Only {ts.get('trades', 0)} closed trades - too few to trust any statistic.")
    if full["cagr"] <= bfull["cagr"]:
        flags.append("The strategy did NOT beat simply holding the benchmark after costs.")
    if o_p["sharpe"] < 0.5 * i_p["sharpe"] if np.isfinite(i_p["sharpe"]) and i_p["sharpe"] > 0 else False:
        flags.append("Out-of-sample Sharpe is less than half of in-sample: classic sign of overfitting.")
    if o_p["cagr"] < b_o["cagr"]:
        flags.append("Out-of-sample, the strategy lagged the benchmark.")
    if full["max_drawdown"] < -0.25:
        flags.append(f"Max drawdown {_pct(full['max_drawdown'])}: could you stomach that with real money?")
    if "yahoo" in data_label.lower() or "csv" in data_label.lower():
        flags.append("Survivorship bias: the stock list is TODAY's large caps, which flatters past results.")
    if robust_df is not None and len(robust_df):
        share = (robust_df.oos_sharpe > 0.3).mean()
        if share < 0.6:
            flags.append(f"Only {share:.0%} of tested settings had a decent out-of-sample Sharpe: the idea is fragile.")

    row = lambda name, k, f: f"| {name} | " + " | ".join(f(d[k]) for d in (full, bfull, i_p, o_p)) + " |"
    md = [f"# Backtest report: {res.strategy}", "",
          f"*Data:* {data_label} - {universe_n} stocks, {res.equity.index[0].date()} to {res.equity.index[-1].date()} "
          f"({years:.1f} years). *Capital:* Rs {cap:,.0f}. *Max positions:* {res.config.max_positions}. "
          f"*Params:* `{res.params}`", "",
          "| Metric | Strategy | Benchmark | Strategy in-sample | Strategy out-of-sample |", "|---|---|---|---|---|",
          row("CAGR", "cagr", _pct), row("Total return", "total_return", _pct), row("Volatility", "volatility", _pct),
          row("Sharpe", "sharpe", _num), row("Sortino", "sortino", _num), row("Max drawdown", "max_drawdown", _pct),
          row("Calmar", "calmar", _num), "",
          f"**Trades:** {ts.get('trades', 0)} closed ({ts.get('trades', 0) / years:.0f}/year), win rate {_pct(ts.get('win_rate'))}, "
          f"avg win {_pct(ts.get('avg_win'))}, avg loss {_pct(ts.get('avg_loss'))}, profit factor {_num(ts.get('profit_factor'))}, "
          f"avg holding {_num(ts.get('avg_days_held'), 0)} days, {ts.get('stop_exits', 0)} stop-outs.  ",
          f"**Costs paid:** Rs {res.total_costs:,.0f} ({res.total_costs / cap / years * 100:.2f}% of capital per year) - "
          f"STT, stamp duty, exchange fees, GST, DP charges, plus {res.config.slippage_bps:g} bps slippage per fill.  ",
          f"**Average exposure:** {res.exposure.mean():.0%} invested.", "", "![equity](equity.png)", "",
          "## Calendar-year returns", "", "| Year | Strategy | Benchmark |", "|---|---|---|"]
    ys, yb = yearly_returns(res.equity), yearly_returns(bench)
    for y in ys.index:
        md.append(f"| {y.year} | {_pct(ys[y])} | {_pct(yb.get(y))} |")
    if robust_df is not None and len(robust_df):
        best = robust_df.sort_values("is_sharpe", ascending=False).iloc[0]
        md += ["", "## Robustness: does it work across settings, or only for one lucky one?", "",
               f"Best settings *by in-sample Sharpe* ({', '.join(f'{k}={best[k]:g}' for k in robust_df.columns if k not in ('is_cagr','is_sharpe','is_maxdd','oos_cagr','oos_sharpe','oos_maxdd','trades'))}): "
               f"in-sample Sharpe {_num(best.is_sharpe)} -> out-of-sample Sharpe **{_num(best.oos_sharpe)}**. "
               f"Median out-of-sample Sharpe across all {len(robust_df)} settings: {_num(robust_df.oos_sharpe.median())}.", "",
               robust_df.round(3).to_markdown(index=False) if hasattr(robust_df, "to_markdown") and _has_tabulate() else
               "```\n" + robust_df.round(3).to_string(index=False) + "\n```"]
    md += ["", "## Reality checks", ""] + ([f"- {f}" for f in flags] or ["- No automatic red flags - which is NOT proof the strategy works."])
    md += ["", "## Read this before trusting any number", "",
           "- A backtest is a story about the past, not a forecast. Markets change; edges fade.",
           "- Prices are adjusted for splits and dividends; fills assume you can trade at the next open plus slippage.",
           "- Tax is not included: delivery gains held under 12 months are taxed as short-term capital gains. Keep records / ask a CA.",
           "- Not investment advice. No result here guarantees future profit."]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return full, bfull, flags


def _has_tabulate():
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False
