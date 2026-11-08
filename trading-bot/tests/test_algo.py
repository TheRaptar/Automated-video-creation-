import numpy as np
import pandas as pd
import pytest

from algo.costs import DeliveryCosts
from algo.data import Panel, synthetic_panel
from algo.engine import Config, run_backtest
from algo.indicators import atr, rsi, sma
from algo.strategies import STRATEGIES, Signals, Strategy


class Manual(Strategy):
    """Test helper: hold exactly what the given boolean table says."""
    name = "manual"
    stop_atr_mult = None
    trailing_stop = False

    def __init__(self, desired):
        self.desired = desired

    def signals(self, p):
        return Signals(self.desired, self.desired.astype(float))


def flat_panel(n=40, price=100.0, symbols=("A",), spread=0.0):
    idx = pd.bdate_range("2024-01-01", periods=n)
    mk = lambda v: pd.DataFrame({s: np.full(n, v, dtype=float) for s in symbols}, index=idx)
    p = Panel(mk(price), mk(price + spread), mk(price - spread), mk(price), mk(1e7), pd.Series(100.0, index=idx))
    return p


ZERO = DeliveryCosts(stt_rate=0, exch_txn_rate=0, sebi_rate=0, stamp_rate=0, gst_rate=0, dp_charge=0)


# ---------------------------------------------------------------- costs
def test_costs_match_zerodha_example():
    c = DeliveryCosts()
    buy, sell = c.charges("BUY", 150_000), c.charges("SELL", 160_000)
    assert 22.5 + 150 < buy < 190          # STT 150 + stamp 22.5 + small exchange/GST
    assert 160 < sell < 200                # STT 160 + DP 15.93 + small exchange/GST
    assert abs(c.dp_charge * 1.18 - 15.93) < 1e-9


# ---------------------------------------------------------------- no look-ahead
def test_indicators_are_causal():
    p = synthetic_panel(5, 3, seed=1)
    cut = 500
    for f in (lambda d: sma(d.close, 50), lambda d: rsi(d.close, 2),
              lambda d: atr(d.high, d.low, d.close, 14)):
        full, part = f(p), f(p.slice(end=p.dates[cut]))
        pd.testing.assert_frame_equal(full.iloc[:cut + 1], part, check_exact=False, rtol=1e-9)


def mid_month_cut(p, start=700):
    """A cut date in the middle of a month, so the month-end rebalance flag is unambiguous."""
    for i in range(start, len(p.dates) - 1):
        d = p.dates[i]
        if 10 <= d.day <= 20 and p.dates[i + 1].month == d.month:
            return i
    raise AssertionError("no mid-month date found")


def assert_causal(strategy, p):
    cut = mid_month_cut(p)
    full, part = strategy.signals(p), strategy.signals(p.slice(end=p.dates[cut]))
    # compare EVERY row up to and including the cut: a one-day peek at tomorrow would show up in the last row
    pd.testing.assert_frame_equal(full.desired.iloc[:cut + 1], part.desired)
    pd.testing.assert_frame_equal(full.score.iloc[:cut + 1], part.score, check_exact=False, rtol=1e-9)


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_strategy_signals_are_causal(name):
    assert_causal(STRATEGIES[name](), synthetic_panel(12, 4, seed=2))


def test_causality_test_catches_a_cheater():
    class Cheater(Strategy):
        name = "cheater"

        def signals(self, p):
            return Signals(p.close.shift(-1) > p.close, p.close.pct_change())   # peeks one day ahead

    with pytest.raises(AssertionError):
        assert_causal(Cheater(), synthetic_panel(12, 4, seed=2))


# ---------------------------------------------------------------- accounting
def test_flat_prices_only_lose_costs():
    p = flat_panel()
    des = pd.DataFrame(False, index=p.dates, columns=p.symbols)
    des.iloc[5:15] = True
    cfg = Config(max_positions=1, slippage_bps=0, min_adv=0, cash_buffer=0.0)
    r = run_backtest(p, Manual(des), cfg)
    assert len(r.trades) == 1
    t = r.trades.iloc[0]
    assert t.entry_date == p.dates[6]          # signal at close of day 5 -> fills at OPEN of day 6
    assert t.exit_date == p.dates[16]          # signal flips at close of day 15 -> sells at open of day 16
    assert abs(r.equity.iloc[-1] - (cfg.capital - r.total_costs)) < 1e-6
    assert r.total_costs > 0 and r.min_cash >= 0


def test_zero_cost_flat_is_exactly_flat():
    p = flat_panel()
    des = pd.DataFrame(False, index=p.dates, columns=p.symbols)
    des.iloc[5:15] = True
    r = run_backtest(p, Manual(des), Config(max_positions=1, slippage_bps=0, min_adv=0, costs=ZERO))
    assert abs(r.equity.iloc[-1] - 1_000_000) < 1e-6


def test_fills_at_next_open_not_same_close():
    n = 30
    idx = pd.bdate_range("2024-01-01", periods=n)
    o = pd.DataFrame({"A": 100.0 + np.arange(n)}, index=idx)
    c = o + 0.5
    p = Panel(o, c + 1, o - 1, c, pd.DataFrame({"A": 1e7}, index=idx), pd.Series(100.0, index=idx))
    des = pd.DataFrame(False, index=idx, columns=["A"])
    des.iloc[10:20] = True
    r = run_backtest(p, Manual(des), Config(max_positions=1, slippage_bps=0, min_adv=0, costs=ZERO))
    assert r.trades.iloc[0].entry_price == o.iloc[11, 0]
    assert r.trades.iloc[0].exit_price == o.iloc[21, 0]


def test_max_positions_and_no_negative_cash():
    p = synthetic_panel(20, 4, seed=3)
    for name, cls in STRATEGIES.items():
        r = run_backtest(p, cls(), Config(max_positions=5))
        assert r.n_positions.max() <= 5, name
        assert r.min_cash >= -1e-6, name
        assert np.isfinite(r.equity).all() and (r.equity > 0).all(), name
        assert r.exposure.max() <= 1.0 + 1e-9, name


# ---------------------------------------------------------------- stops
def _stop_panel(day_open, day_low):
    n = 40
    idx = pd.bdate_range("2024-01-01", periods=n)
    base = lambda v: np.full(n, v, dtype=float)
    o, h, l, c = base(100), base(101), base(99), base(100)      # ATR = 2 -> 3*ATR stop = 94
    o[30], l[30] = day_open, day_low
    mk = lambda a: pd.DataFrame({"A": a}, index=idx)
    return Panel(mk(o), mk(h), mk(l), mk(c), mk(np.full(n, 1e7)), pd.Series(100.0, index=idx))


class ManualStop(Manual):
    stop_atr_mult = 3.0


def test_stop_gap_fills_at_open_not_stop():
    p = _stop_panel(day_open=90, day_low=88)
    des = pd.DataFrame(False, index=p.dates, columns=["A"]); des.iloc[20:] = True
    r = run_backtest(p, ManualStop(des), Config(max_positions=1, slippage_bps=0, min_adv=0, costs=ZERO))
    t = r.trades.iloc[0]
    assert t.reason == "stop" and t.exit_price == 90


def test_stop_intraday_fills_at_stop_price():
    p = _stop_panel(day_open=100, day_low=93)
    des = pd.DataFrame(False, index=p.dates, columns=["A"]); des.iloc[20:] = True
    r = run_backtest(p, ManualStop(des), Config(max_positions=1, slippage_bps=0, min_adv=0, costs=ZERO))
    t = r.trades.iloc[0]
    assert t.reason == "stop" and abs(t.exit_price - 94.0) < 0.2    # ATR warms up to ~2.0


def test_stopped_stock_cannot_instantly_reenter():
    p = _stop_panel(day_open=90, day_low=88)
    des = pd.DataFrame(False, index=p.dates, columns=["A"]); des.iloc[20:] = True
    r = run_backtest(p, ManualStop(des), Config(max_positions=1, slippage_bps=0, min_adv=0, costs=ZERO))
    assert len(r.trades) == 1 and r.open_positions.empty      # signal never reset, so no re-entry


# ---------------------------------------------------------------- end to end
def test_momentum_beats_random_on_planted_momentum():
    p = synthetic_panel(30, 8, seed=5)
    r = run_backtest(p, STRATEGIES["momentum"](), Config(max_positions=10))
    assert len(r.trades) > 20 and r.equity.iloc[-1] > 0
