"""Zerodha equity-delivery trading costs (NSE). Rates change - verify against Zerodha's brokerage calculator."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryCosts:
    brokerage: float = 0.0            # equity delivery is free at Zerodha
    stt_rate: float = 0.001           # 0.1% on BOTH buy and sell (the big one)
    exch_txn_rate: float = 0.0000322  # NSE 0.00322% each side
    sebi_rate: float = 0.000001       # Rs 10 per crore
    stamp_rate: float = 0.00015       # 0.015%, buy side only
    gst_rate: float = 0.18            # on brokerage + exchange charge + SEBI fee (not on STT/stamp)
    dp_charge: float = 13.5           # per scrip on SELL, plus GST

    def charges(self, side: str, value: float) -> float:
        exch = value * self.exch_txn_rate
        sebi = value * self.sebi_rate
        gst = self.gst_rate * (self.brokerage + exch + sebi)
        total = self.brokerage + value * self.stt_rate + exch + sebi + gst
        if side.upper() == "BUY":
            total += value * self.stamp_rate
        else:
            total += self.dp_charge * (1 + self.gst_rate)
        return total
