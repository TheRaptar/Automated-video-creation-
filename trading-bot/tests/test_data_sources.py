import json

import numpy as np
import pandas as pd

from algo import nse, rates
from algo.provenance import Manifest


class FakeResp:
    def __init__(self, payload, status=200, text=""):
        self._p, self.status_code, self.text = payload, status, text

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json))
        return self.handler(url, json)

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, None))
        return self.handler(url, None)


def tri_rows(start, end, level0=1000.0, growth=1.0003, net=True):
    days = pd.bdate_range(start, end)
    rows = []
    for i, d in enumerate(days):
        r = {"Date": d.strftime("%d %b %Y"), "TotalReturnsIndex": f"{level0 * growth ** i:,.2f}"}
        if net:
            r["NetTotalReturnIndex"] = f"{level0 * growth ** i * 0.99:,.2f}"
        rows.append(r)
    return rows


def window_of(body):
    c = body["cinfo"]
    info = json.loads(c) if c.strip().startswith('{"') else eval(c)          # python-style variant
    return pd.to_datetime(info["startDate"]), pd.to_datetime(info["endDate"])


def test_parse_tri_gross_and_net():
    df = nse.parse_rows(tri_rows("2021-06-01", "2021-06-10"), {"gross_tri": (("total", "return"), ("net",)), "net_tri": ("net", "return")})
    assert df.index.is_monotonic_increasing and len(df) == 8
    assert abs(df["gross_tri"].iloc[0] - 1000.0) < 1e-9 and df["net_tri"].iloc[0] < df["gross_tri"].iloc[0]


def test_fetch_tri_chunks_dedupes_and_sorts():
    def handler(url, body):
        s, e = window_of(body)
        rows = [r for r in tri_rows("2018-01-01", "2020-12-31") if s <= pd.to_datetime(r["Date"]) <= e]
        return FakeResp({"d": json.dumps(rows)})
    sess = FakeSession(handler)
    df = nse.fetch_tri("NIFTY 50", "2018-01-01", "2020-12-31", sess)
    assert len(sess.calls) >= 3 and df.index.is_unique and df.index.is_monotonic_increasing
    assert len(df) == len(pd.bdate_range("2018-01-01", "2020-12-31"))


def test_second_payload_style_is_tried_when_first_is_empty():
    def handler(url, body):
        if body["cinfo"].startswith('{"'):
            return FakeResp({"d": "[]"})
        return FakeResp({"d": json.dumps(tri_rows("2021-01-01", "2021-03-01"))})
    df = nse.fetch_tri("NIFTY 50", "2021-01-01", "2021-03-01", FakeSession(handler))
    assert len(df) > 30


def test_cash_index_tries_name_variants():
    def handler(url, body):
        if "1D Rate Index" in body["cinfo"] and "NIFTY" not in body["cinfo"].split("name")[1][:12]:
            return FakeResp({"d": json.dumps(tri_rows("2015-01-01", "2016-12-31", 1000, 1.00022, net=False))})
        return FakeResp({"d": "[]"})
    df, used = nse.fetch_cash_index("2015-01-01", "2016-12-31", FakeSession(handler))
    assert used == "Nifty 1D Rate Index" and len(df) > 100


def test_fetch_failure_returns_empty_not_exception():
    def handler(url, body):
        raise RuntimeError("blocked")
    assert nse.fetch_tri("NIFTY 50", "2021-01-01", "2021-02-01", FakeSession(handler)).empty


# ---------------------------------------------------------------- cash returns
DATES = pd.bdate_range("2012-01-02", "2026-06-30")


def test_cash_from_official_index_is_verified():
    lvl = pd.Series(1000 * 1.00022 ** np.arange(len(DATES)), index=DATES)
    m = Manifest()
    ret, status = rates.load_cash_returns(DATES, m, fetch_cash=lambda s, e: (pd.DataFrame({"gross_tri": lvl}), "NIFTY 1D RATE INDEX"))
    assert status == "VERIFIED" and m.status("cash returns (overnight rate)") == "VERIFIED"
    assert abs(ret.iloc[100] - 0.00022) < 1e-9


def test_cash_partial_history_is_marked_incomplete_and_filled_with_estimate():
    lvl = pd.Series(1000 * 1.00022 ** np.arange(len(DATES)), index=DATES)[DATES >= "2016-01-01"]
    m = Manifest()
    ret, status = rates.load_cash_returns(DATES, m, fetch_cash=lambda s, e: (pd.DataFrame({"gross_tri": lvl}), "x"))
    assert status == "INCOMPLETE" and ret[DATES < "2016-01-01"].gt(0).all()


def test_cash_falls_back_to_repo_estimate_then_constant():
    m = Manifest()
    ret, status = rates.load_cash_returns(DATES, m, fetch_cash=lambda s, e: (pd.DataFrame(), None))
    assert status == "ESTIMATED"
    d = pd.Timestamp("2020-06-01")                                  # repo was 4.00% -> (4.00-0.40)% = 3.6% a year
    assert abs((1 + ret[d]) ** 252 - 1 - 0.036) < 1e-9
    short = pd.bdate_range("2005-01-03", "2005-06-30")               # before the table starts -> constant
    ret2, status2 = rates.load_cash_returns(short, m)
    assert status2 == "ASSUMED" and abs((1 + ret2.iloc[0]) ** 252 - 1.06) < 1e-9


def test_repo_table_is_sorted_and_plausible():
    d = [pd.Timestamp(x) for x, _ in rates.REPO_HISTORY]
    assert d == sorted(d) and all(3.0 <= r <= 9.0 for _, r in rates.REPO_HISTORY)


def test_manifest_roundtrip_and_status_rules(tmp_path):
    m = Manifest()
    m.add("a", "VERIFIED", "src", series=pd.Series([1.0, 2.0], index=pd.bdate_range("2020-01-01", periods=2)))
    m.add("b", "ESTIMATED", "src")
    m.save(tmp_path / "m.json")
    assert json.loads((tmp_path / "m.json").read_text())["a"]["rows"] == 2
    assert m.status("zzz") == "UNAVAILABLE" and not m.all_verified(["a", "b"]) and m.all_verified(["a"])
    assert "ESTIMATED" in m.to_markdown()
