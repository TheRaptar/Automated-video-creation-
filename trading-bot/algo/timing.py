"""
Does the market filter (trend / India VIX) add value on the INDEX itself, or is it luck?

Strategy: hold the index while the filter says risk-on, otherwise sit in cash (liquid fund). Decisions are made at the
close and applied from the NEXT day. Null test: random on/off schedules built by SHUFFLING the lengths of the real
on-periods and off-periods - same time invested, same number of switches, same costs, only the TIMING is random.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import performance


def timed_returns(bench: pd.Series, gate: np.ndarray, cash_yield: float, div_yield: float, switch_cost: float) -> np.ndarray:
    r = bench.pct_change().fillna(0.0).to_numpy() + div_yield / 252          # price index + approximate dividends
    cash = (1 + cash_yield) ** (1 / 252) - 1
    g = np.r_[False, gate[:-1]].astype(bool)                                   # decided at yesterday's close
    switched = g != np.r_[False, g[:-1]]
    return np.where(g, r, cash) - switch_cost * switched


def equity_from(ret: np.ndarray, index, capital: float = 1_000_000) -> pd.Series:
    return pd.Series(capital * np.cumprod(1 + ret), index=index)


def shuffle_runs(gate: np.ndarray, rng) -> np.ndarray:
    """Random schedule with the same on/off run lengths (and the same first state) as the real one."""
    change = np.flatnonzero(gate[1:] != gate[:-1]) + 1
    bounds = np.r_[0, change, len(gate)]
    lengths = np.diff(bounds)
    first = bool(gate[0])
    on = lengths[0::2] if first else lengths[1::2]
    off = lengths[1::2] if first else lengths[0::2]
    on, off = rng.permutation(on), rng.permutation(off)
    out, state, i_on, i_off = [], first, 0, 0
    for _ in range(len(lengths)):
        if state:
            out.append(np.ones(on[i_on], bool)); i_on += 1
        else:
            out.append(np.zeros(off[i_off], bool)); i_off += 1
        state = not state
    return np.concatenate(out)


def timing_test(bench: pd.Series, gate: pd.Series, n: int = 2000, seed: int = 19, cash_yield: float = 0.06,
                div_yield: float = 0.013, switch_cost: float = 0.001, rf: float = 0.06) -> dict:
    g = gate.reindex(bench.index).fillna(False).to_numpy(bool)
    idx = bench.index
    real_eq = equity_from(timed_returns(bench, g, cash_yield, div_yield, switch_cost), idx)
    bh_eq = equity_from(bench.pct_change().fillna(0.0).to_numpy() + div_yield / 252, idx)
    pr, pb = performance(real_eq, rf), performance(bh_eq, rf)
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        eq = equity_from(timed_returns(bench, shuffle_runs(g, rng), cash_yield, div_yield, switch_cost), idx)
        pf = performance(eq, rf)
        rows.append((pf["cagr"], pf["sharpe"], pf["max_drawdown"]))
    null = pd.DataFrame(rows, columns=["cagr", "sharpe", "max_drawdown"])
    pv = lambda m: (1 + int((null[m] >= pr[m]).sum())) / (n + 1)
    pdd = (1 + int((null["max_drawdown"] >= pr["max_drawdown"]).sum())) / (n + 1)
    switches = int((np.r_[False, g[:-1]] != np.r_[False, np.r_[False, g[:-1]][:-1]]).sum())
    return {"n": n, "seed": seed, "real": pr, "buy_hold": pb, "null": null, "p_sharpe": pv("sharpe"), "p_cagr": pv("cagr"),
            "p_drawdown": pdd, "exposure": float(g.mean()), "switches": int((g[1:] != g[:-1]).sum()),
            "real_equity": real_eq, "bh_equity": bh_eq}


def timing_verdict(res: dict) -> str:
    p, r, b = res["p_sharpe"], res["real"], res["buy_hold"]
    if p > 0.10:
        head = (f"The filter's timing is indistinguishable from luck: random on/off schedules with the same exposure and number of "
                f"switches matched its Sharpe in {p:.0%} of runs.")
    elif p > 0.025:
        head = f"The filter leans toward real timing value (random schedules matched it in {p:.1%} of runs) but it is not convincing."
    else:
        head = f"Strong evidence of timing value: random schedules matched it in only {p:.1%} of runs."
    tail = (f" Versus simply holding the index: CAGR {r['cagr']:.1%} vs {b['cagr']:.1%}, max drawdown {r['max_drawdown']:.1%} vs {b['max_drawdown']:.1%}.")
    return head + tail
