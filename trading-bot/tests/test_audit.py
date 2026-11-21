import numpy as np
import pandas as pd

from algo.audit import audit_frames, audit_symbol

IDX = pd.bdate_range("2018-01-01", periods=900)


def clean_frame(seed=0, idx=IDX):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx))))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, len(idx)))
    high = np.maximum(open_, close) * 1.004
    low = np.minimum(open_, close) * 0.996
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.lognormal(14, 0.3, len(idx))}, index=idx)


def checks(sym="X", df=None, splits=None, bench=None, cal=IDX):
    return {r["check"] for r in audit_symbol(sym, df if df is not None else clean_frame(), cal, splits, bench)}


def test_clean_data_raises_no_flags():
    issues, scores, summary = audit_frames({f"S{i}": clean_frame(i) for i in range(6)})
    assert issues.empty and (scores["class"] == "CLEAN").all() and summary["clean"] == 6


def test_unadjusted_5_to_1_split_is_caught_and_excluded():
    df = clean_frame()
    df.loc[df.index[400]:, ["open", "high", "low", "close"]] /= 5
    df.loc[df.index[400]:, "volume"] *= 5
    assert "possible_unadjusted_split_or_bonus" in checks(df=df)
    _, scores, _ = audit_frames({"A": df, "B": clean_frame(1)})
    assert scores.set_index("symbol").loc["A", "class"] == "EXCLUDE"


def test_recorded_split_date_with_jump_is_flagged_unadjusted():
    df = clean_frame()
    df.loc[df.index[300]:, ["open", "high", "low", "close"]] *= 0.5
    splits = pd.Series([2.0], index=[df.index[300]])
    assert "unadjusted_split" in checks(df=df, splits=splits)


def test_genuine_crash_without_volume_jump_goes_to_review_not_exclude():
    df = clean_frame()
    df.loc[df.index[500]:, ["open", "high", "low", "close"]] *= 0.55
    c = checks(df=df)
    assert "extreme_move" in c and "possible_unadjusted_split_or_bonus" not in c
    _, scores, _ = audit_frames({"A": df, "B": clean_frame(1)})
    assert scores.set_index("symbol").loc["A", "class"] == "REVIEW"


def test_gap_zero_price_ohlc_duplicates_stale_and_early_end():
    df = clean_frame().drop(clean_frame().index[200:240])
    assert "large_gap" in checks(df=df)
    z = clean_frame(); z.iloc[50, z.columns.get_loc("close")] = 0.0
    assert "non_positive_price" in checks(df=z)
    o = clean_frame(); o.iloc[60, o.columns.get_loc("high")] = o.iloc[60]["low"] * 0.9
    assert "inconsistent_ohlc" in checks(df=o)
    dup = pd.concat([clean_frame(), clean_frame().iloc[[10]]])
    assert "index_order_or_duplicates" in checks(df=dup)
    st = clean_frame(); st.iloc[100:110, st.columns.get_loc("close")] = st.iloc[100]["close"]
    assert "stale_price" in checks(df=st)
    assert "series_ends_early" in checks(df=clean_frame().iloc[:700])


def test_low_correlation_with_index_is_low_severity_only():
    bench = pd.Series(np.random.default_rng(9).normal(0, 0.01, len(IDX)), index=IDX)
    issues, scores, _ = audit_frames({"A": clean_frame(0), "B": clean_frame(1), "C": clean_frame(2)}, benchmark=100 * (1 + bench).cumprod())
    assert set(issues.severity) <= {"LOW"} and (scores["class"] == "CLEAN").all()


def test_manual_override_is_respected_and_logged():
    df = clean_frame(); df.loc[df.index[500]:, ["open", "high", "low", "close"]] *= 0.55
    d = df.index[500].strftime("%Y-%m-%d")
    issues, scores, _ = audit_frames({"A": df, "B": clean_frame(1)}, overrides={"A": {"allow_dates": [d], "note": "verified demerger"}})
    assert issues["overridden"].any() and scores.set_index("symbol").loc["A", "class"] == "CLEAN"
