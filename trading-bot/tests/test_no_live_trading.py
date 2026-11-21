"""Safety net: this project is in RESEARCH / PAPER mode. No code path may talk to a broker or place an order."""
import pathlib
import re

FORBIDDEN = [r"kiteconnect", r"KiteConnect", r"place_order", r"kite\.trade", r"api\.kite", r"zerodha\.com/api", r"alpaca", r"order_place",
             r"smartapi", r"upstox", r"fyers", r"angelone"]
ROOT = pathlib.Path(__file__).resolve().parent.parent


def source_files():
    return [p for p in list(ROOT.glob("algo/*.py")) + list(ROOT.glob("run_*.py"))]


def test_no_broker_or_order_placement_code_exists():
    hits = []
    for p in source_files():
        text = p.read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            if re.search(pat, text, flags=re.I):
                hits.append((p.name, pat))
    assert not hits, f"broker/order code found (live trading is not allowed in this phase): {hits}"


def test_risk_gate_has_no_network_imports():
    text = (ROOT / "algo" / "risk_gate.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(requests|urllib|socket|http)", text, flags=re.M)
