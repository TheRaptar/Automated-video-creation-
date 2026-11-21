"""
Historical price-data audit. Looks for the failures that silently corrupt backtests:
unadjusted splits/bonuses/demergers, gaps, impossible prices, stale quotes, and series that stop early (delisted/merged/renamed).
Every finding is a row (symbol, date, check, severity, detail). Symbols are classified CLEAN / REVIEW / EXCLUDE.
Nothing is changed silently: exclusions are only applied when the caller asks, and are logged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

T = dict(big_move=0.25, huge_move=0.40, stale_run=5, zero_vol_share=0.02, gap_days=5, big_gap=20,
         ohlc_tol=1e-6, vol_jump=1.5, end_gap_days=10, min_corr=0.15)
SPLIT_RATIOS = [1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1 / 20, 2 / 3, 3 / 4, 4 / 5]        # price after k:1 splits / bonuses
EXCLUDE_CHECKS = {"index_order_or_duplicates", "non_positive_price", "possible_unadjusted_split_or_bonus",
                  "unadjusted_split", "large_gap"}


def _row(sym, date, check, sev, detail):
    return {"symbol": sym, "date": None if date is None else pd.Timestamp(date), "check": check, "severity": sev, "detail": detail}


def _looks_like_split(ratio: float) -> bool:
    if not np.isfinite(ratio) or ratio <= 0:
        return False
    return any(abs(ratio - r) / r < 0.06 for r in SPLIT_RATIOS) or any(abs(1 / ratio - k) / k < 0.06 for k in (2, 3, 4, 5, 10, 20))


def audit_symbol(sym: str, df: pd.DataFrame, calendar: pd.DatetimeIndex, splits: pd.Series | None = None,
                 bench_ret: pd.Series | None = None) -> list:
    out = []
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        out.append(_row(sym, None, "index_order_or_duplicates", "HIGH", "dates are unsorted or duplicated"))
    d = df[~df.index.duplicated()].sort_index()
    if d.empty:
        return out + [_row(sym, None, "empty", "HIGH", "no rows")]
    o, h, l, c, v = (d[k] for k in ("open", "high", "low", "close", "volume"))

    nonpos = d[["open", "high", "low", "close"]].le(0).any(axis=1)
    for dt in d.index[nonpos][:20]:
        out.append(_row(sym, dt, "non_positive_price", "HIGH", "a price is zero or negative"))
    n_nan = int(d[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    if n_nan:
        out.append(_row(sym, None, "missing_ohlc_values", "MEDIUM", f"{n_nan} rows have missing prices"))

    tol = T["ohlc_tol"]
    bad_hi = h < np.maximum.reduce([o, c, l]) * (1 - tol)
    bad_lo = l > np.minimum.reduce([o, c, h]) * (1 + tol)
    for name, bad in (("high_below_price", bad_hi), ("low_above_price", bad_lo)):
        if bad.any():
            out.append(_row(sym, bad[bad].index[0], "inconsistent_ohlc", "MEDIUM", f"{int(bad.sum())} days where {name.replace('_', ' ')}"))

    ret = c.pct_change()
    ratio = c / c.shift(1)
    big = ret.abs() > T["big_move"]
    for dt in d.index[big.fillna(False)]:
        i = d.index.get_loc(dt)
        before, after = v.iloc[max(0, i - 20):i].median(), v.iloc[i:i + 20].median()
        vr = after / before if before and before > 0 and np.isfinite(after) else np.nan
        rec_split = splits is not None and len(splits) and (abs((splits.index - dt).days) <= 3).any()
        if rec_split:
            out.append(_row(sym, dt, "unadjusted_split", "HIGH", f"price moved {ret[dt]:+.0%} on a recorded split date: prices look UNADJUSTED"))
        elif _looks_like_split(ratio[dt]) and np.isfinite(vr) and vr >= T["vol_jump"]:
            out.append(_row(sym, dt, "possible_unadjusted_split_or_bonus", "HIGH",
                            f"price ratio {ratio[dt]:.3f} with volume x{vr:.1f}: typical of an unadjusted split/bonus"))
        else:
            sev = "HIGH" if abs(ret[dt]) > T["huge_move"] else "MEDIUM"
            out.append(_row(sym, dt, "extreme_move", sev, f"one-day move {ret[dt]:+.0%} (volume ratio {vr:.1f}): genuine event, demerger or bad data - review"))

    active = v.notna()
    zero_share = float((v.fillna(0) == 0).sum() / max(1, active.sum()))
    if zero_share > T["zero_vol_share"]:
        out.append(_row(sym, None, "zero_volume_days", "MEDIUM", f"{zero_share:.1%} of days have zero volume"))

    same = c.diff().eq(0)
    grp = (~same).cumsum()
    for _, run in same[same].groupby(grp[same]):
        if len(run) >= T["stale_run"]:
            dt = run.index[0]
            vol = v.loc[run.index].mean()
            out.append(_row(sym, dt, "stale_price" if vol and vol > 0 else "no_trading_period", "MEDIUM" if vol and vol > 0 else "LOW",
                            f"close unchanged for {len(run)} days (avg volume {vol:,.0f})"))

    span = calendar[(calendar >= d.index[0]) & (calendar <= d.index[-1])]
    missing = span.difference(d.index)
    if len(missing):
        pos = span.get_indexer(missing)
        runs = np.split(pos, np.where(np.diff(pos) != 1)[0] + 1)
        for r in runs:
            if len(r) > T["gap_days"]:
                out.append(_row(sym, span[r[0]], "large_gap" if len(r) > T["big_gap"] else "gap", "HIGH" if len(r) > T["big_gap"] else "MEDIUM",
                                f"{len(r)} consecutive trading days missing"))
    if d.index[-1] < calendar[-1] - pd.Timedelta(days=T["end_gap_days"]):
        out.append(_row(sym, d.index[-1], "series_ends_early", "LOW", "history stops before the end of the calendar: delisted, merged or renamed?"))

    if bench_ret is not None:
        j = pd.concat([ret, bench_ret], axis=1, join="inner").dropna()
        if len(j) >= 250 and j.iloc[:, 0].corr(j.iloc[:, 1]) < T["min_corr"]:
            out.append(_row(sym, None, "low_correlation_with_index", "LOW", f"daily correlation with the index only {j.iloc[:, 0].corr(j.iloc[:, 1]):.2f}"))
    return out


def audit_frames(frames: dict, splits: dict | None = None, benchmark: pd.Series | None = None, overrides: dict | None = None):
    """Returns (issues DataFrame, per-symbol scores DataFrame, dataset summary dict)."""
    cal_counts = pd.concat([f.index.to_series() for f in frames.values()]).value_counts()
    calendar = pd.DatetimeIndex(sorted(cal_counts[cal_counts >= max(2, 0.5 * len(frames))].index))
    bret = benchmark.pct_change() if benchmark is not None else None
    rows = []
    for sym, df in frames.items():
        rows += audit_symbol(sym, df, calendar, (splits or {}).get(sym), bret)
    issues = pd.DataFrame(rows, columns=["symbol", "date", "check", "severity", "detail"])
    allow = {(s, pd.Timestamp(d)) for s, spec in (overrides or {}).items() for d in spec.get("allow_dates", [])}
    if allow and not issues.empty:
        issues["overridden"] = [(r.symbol, r.date) in allow for r in issues.itertuples()]
    else:
        issues["overridden"] = False
    live = issues[~issues["overridden"]]
    score_rows = []
    for sym, df in frames.items():
        s = live[live.symbol == sym]
        sev = s.severity.value_counts()
        excl = s.check.isin(EXCLUDE_CHECKS).any()
        review = (sev.get("HIGH", 0) > 0) or (sev.get("MEDIUM", 0) >= 3)
        score_rows.append({"symbol": sym, "rows": len(df), "start": df.index.min().date(), "end": df.index.max().date(),
                           "high": int(sev.get("HIGH", 0)), "medium": int(sev.get("MEDIUM", 0)), "low": int(sev.get("LOW", 0)),
                           "class": "EXCLUDE" if excl else "REVIEW" if review else "CLEAN",
                           "first_issue": "" if s.empty else s.iloc[0]["check"]})
    scores = pd.DataFrame(score_rows)
    per_date = pd.concat([f["close"].dropna().index.to_series() for f in frames.values()]).value_counts().sort_index()
    summary = {"symbols": len(frames), "clean": int((scores["class"] == "CLEAN").sum()), "review": int((scores["class"] == "REVIEW").sum()),
               "exclude": int((scores["class"] == "EXCLUDE").sum()), "ended_early": int((issues.check == "series_ends_early").sum()),
               "calendar_days": len(calendar), "min_symbols_per_day": int(per_date.min()) if len(per_date) else 0}
    return issues, scores, summary


def write_audit_report(out, issues, scores, summary, manifest=None, title="Historical data audit") -> None:
    from pathlib import Path
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    issues.to_csv(out / "issues.csv", index=False)
    scores.to_csv(out / "symbol_scores.csv", index=False)
    md = [f"# {title}", "",
          f"**{summary['symbols']} symbols**: {summary['clean']} clean, {summary['review']} need review, {summary['exclude']} should be excluded. "
          f"{summary['ended_early']} series end before the calendar does (delisted / merged / renamed). "
          f"Trading calendar inferred from the data: {summary['calendar_days']} days.", "",
          "A CLEAN verdict means *no automated check fired*. It is not proof that the prices match the exchange.", ""]
    if manifest is not None:
        md += ["## Data status", "", manifest.to_markdown(), ""]
    md += ["## Findings by check", ""]
    if issues.empty:
        md.append("No findings.")
    else:
        by = issues.groupby(["check", "severity"]).size().reset_index(name="count").sort_values(["severity", "count"], ascending=[True, False])
        md += ["| check | severity | count |", "|---|---|---|"] + [f"| {r.check} | {r.severity} | {r['count']} |" for _, r in by.iterrows()]
    bad = scores[scores["class"] != "CLEAN"].sort_values(["class", "high"], ascending=[True, False])
    md += ["", "## Symbols to exclude or review", ""]
    if bad.empty:
        md.append("None.")
    else:
        md += ["| symbol | class | high | medium | first issue | data from | to |", "|---|---|---|---|---|---|---|"]
        md += [f"| {r.symbol} | {r['class']} | {r.high} | {r.medium} | {r.first_issue} | {r.start} | {r.end} |" for _, r in bad.head(80).iterrows()]
    hi = issues[(issues.severity == "HIGH") & (~issues["overridden"])].head(40)
    if len(hi):
        md += ["", "## High-severity findings (first 40)", "", "| symbol | date | check | detail |", "|---|---|---|---|"]
        md += [f"| {r.symbol} | {'' if pd.isna(r.date) else r.date.date()} | {r.check} | {r.detail} |" for r in hi.itertuples()]
    ended = issues[issues.check == "series_ends_early"]
    if len(ended):
        md += ["", "## Series that end early (candidate delisted / merged / renamed names)", "",
               ", ".join(f"{r.symbol} (to {r.date.date()})" for r in ended.itertuples())]
    (out / "summary.md").write_text("\n".join(md), encoding="utf-8")
