"""
Pre-trade risk gate for LIVE trading (Phase 3). Adapted in spirit from trader-risk / trader-budget in
Jakeschincariol/day-trader-skill (MIT): every order is checked against written limits and gets PASS or BLOCK with reasons.
Rewritten for Indian delivery (CNC) trading, rupees, IST - no code copied.

Principles:
  * A BLOCK is final for that order. A PASS only means "allowed to be shown to you" - it is not a decision to trade.
  * Orders that REDUCE risk (sells of shares you hold) are never blocked by exposure limits, only by sanity checks.
  * The gate is independent of the strategy: the strategy can be wrong, the gate still holds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time


@dataclass
class Limits:
    max_position_pct: float = 0.10           # one stock may not exceed 10% of equity after the order
    max_positions: int = 15
    max_loss_per_trade_pct: float = 0.01     # loss at the stop may not exceed 1% of equity (only if a stop is given)
    max_daily_loss_pct: float = 0.02         # equity down 2% on the day -> no new buys
    max_orders_per_day: int = 20
    max_order_adv_pct: float = 0.02          # order value vs the stock's average daily traded value
    min_adv_value: float = 5e7               # Rs 5 crore/day minimum liquidity
    cash_buffer_pct: float = 0.02            # always keep 2% of equity in cash
    est_cost_pct: float = 0.0025             # allowance for STT, stamp duty, fees on a buy
    max_price_deviation_pct: float = 0.03    # limit price may not be > 3% away from the last price
    min_price: float = 50.0                  # no penny stocks
    window_start: time = time(9, 20)
    window_end: time = time(15, 15)
    allowed_products: tuple = ("CNC",)       # delivery only: no intraday, margin, F&O
    allowed_symbols: frozenset | None = None  # None = any; set a whitelist when you go live


@dataclass
class Order:
    symbol: str
    side: str                                # "BUY" or "SELL"
    qty: int
    price: float                             # limit price (or the price you expect to pay)
    stop: float | None = None                # optional protective stop, used for the loss check
    product: str = "CNC"


@dataclass
class Portfolio:
    equity: float
    cash: float
    day_start_equity: float
    positions: dict = field(default_factory=dict)    # symbol -> qty held
    orders_today: int = 0


@dataclass
class Market:
    last_price: float
    adv_value: float                         # average daily traded value in rupees


@dataclass
class Decision:
    allowed: bool
    reasons: list
    notes: list

    def __str__(self):
        head = "PASS" if self.allowed else "BLOCK"
        return head + ("" if self.allowed else ": " + "; ".join(self.reasons)) + ("  (" + "; ".join(self.notes) + ")" if self.notes else "")


def check_order(order: Order, pf: Portfolio, mkt: Market, lim: Limits, now: time, kill_switch: bool = False) -> Decision:
    why, notes = [], []
    value = order.qty * order.price
    side = order.side.upper()

    # ---- sanity checks (apply to every order)
    if side not in ("BUY", "SELL"):
        why.append("side must be BUY or SELL")
    if not (isinstance(order.qty, int) and order.qty > 0):
        why.append("quantity must be a positive whole number")
    if order.product not in lim.allowed_products:
        why.append(f"product {order.product} not allowed (allowed: {', '.join(lim.allowed_products)})")
    if lim.allowed_symbols is not None and order.symbol not in lim.allowed_symbols:
        why.append(f"{order.symbol} is not on the whitelist")
    if not (lim.window_start <= now <= lim.window_end):
        why.append(f"outside the trading window {lim.window_start:%H:%M}-{lim.window_end:%H:%M} IST")
    if mkt.last_price <= 0 or abs(order.price / mkt.last_price - 1) > lim.max_price_deviation_pct:
        why.append(f"limit price {order.price:g} is more than {lim.max_price_deviation_pct:.0%} away from the last price {mkt.last_price:g}")
    if pf.orders_today >= lim.max_orders_per_day:
        why.append(f"daily order limit reached ({lim.max_orders_per_day})")

    if side == "SELL":
        held = pf.positions.get(order.symbol, 0)
        if order.qty > held:
            why.append(f"selling {order.qty} but holding {held} (no short selling)")
        else:
            notes.append("risk-reducing order: exposure limits do not apply")
        return Decision(not why, why, notes)

    # ---- BUY-only checks (exposure limits)
    if kill_switch:
        why.append("kill switch is ON: no new buys")
    if pf.equity <= 0:
        why.append("equity is zero")
        return Decision(False, why, notes)
    if order.price < lim.min_price:
        why.append(f"price {order.price:g} is below the minimum {lim.min_price:g}")
    if mkt.adv_value < lim.min_adv_value:
        why.append(f"stock too illiquid: average traded value Rs {mkt.adv_value:,.0f} < Rs {lim.min_adv_value:,.0f}")
    if mkt.adv_value > 0 and value > lim.max_order_adv_pct * mkt.adv_value:
        why.append(f"order is {value / mkt.adv_value:.1%} of average daily value (max {lim.max_order_adv_pct:.0%})")
    new_pos_value = (pf.positions.get(order.symbol, 0) * order.price) + value
    if new_pos_value > lim.max_position_pct * pf.equity:
        why.append(f"position would be {new_pos_value / pf.equity:.1%} of equity (max {lim.max_position_pct:.0%})")
    if order.symbol not in pf.positions and len(pf.positions) >= lim.max_positions:
        why.append(f"already holding {len(pf.positions)} positions (max {lim.max_positions})")
    need = value * (1 + lim.est_cost_pct) + lim.cash_buffer_pct * pf.equity
    if need > pf.cash:
        why.append(f"not enough cash: need Rs {need:,.0f} including costs and the {lim.cash_buffer_pct:.0%} buffer, have Rs {pf.cash:,.0f}")
    if order.stop is not None:
        if order.stop >= order.price:
            why.append("stop must be below the buy price")
        else:
            loss = order.qty * (order.price - order.stop)
            if loss > lim.max_loss_per_trade_pct * pf.equity:
                why.append(f"loss at the stop Rs {loss:,.0f} exceeds {lim.max_loss_per_trade_pct:.1%} of equity (Rs {lim.max_loss_per_trade_pct * pf.equity:,.0f})")
    else:
        notes.append("no stop given: size is limited by the position cap only")
    if pf.day_start_equity > 0 and pf.equity <= pf.day_start_equity * (1 - lim.max_daily_loss_pct):
        why.append(f"daily loss limit hit: equity is {1 - pf.equity / pf.day_start_equity:.1%} below the day's start (max {lim.max_daily_loss_pct:.0%})")
    return Decision(not why, why, notes)


def size_by_risk(equity: float, cash: float, entry: float, stop: float, lim: Limits) -> int:
    """Shares to buy so that a stop-out loses at most max_loss_per_trade_pct of equity, capped by the position
    limit and by available cash (idea from trader-budget: qty = max loss / risk per share, rounded DOWN)."""
    if entry <= 0 or stop >= entry:
        return 0
    by_loss = (lim.max_loss_per_trade_pct * equity) / (entry - stop)
    by_pos = lim.max_position_pct * equity / entry
    by_cash = max(0.0, cash - lim.cash_buffer_pct * equity) / (entry * (1 + lim.est_cost_pct))
    return max(0, int(math.floor(min(by_loss, by_pos, by_cash))))


def size_equal_weight(equity: float, cash: float, entry: float, n_positions: int, lim: Limits) -> int:
    """Shares for an equal-weight portfolio of n positions, capped by the position limit and cash."""
    if entry <= 0 or n_positions <= 0:
        return 0
    per = min(equity / n_positions, lim.max_position_pct * equity)
    by_cash = max(0.0, cash - lim.cash_buffer_pct * equity) / (1 + lim.est_cost_pct)
    return max(0, int(math.floor(min(per, by_cash) / entry)))
