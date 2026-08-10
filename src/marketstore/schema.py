"""Core data model for the feature store.

The entire point-in-time story rests on distinguishing two timestamps:

  event_timestamp
      When the fact became true in the world. For a daily feature about
      trading day D, the fact is "true as of" the close of D.

  knowledge_timestamp  (a.k.a. `available_at`, Feast calls it `created_timestamp`)
      When our system could actually *know* the value. This is >= event_timestamp
      whenever data arrives late or is revised. It is the timestamp a
      point-in-time-correct read must filter on: "give me what was knowable at T",
      not "what turned out to be true about T".

A feature store is correct iff, for any request time T, it returns exactly the
values whose knowledge_timestamp <= T. Everything else in this repo is machinery
to guarantee that and a demo of what breaks when you don't.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Iterable

import pandas as pd

# The canonical column set for a feature row. Kept as a module constant so the
# offline store, online store, and consistency checks all agree on the schema.
FEATURE_COLUMNS = [
    "entity_id",          # e.g. ticker "AAPL"
    "feature_name",       # e.g. "volume_zscore"
    "value",              # float
    "event_timestamp",    # when the fact became true in the world (the trading day)
    "knowledge_timestamp",  # when the system could know it (>= event_timestamp)
]

FEATURE_NAMES = [
    "rolling_5d_volatility",
    "rolling_20d_return",
    "volume_zscore",
    "price_momentum_10d",
]


@dataclass(frozen=True)
class FeatureRow:
    entity_id: str
    feature_name: str
    value: float
    event_timestamp: datetime
    knowledge_timestamp: datetime

    def __post_init__(self) -> None:
        if self.knowledge_timestamp < self.event_timestamp:
            # A value cannot be known before it is true. This is an invariant,
            # not a soft warning: violating it means the pipeline invented data.
            raise ValueError(
                f"knowledge_timestamp {self.knowledge_timestamp} precedes "
                f"event_timestamp {self.event_timestamp} for "
                f"{self.entity_id}/{self.feature_name}"
            )


def to_frame(rows: Iterable[FeatureRow]) -> pd.DataFrame:
    df = pd.DataFrame([r.__dict__ for r in rows], columns=FEATURE_COLUMNS)
    return _coerce(df)


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(FEATURE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"feature frame missing columns: {sorted(missing)}")
    df = df.copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    df["knowledge_timestamp"] = pd.to_datetime(df["knowledge_timestamp"])
    bad = df["knowledge_timestamp"] < df["event_timestamp"]
    if bad.any():
        raise ValueError(
            f"{int(bad.sum())} rows have knowledge_timestamp < event_timestamp"
        )
    return df[FEATURE_COLUMNS]


def as_datetime(t) -> datetime:
    if isinstance(t, datetime):
        return t
    if isinstance(t, date):
        return datetime(t.year, t.month, t.day)
    return pd.to_datetime(t).to_pydatetime()
