from datetime import time

import pytest

from algo.risk_gate import Limits, Market, Order, Portfolio, check_order, size_by_risk, size_equal_weight

LIM = Limits()
NOW = time(10, 30)


def pf(**kw):
    base = dict(equity=1_000_000, cash=1_000_000, day_start_equity=1_000_000, positions={}, orders_today=0)
    base.update(kw)
    return Portfolio(**base)


MKT = Market(last_price=1000.0, adv_value=5e9)
GOOD = Order("RELIANCE", "BUY", 50, 1000.0, stop=980.0)      # Rs 50,000 = 5% of equity; loss at stop Rs 1,000 = 0.1%


def test_good_order_passes():
    assert check_order(GOOD, pf(), MKT, LIM, NOW).allowed


@pytest.mark.parametrize("order,expect", [
    (Order("X", "BUY", 150, 1000.0), "position would be"),                      # 15% of equity
    (Order("X", "BUY", 50, 1000.0, stop=800.0), "loss at the stop"),            # Rs 10,000 loss = 1% limit exceeded? 50*200=10,000 -> equal; use bigger
    (Order("X", "BUY", 50, 1000.0, product="MIS"), "product MIS"),
    (Order("X", "BUY", 50, 1100.0), "away from the last price"),
    (Order("X", "BUY", 0, 1000.0), "positive whole number"),
    (Order("X", "BUY", 5, 40.0), "below the minimum"),
])
def test_blocks_and_reasons(order, expect):
    if order.stop == 800.0:
        order = Order("X", "BUY", 60, 1000.0, stop=800.0)                       # Rs 12,000 loss > Rs 10,000 limit
    d = check_order(order, pf(), Market(order.price, 5e9) if order.price < 1100 and order.price > 0 and expect != "away from the last price" else MKT, LIM, NOW)
    assert not d.allowed and any(expect in r for r in d.reasons), d


def test_liquidity_and_cash_and_position_count():
    assert not check_order(GOOD, pf(), Market(1000.0, 1e7), LIM, NOW).allowed                       # illiquid
    assert not check_order(GOOD, pf(cash=40_000), MKT, LIM, NOW).allowed                              # not enough cash
    full = pf(positions={f"S{i}": 10 for i in range(15)})
    assert any("already holding" in r for r in check_order(GOOD, full, MKT, LIM, NOW).reasons)


def test_window_orders_per_day_daily_loss_kill_switch():
    assert not check_order(GOOD, pf(), MKT, LIM, time(9, 0)).allowed
    assert not check_order(GOOD, pf(), MKT, LIM, time(15, 25)).allowed
    assert not check_order(GOOD, pf(orders_today=20), MKT, LIM, NOW).allowed
    assert not check_order(GOOD, pf(equity=970_000, cash=970_000), MKT, LIM, NOW).allowed            # -3% on the day
    assert not check_order(GOOD, pf(), MKT, LIM, NOW, kill_switch=True).allowed


def test_sells_reduce_risk_and_are_not_blocked_by_exposure_limits():
    held = pf(positions={"RELIANCE": 100}, equity=970_000, day_start_equity=1_000_000)               # daily-loss limit hit
    sell = Order("RELIANCE", "SELL", 100, 1000.0)
    assert check_order(sell, held, MKT, LIM, NOW, kill_switch=True).allowed                          # exit still possible
    assert not check_order(Order("RELIANCE", "SELL", 150, 1000.0), held, MKT, LIM, NOW).allowed      # but no short selling
    assert not check_order(sell, held, MKT, LIM, time(8, 0)).allowed                                  # window still applies


def test_whitelist():
    lim = Limits(allowed_symbols=frozenset({"TCS"}))
    assert not check_order(GOOD, pf(), MKT, lim, NOW).allowed


def test_sizing():
    assert size_by_risk(1_000_000, 1_000_000, 1000, 980, LIM) == 100          # loss cap Rs 10,000 / Rs 20 = 500; position cap 100
    assert size_by_risk(1_000_000, 1_000_000, 1000, 900, LIM) == 100          # 10,000/100 = 100 shares
    assert size_by_risk(1_000_000, 1_000_000, 1000, 1000, LIM) == 0           # stop at entry is invalid
    assert size_by_risk(1_000_000, 50_000, 1000, 980, LIM) < 50                # cash-limited
    assert size_equal_weight(1_000_000, 1_000_000, 1000, 15, LIM) == 66        # 66,666 / 1000
    assert size_equal_weight(1_000_000, 1_000_000, 1000, 5, LIM) == 100        # capped by the 10% position limit
    q = size_by_risk(1_000_000, 1_000_000, 1000, 950, LIM)
    assert q * 50 <= LIM.max_loss_per_trade_pct * 1_000_000                     # never risks more than the limit
