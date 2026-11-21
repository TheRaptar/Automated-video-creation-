import io
import zipfile

import numpy as np
import pandas as pd

from algo.data import synthetic_panel
from algo.engine import Config, run_backtest
from algo.strategies import MultiFactor, TrendMomentum
from algo.universe import (Membership, from_snapshots, index_key_from_filename, parse_constituent_csv, parse_incl_excl,
                           parse_monthly_zip, reconstruct_backwards)


def changes():
    return pd.DataFrame({"date": pd.to_datetime(["2018-09-28", "2020-03-31"]), "symbol": ["D", "C"], "action": ["EXCLUDE", "INCLUDE"]})


def test_reconstruction_undoes_changes_newest_first():
    m = reconstruct_backwards("nifty50", {"A", "B", "C"}, "2026-01-01", changes())
    assert m.members_on("2021-01-01") == {"A", "B", "C"}
    assert m.members_on("2019-06-01") == {"A", "B"}            # C not yet included
    assert m.members_on("2017-01-01") == {"A", "B", "D"}       # D still a member before its exclusion
    assert m.status_on("2017-01-01") == "RECONSTRUCTED"


def test_mask_matches_members_on():
    m = reconstruct_backwards("nifty50", {"A", "B", "C"}, "2026-01-01", changes())
    dates = pd.bdate_range("2017-01-01", "2021-12-31")
    mask = m.mask(dates, ["A", "B", "C", "D", "E"])
    for d in (pd.Timestamp("2017-06-01"), pd.Timestamp("2019-06-03"), pd.Timestamp("2021-06-01")):
        assert set(mask.columns[mask.loc[d]]) == set(m.members_on(d)) & {"A", "B", "C", "D", "E"}
    assert not mask["E"].any()


def test_coverage_and_survivor_share_quantify_the_bias():
    m = reconstruct_backwards("nifty50", {"A", "B", "C"}, "2026-01-01", changes())
    cov = m.coverage({"A", "B", "C"})                           # D has no price history (delisted/renamed)
    first = cov.iloc[0]
    assert first["members"] == 3 and first["with_prices"] == 2 and abs(first["share"] - 2 / 3) < 1e-12 and "D" in first["missing_examples"]
    ss = m.survivor_share({"A", "B", "C"})
    assert abs(ss.iloc[0]["share"] - 2 / 3) < 1e-12 and ss.iloc[-1]["share"] == 1.0


def test_size_check_flags_wrong_membership_counts():
    m = Membership("nifty50", [(pd.Timestamp("2020-01-01"), frozenset(f"S{i}" for i in range(50)), "SNAPSHOT"),
                               (pd.Timestamp("2020-06-01"), frozenset(f"S{i}" for i in range(44)), "SNAPSHOT")])
    ok = m.size_check()["ok"].tolist()
    assert ok == [True, False]


def test_parsers():
    assert parse_constituent_csv(pd.DataFrame({"Company Name": ["x"], "Symbol": [" tcs "]})) == {"TCS"}
    assert index_key_from_filename("ind_nifty500list.csv") == "nifty500" and index_key_from_filename("cnx200.csv") == "nifty200"
    assert index_key_from_filename("nifty50equalweight.csv") is None and index_key_from_filename("niftymidcap500.csv") is None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ind_nifty500.csv", "Security Symbol,Weightage\nAAA,1\nBBB,2\n")
        z.writestr("readme.txt", "hello")
    found, unmatched = parse_monthly_zip(buf.getvalue())
    assert found == {"nifty500": {"AAA", "BBB"}} and unmatched == ["readme.txt"]
    log = parse_incl_excl(pd.DataFrame({"Effective Date": ["28-09-2018", "31-03-2020"], "Symbol": ["d", "c"], "Action": ["Exclusion", "Inclusion"]}))
    assert log["action"].tolist() == ["EXCLUDE", "INCLUDE"] and log["symbol"].tolist() == ["D", "C"]


def test_from_snapshots_uses_latest_snapshot_on_or_before_date():
    m = from_snapshots("nifty50", {"2020-01-31": {"A"}, "2020-02-28": {"A", "B"}})
    assert m.members_on("2020-02-15") == {"A"} and m.members_on("2020-03-01") == {"A", "B"} and m.members_on("2019-12-01") == frozenset()


def test_strategies_never_hold_non_members():
    p = synthetic_panel(24, 6, seed=3)
    syms = p.symbols
    allowed = set(syms[:8])                                      # only 8 stocks are ever eligible
    p.members = pd.DataFrame({s: s in allowed for s in syms}, index=p.dates)
    for strat in (MultiFactor(top_n=5, regime="none"), TrendMomentum(top_n=5, regime=False)):
        r = run_backtest(p, strat, Config(max_positions=5))
        held = (set(r.trades.symbol) if len(r.trades) else set()) | (set(r.open_positions.symbol) if len(r.open_positions) else set())
        assert held and held <= allowed, (strat.name, held - allowed)


def test_membership_changes_over_time_are_respected():
    p = synthetic_panel(20, 6, seed=4)
    syms = p.symbols
    mask = pd.DataFrame(False, index=p.dates, columns=syms)
    mask.loc[:, syms[:6]] = True                                 # first half of the sample: only 6 stocks
    cut = p.dates[len(p.dates) // 2]
    mask.loc[mask.index >= cut, :] = False
    mask.loc[mask.index >= cut, syms[10:16]] = True             # second half: a different 6
    p.members = mask
    r = run_backtest(p, MultiFactor(top_n=4, regime="none"), Config(max_positions=4))
    t = pd.concat([r.trades[["symbol", "entry_date"]] if len(r.trades) else pd.DataFrame(columns=["symbol", "entry_date"]),
                   r.open_positions[["symbol", "entry_date"]] if len(r.open_positions) else pd.DataFrame(columns=["symbol", "entry_date"])])
    assert len(t) > 0
    early = t[t.entry_date < cut]
    late = t[t.entry_date >= cut + pd.Timedelta(days=5)]
    assert set(early.symbol) <= set(syms[:6]) and set(late.symbol) <= set(syms[10:16])


def test_valid_until_stops_stale_membership_and_csv_roundtrips(tmp_path):
    from algo.universe import load_membership_csv, save_membership_csv
    m = from_snapshots("nifty500", {"2020-01-31": {"A", "B"}, "2020-02-28": {"A", "B", "C"}})
    m.valid_until = pd.Timestamp("2020-04-30")
    dates = pd.bdate_range("2020-02-03", "2020-06-30")
    mask = m.mask(dates, ["A", "B", "C"])
    assert mask.loc["2020-04-30"].all() and not mask.loc["2020-05-01"].any()        # unknown after valid_until: nobody eligible
    save_membership_csv(m, tmp_path / "m.csv")
    back = load_membership_csv(tmp_path / "m.csv", "nifty500")
    assert back.valid_until == m.valid_until and back.members_on("2020-03-15") == {"A", "B", "C"} and back.members_on("2020-02-10") == {"A", "B"}
