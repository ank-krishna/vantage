"""One place that wires the components together, so scripts and tests share a
single build path.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data.generate import generate_universe, write_raw
from .offline.features import compute_universe
from .offline.store import OfflineStore
from .online.replay import replay_into_online
from .online.store import OnlineStore

DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "JPM"]


def load_or_generate_raw(raw_dir: str | Path, regenerate: bool = False) -> dict:
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob("*.parquet"))
    if regenerate or not files:
        uni = generate_universe(DEFAULT_TICKERS)
        write_raw(uni, raw_dir)
        return uni
    return {f.stem: pd.read_parquet(f) for f in files}


def build_offline(raw: dict, db_path: str = ":memory:") -> OfflineStore:
    store = OfflineStore(db_path)
    store.write(compute_universe(raw, "correct"), "correct")
    store.write(compute_universe(raw, "leaked"), "leaked")
    return store


def build_online(raw: dict) -> OnlineStore:
    online = OnlineStore()
    correct = compute_universe(raw, "correct")
    replay_into_online(correct, online)
    return online


def build_all(raw_dir: str | Path = "data_raw", db_path: str = ":memory:"):
    raw = load_or_generate_raw(raw_dir)
    offline = build_offline(raw, db_path)
    online = build_online(raw)
    return raw, offline, online
