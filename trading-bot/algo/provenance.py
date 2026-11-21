"""Data provenance: every dataset carries a status, so verified data is never confused with estimates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

STATUS_HELP = {
    "VERIFIED": "downloaded from the primary source AND passed the automated checks",
    "UNCONFIRMED": "from a secondary source (e.g. Yahoo) that passed the automated checks but was not reconciled with the exchange",
    "ESTIMATED": "derived or approximated from other data (size of the error unknown)",
    "ASSUMED": "a constant or rule of thumb, not data",
    "INCOMPLETE": "partial coverage: usable only for the stated range",
    "UNAVAILABLE": "could not be obtained",
}


@dataclass
class Entry:
    name: str
    status: str
    source: str
    note: str = ""
    rows: int | None = None
    start: str | None = None
    end: str | None = None
    fingerprint: str | None = None
    checks: dict = field(default_factory=dict)


class Manifest:
    def __init__(self):
        self.entries: dict[str, Entry] = {}

    def add(self, name: str, status: str, source: str, note: str = "", series=None, **checks) -> Entry:
        if status not in STATUS_HELP:
            raise ValueError(f"unknown status {status}")
        rows = start = end = fp = None
        if series is not None and len(series):
            s = series.dropna(how="all") if hasattr(series, "dropna") else series
            if len(s):
                rows, start, end = len(s), str(s.index[0].date()), str(s.index[-1].date())
                fp = hashlib.sha1(pd.util.hash_pandas_object(s, index=True).values.tobytes()).hexdigest()[:12]
        e = Entry(name, status, source, note, rows, start, end, fp, checks)
        self.entries[name] = e
        return e

    def status(self, name: str) -> str:
        return self.entries[name].status if name in self.entries else "UNAVAILABLE"

    def all_verified(self, names) -> bool:
        return all(self.status(n) == "VERIFIED" for n in names)

    def to_markdown(self) -> str:
        lines = ["| Dataset | Status | Source | Coverage | Notes |", "|---|---|---|---|---|"]
        for e in self.entries.values():
            cov = f"{e.start} to {e.end} ({e.rows:,} rows)" if e.rows else "-"
            lines.append(f"| {e.name} | **{e.status}** | {e.source} | {cov} | {e.note} |")
        lines += ["", "Status legend: " + "; ".join(f"**{k}** = {v}" for k, v in STATUS_HELP.items()) + "."]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {k: asdict(v) for k, v in self.entries.items()}

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")

    def merge(self, other: "Manifest") -> None:
        self.entries.update(other.entries)
