"""
Monte Carlo tests for our strategies, inspired by the Time Machine skill in Jakeschincariol/day-trader-skill (MIT).

The Time Machine asks, for ONE intraday trade: "if the rest of today is replayed 10,000 times from this stock's own bars,
how often does the plan hit target first?" and prints an honest verdict with a fixed seed. We keep those principles
(replay many alternative histories, compare with a break-even yardstick, fixed seed, plain verdict) and apply them to the
question that decides whether our PORTFOLIO is worth trading:

  1. NULL TEST  - run the strategy thousands of times picking stocks AT RANDOM with the same timing (regime), the same
     number of holdings, the same turnover and the same costs. Where does the real strategy rank? If it sits in the middle
     of the random pack, its returns come from timing/cash/luck, not from stock selection.
  2. CONTROL    - the whole universe held equal-weight under the same timing (what "just be invested when the filter says so" earns).
  3. BOOTSTRAP  - block-resample the daily returns to put honest error bars on CAGR, Sharpe and max drawdown.
     (Blocks keep volatility clustering, which the Time Machine's one-bar-at-a-time draws deliberately do not.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Config, run_backtest
from .metrics import performance
from .strategies import MultiFactor, Signals, Strategy, _gate, rebalance_starts


class RandomPicks(Strategy):
    """Same eligibility, timing, number of holdings and turnover as a reference MultiFactor - but random identities."""
    name = "random_picks"
    stop_atr_mult = None
    trailing_stop = False

    def __init__(self, ref: MultiFactor, score: pd.DataFrame, desired_ref: pd.DataFrame, gate, seed: int):
        self.ref, self.score, self.D, self.gate, self.seed = ref, score, desired_ref.to_numpy(bool), gate, seed

    def params(self):
        return {"seed": self.seed}

    def signals(self, p):
        S, D, ref = self.score.to_numpy(float), self.D, self.ref
        T, N = S.shape
        rng = np.random.default_rng(self.seed)
        starts = rebalance_starts(S, ref.rebalance_days, ref.top_n)
        out = np.zeros((T, N), bool)
        held, prev_ref = set(), set()
        for k, i in enumerate(starts):
            elig = np.flatnonzero(np.isfinite(S[i]))
            ref_now = set(np.flatnonzero(D[i]).tolist())
            replace_n = len(ref_now - prev_ref) if k else ref.top_n
            held = {j for j in held if np.isfinite(S[i, j])}
            if not held:
                held = set(rng.choice(elig, size=min(ref.top_n, len(elig)), replace=False).tolist())
            else:
                drop = min(replace_n, len(held))
                dropped = set(rng.choice(sorted(held), size=drop, replace=False).tolist()) if drop else set()
                held -= dropped
                pool = [j for j in elig if j not in held and j not in dropped]     # a dropped name cannot come straight back
                need = ref.top_n - len(held)
                if need > 0 and pool:
                    held |= set(rng.choice(pool, size=min(need, len(pool)), replace=False).tolist())
            prev_ref = ref_now
            end = starts[k + 1] if k + 1 < len(starts) else T
            out[i:end, list(held)] = True
        df = pd.DataFrame(out, index=self.score.index, columns=self.score.columns)
        return Signals(df if self.gate is None else _gate(df, self.gate), self.score * 0.0)


class EqualWeightTimed(Strategy):
    """Control: hold EVERY eligible stock equal-weight whenever the regime filter says risk-on, else cash."""
    name = "equal_weight_timed"
    stop_atr_mult = None
    trailing_stop = False

    def __init__(self, score: pd.DataFrame, gate):
        self.score, self.gate = score, gate

    def signals(self, p):
        df = self.score.notna()
        return Signals(df if self.gate is None else _gate(df, self.gate), self.score * 0.0)


def null_test(panel, ref: MultiFactor, cfg: Config, n: int = 200, seed: int = 19, rf: float = 0.06) -> dict:
    score, d_ref = ref.target(panel)
    gate = ref.gate(panel)
    real = run_backtest(panel, ref, cfg)
    pr = performance(real.equity, rf)
    rows = []
    for k in range(n):
        res = run_backtest(panel, RandomPicks(ref, score, d_ref, gate, seed * 100003 + k), cfg)
        pf = performance(res.equity, rf)
        rows.append((pf["cagr"], pf["sharpe"], pf["max_drawdown"], res.total_costs))
    null = pd.DataFrame(rows, columns=["cagr", "sharpe", "max_drawdown", "costs"])
    ctrl_cfg = Config(**{**cfg.__dict__, "max_positions": len(panel.symbols)})
    ctrl = run_backtest(panel, EqualWeightTimed(score, gate), ctrl_cfg)
    pc = performance(ctrl.equity, rf)

    def pv(metric):                      # one-sided: how often does random picking do at least as well?
        return (1 + int((null[metric] >= pr[metric]).sum())) / (n + 1)

    return {"n": n, "seed": seed, "real": pr, "real_costs": real.total_costs, "real_result": real, "null": null,
            "control": pc, "control_result": ctrl, "p_sharpe": pv("sharpe"), "p_cagr": pv("cagr"),
            "pct_sharpe": float((null.sharpe < pr["sharpe"]).mean()), "pct_cagr": float((null.cagr < pr["cagr"]).mean())}


def null_verdict(p: float) -> str:
    if p > 0.10:
        return ("Indistinguishable from random stock picking: with the same timing, turnover and costs, random baskets "
                "did as well or better in %.0f%% of runs. The returns come from timing and cash, not from stock selection." % (100 * p))
    if p > 0.025:
        return ("Leans toward real stock-selection skill (random picking matched it in %.1f%% of runs), but not convincingly. "
                "Remember we tested several variants, which makes lucky results more likely." % (100 * p))
    return ("Strong evidence of stock-selection skill: random picking matched it in only %.1f%% of runs. Re-check for look-ahead and "
            "survivorship effects before believing it." % (100 * p))


def block_bootstrap(equity: pd.Series, benchmarks: dict | None = None, n: int = 2000, block: int = 21,
                    seed: int = 19, rf: float = 0.06) -> dict:
    """Circular block bootstrap of daily returns. Returns 5/50/95 percentiles and P(beats each benchmark on CAGR)."""
    r = equity.pct_change().dropna().to_numpy()
    T = len(r)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(T / block))
    starts = rng.integers(0, T, size=(n, nb))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % T).reshape(n, -1)[:, :T].astype(np.int32)

    def stats(rets):
        cum = np.cumprod(1 + rets, axis=1)
        years = T / 252
        cagr = cum[:, -1] ** (1 / years) - 1
        vol = rets.std(axis=1, ddof=1) * np.sqrt(252)
        sharpe = (rets.mean(axis=1) * 252 - rf) / vol
        dd = (cum / np.maximum.accumulate(cum, axis=1) - 1).min(axis=1)
        return cagr, sharpe, dd

    cagr, sharpe, dd = stats(r[idx])
    q = lambda x: [float(np.percentile(x, v)) for v in (5, 50, 95)]
    out = {"cagr": q(cagr), "sharpe": q(sharpe), "max_drawdown": q(dd), "n": n, "block": block, "seed": seed,
           "p_beats": {}}
    for name, beq in (benchmarks or {}).items():
        br = beq.reindex(equity.index).ffill().pct_change().dropna().to_numpy()
        if len(br) == T:
            out["p_beats"][name] = float((cagr > stats(br[idx])[0]).mean())
    return out
