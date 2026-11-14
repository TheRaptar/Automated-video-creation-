#!/usr/bin/env python3
"""How much does smart order slicing (VWAP/TWAP) matter at YOUR order sizes? Model-based estimate, not a promise."""
import argparse

from algo.execution import front_loaded_schedule, schedule_cost_bps, twap_schedule, vwap_schedule

ap = argparse.ArgumentParser()
ap.add_argument("--adv-crore", type=float, default=50, help="average daily traded value of the stock, in Rs crore")
ap.add_argument("--price", type=float, default=1000)
ap.add_argument("--sigma", type=float, default=0.015, help="daily volatility")
a = ap.parse_args()
adv_shares = a.adv_crore * 1e7 / a.price
print(f"Stock: Rs {a.adv_crore:g} crore/day, price Rs {a.price:g}, daily volatility {a.sigma:.1%}  (one-way cost in basis points)\n")
print(f"{'order size':>12} {'% of ADV':>9} {'15-min dump':>12} {'TWAP':>8} {'VWAP':>8} {'VWAP saves vs TWAP':>20}")
for lakh in (1, 10, 100, 500, 2500):
    value = lakh * 1e5
    q = int(value / a.price)
    c = {n: schedule_cost_bps(s(q), adv_shares, a.sigma) for n, s in
         (("dump", front_loaded_schedule), ("twap", twap_schedule), ("vwap", vwap_schedule))}
    saving_rs = (c["twap"] - c["vwap"]) / 1e4 * value
    print(f"{'Rs %g lakh' % lakh:>12} {value / (a.adv_crore * 1e7):>9.2%} {c['dump']:>12.1f} {c['twap']:>8.1f} {c['vwap']:>8.1f} {'Rs %.0f per trade' % saving_rs:>20}")
print("\nFor comparison: STT alone is 10 bps per side on delivery trades, and it cannot be optimised away.")
