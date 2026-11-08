"""
Daily backtest engine for a long-only, no-leverage delivery portfolio.

Timeline of one day t:  (1) sell orders from yesterday's signals fill at today's OPEN,
(2) buy orders fill at today's OPEN, (3) protective stops are checked against today's LOW,
(4) the portfolio is valued at the CLOSE, (5) new orders are decided from today's close for tomorrow's open.
Nothing can trade on information from the future.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import DeliveryCosts
from .data import Panel
from .indicators import atr as atr_fn
from .strategies import Strategy


@dataclass
class Config:
    capital: float = 1_000_000.0
    max_positions: int = 10
    slippage_bps: float = 5.0             # each fill is this much worse than the quoted price
    stop_atr_mult: float | None = None    # None -> use the strategy's suggestion
    trailing_stop: bool | None = None
    use_stops: bool = True
    atr_period: int = 14
    min_adv: float = 5e7                  # skip stocks trading < Rs 5 crore/day (20-day average)
    max_adv_pct: float = 0.05             # never buy more than 5% of a day's traded value
    cash_buffer: float = 0.02             # keep 2% of equity as cash
    costs: DeliveryCosts = field(default_factory=DeliveryCosts)


@dataclass
class Result:
    strategy: str
    params: dict
    config: Config
    equity: pd.Series
    exposure: pd.Series
    n_positions: pd.Series
    trades: pd.DataFrame
    open_positions: pd.DataFrame
    total_costs: float
    min_cash: float


def run_backtest(panel: Panel, strategy: Strategy, cfg: Config | None = None) -> Result:
    cfg = cfg or Config()
    mult = strategy.stop_atr_mult if cfg.stop_atr_mult is None else cfg.stop_atr_mult
    trailing = strategy.trailing_stop if cfg.trailing_stop is None else cfg.trailing_stop
    if not cfg.use_stops:
        mult = None

    dates, syms = panel.close.index, list(panel.close.columns)
    n_days = len(dates)
    sig = strategy.signals(panel)
    desired = sig.desired.reindex(index=dates, columns=syms).fillna(False).astype(bool).to_numpy()
    score = sig.score.reindex(index=dates, columns=syms).to_numpy(dtype=float)
    atr = atr_fn(panel.high, panel.low, panel.close, cfg.atr_period).to_numpy(dtype=float)
    adv = (panel.close * panel.volume).rolling(20, min_periods=20).mean().to_numpy(dtype=float)
    O, H, L, C = (panel.open.to_numpy(dtype=float), panel.high.to_numpy(dtype=float),
                  panel.low.to_numpy(dtype=float), panel.close.to_numpy(dtype=float))
    Cff = panel.close.ffill().to_numpy(dtype=float)
    slip = cfg.slippage_bps / 1e4

    cash, total_costs, min_cash = cfg.capital, 0.0, cfg.capital
    pos: dict[int, dict] = {}
    blocked: set[int] = set()
    pending_sell: list[tuple[int, str]] = []
    pending_buy: list[tuple[int, float, float]] = []
    equity, exposure, npos, trades = [], [], [], []

    def sell(j: int, raw_price: float, i: int, reason: str):
        nonlocal cash, total_costs
        p = pos.pop(j)
        fill = raw_price * (1 - slip)
        value = p["shares"] * fill
        ch = cfg.costs.charges("SELL", value)
        cash += value - ch
        total_costs += ch
        gross = (fill - p["entry"]) * p["shares"]
        costs_paid = ch + p["buy_charges"]
        trades.append({
            "symbol": syms[j], "entry_date": p["entry_date"], "exit_date": dates[i], "shares": p["shares"],
            "entry_price": p["entry"], "exit_price": fill, "gross_pnl": gross, "costs": costs_paid,
            "net_pnl": gross - costs_paid, "return": (gross - costs_paid) / (p["entry"] * p["shares"]),
            "days_held": (dates[i] - p["entry_date"]).days, "reason": reason})

    for i in range(n_days):
        o, l, c = O[i], L[i], C[i]

        # (1) sells at the open
        for j, reason in pending_sell:
            if j in pos and np.isfinite(o[j]):
                sell(j, o[j], i, reason)
        pending_sell = []

        # (2) buys at the open
        if pending_buy:
            held = sum(p["shares"] * (o[j] if np.isfinite(o[j]) else Cff[i, j]) for j, p in pos.items())
            equity_open = cash + held
            target = equity_open / cfg.max_positions
            for j, atr_sig, adv_sig in pending_buy:
                if j in pos or len(pos) >= cfg.max_positions or not np.isfinite(o[j]):
                    continue
                fill = o[j] * (1 + slip)
                budget = min(target, cash - cfg.cash_buffer * equity_open,
                             adv_sig * cfg.max_adv_pct if np.isfinite(adv_sig) else np.inf)
                shares = int(budget / (fill * 1.0015)) if budget > 0 else 0   # 0.15% headroom for charges
                if shares < 1:
                    continue
                value = shares * fill
                ch = cfg.costs.charges("BUY", value)
                if value + ch > cash:
                    continue
                cash -= value + ch
                total_costs += ch
                stop = fill - mult * atr_sig if (mult and np.isfinite(atr_sig)) else -np.inf
                pos[j] = {"shares": shares, "entry": fill, "entry_date": dates[i], "stop": stop, "buy_charges": ch}
            pending_buy = []

        # (3) protective stops (gap-aware)
        if mult:
            for j in list(pos):
                if not np.isfinite(o[j]):
                    continue
                st = pos[j]["stop"]
                if o[j] <= st:
                    sell(j, o[j], i, "stop"); blocked.add(j)
                elif l[j] <= st:
                    sell(j, st, i, "stop"); blocked.add(j)

        # (4) value at the close, trail stops
        held_val = 0.0
        for j, p in pos.items():
            held_val += p["shares"] * Cff[i, j]
            if mult and trailing and np.isfinite(atr[i, j]):
                p["stop"] = max(p["stop"], Cff[i, j] - mult * atr[i, j])
        eq = cash + held_val
        equity.append(eq); exposure.append(held_val / eq if eq > 0 else 0.0); npos.append(len(pos))
        min_cash = min(min_cash, cash)

        # (5) decide tomorrow's orders from today's close
        if i < n_days - 1:
            des = desired[i]
            sells = [(j, "signal") for j in pos if not des[j]]
            pending_sell = sells
            for j in list(blocked):
                if not des[j]:
                    blocked.discard(j)               # a stopped-out stock may re-enter only after its signal resets
            free = cfg.max_positions - (len(pos) - len(sells))
            pending_buy = []
            if free > 0:
                cand = [j for j in np.flatnonzero(des)
                        if j not in pos and j not in blocked and np.isfinite(c[j])
                        and (cfg.min_adv <= 0 or adv[i, j] >= cfg.min_adv)]
                cand.sort(key=lambda j: -(score[i, j] if np.isfinite(score[i, j]) else -np.inf))
                pending_buy = [(j, atr[i, j], adv[i, j]) for j in cand[:free]]

    open_rows = [{"symbol": syms[j], "entry_date": p["entry_date"], "shares": p["shares"], "entry_price": p["entry"],
                  "last_price": Cff[-1, j], "unrealised_pnl": (Cff[-1, j] - p["entry"]) * p["shares"]}
                 for j, p in pos.items()]
    return Result(strategy.name, strategy.params(), cfg,
                  pd.Series(equity, index=dates, name="equity"), pd.Series(exposure, index=dates),
                  pd.Series(npos, index=dates), pd.DataFrame(trades), pd.DataFrame(open_rows),
                  total_costs, min_cash)
