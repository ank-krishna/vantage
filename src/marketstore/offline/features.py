"""Batch feature computation, in two variants that differ ONLY in what data
they were allowed to see.

correct (as-of)
    Every feature for trading day D uses only information knowable by close of D.
      - prices: the first print, until a later revision becomes knowable
      - normalization (z-score): expanding window statistics (past only)
    knowledge_timestamp reflects when the value could actually be known.

leaked (naive)
    The two most common real-world leaks, deliberately reproduced:
      - uses the FINAL revised close for every day, even days whose revision
        wasn't knowable until later  -> revision leak
      - z-score uses FULL-SAMPLE mean/std (includes future rows)  -> normalization leak
    Its knowledge_timestamp is (wrongly) set equal to event_timestamp, which is
    exactly the lie a naive pipeline tells itself.

A streaming online store can only ever reproduce the `correct` variant, because
at time D it physically does not have D+1's data. So `leaked` is precisely the
online/offline skew this project exists to catch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schema import FEATURE_COLUMNS


def _knowable_close(bars: pd.DataFrame) -> pd.Series:
    """The close as it was first knowable on each event day (first print)."""
    return bars["first_print_close"].astype(float)


def _compute_raw_features(close: pd.Series, volume: pd.Series, mode: str) -> pd.DataFrame:
    """Windowed price features.

    correct: every window is strictly trailing (ends on the event day) -> causal.
    leaked:  windows peek one bar into the future -- the canonical off-by-one a
             batch job makes when it computes features over the whole dataframe
             and forgets to lag. A streaming pipeline literally cannot make this
             mistake, so it is a textbook online/offline skew.
    """
    logret = np.log(close).diff()
    feats = pd.DataFrame(index=close.index)
    if mode == "correct":
        feats["rolling_5d_volatility"] = logret.rolling(5).std()
        feats["rolling_20d_return"] = close.pct_change(20)
        feats["price_momentum_10d"] = close.pct_change(10)
    else:
        # centered window (peeks ahead) and a forward-shifted momentum: both
        # import information from bars that postdate the decision.
        feats["rolling_5d_volatility"] = logret.rolling(5, center=True).std()
        feats["rolling_20d_return"] = close.pct_change(20).shift(-2)
        feats["price_momentum_10d"] = close.pct_change(10).shift(-1)
    feats["_volume"] = volume.astype(float)
    return feats


def compute_features(bars: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Return a long feature frame for one ticker.

    mode = 'correct'  -> as-of prices, expanding-window z-score, honest knowledge ts
    mode = 'leaked'   -> final prices, full-sample z-score, knowledge ts == event ts
    """
    if mode not in {"correct", "leaked"}:
        raise ValueError(mode)

    bars = bars.sort_values("date").reset_index(drop=True)
    entity = bars["ticker"].iloc[0]

    if mode == "correct":
        # As-of behavior: we only ever use the value that was knowable on the
        # event day itself (the first print). We never retroactively adopt a
        # later revision into a past feature, so knowledge == event day.
        close = _knowable_close(bars)                 # first print
        knowledge = bars["date"]
    else:
        # The leak: use the FINAL revised close everywhere, and pretend it was
        # knowable on the event day. In reality the revision only landed days
        # later (see raw `knowledge_date`), so this silently imports the future.
        close = bars["close"].astype(float)           # final revised close
        knowledge = bars["date"]

    feats = _compute_raw_features(close, bars["volume"], mode)

    # --- the z-score: the crux of the normalization leak -----------------------
    vol = feats["_volume"]
    if mode == "correct":
        # expanding window: at row t, use only rows [0..t]
        mean = vol.expanding(min_periods=20).mean()
        std = vol.expanding(min_periods=20).std()
    else:
        # full-sample constants: every row peeks at the entire (incl. future) series
        mean = pd.Series(vol.mean(), index=vol.index)
        std = pd.Series(vol.std(), index=vol.index)
    feats["volume_zscore"] = (vol - mean) / std
    feats = feats.drop(columns="_volume")

    # --- reshape to the canonical long schema ---------------------------------
    feats["event_timestamp"] = pd.to_datetime(bars["date"])
    feats["knowledge_timestamp"] = pd.to_datetime(knowledge)
    long = feats.melt(
        id_vars=["event_timestamp", "knowledge_timestamp"],
        var_name="feature_name", value_name="value",
    )
    long["entity_id"] = entity
    long = long.dropna(subset=["value"])
    # knowledge can't precede event (revision lag only pushes it later)
    long["knowledge_timestamp"] = long[["event_timestamp", "knowledge_timestamp"]].max(axis=1)
    return long[FEATURE_COLUMNS]


def compute_universe(raw: dict[str, pd.DataFrame], mode: str) -> pd.DataFrame:
    return pd.concat([compute_features(df, mode) for df in raw.values()], ignore_index=True)
