"""Connects the live data feed to the online feature store.

On each incoming tick (or completed bar), recomputes the four features using a
rolling window of recent prices/volumes, then writes the updated feature vector
into the OnlineStore — exactly the same features the batch pipeline computes,
but incrementally, from a streaming source.

This is the production-faithful path: at time T, the online store only holds
values that were knowable at T, because the live feed literally cannot deliver
future data.

Usage:
    updater = LiveUpdater(online_store)
    feed = LiveFeed(provider="yfinance")
    feed.subscribe(["AAPL", "MSFT"])
    feed.on_tick(updater.on_tick)
    feed.start_async()
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd

from ..data.live_feed import Tick, TickBuffer
from ..online.store import OnlineStore
from ..schema import FEATURE_NAMES

logger = logging.getLogger(__name__)


@dataclass
class _TickerState:
    """Rolling window of recent closes and volumes for one ticker."""
    closes: deque = field(default_factory=lambda: deque(maxlen=50))
    volumes: deque = field(default_factory=lambda: deque(maxlen=50))
    last_price: float | None = None
    last_volume: float | None = None
    last_update: datetime | None = None
    tick_count: int = 0


def _compute_live_features(closes: list[float], volumes: list[float]) -> dict | None:
    """Compute the four features from a price/volume history.

    Mirrors the 'correct' mode in offline/features.py but operates on
    in-memory arrays instead of a DataFrame.
    """
    if len(closes) < 21:
        # Need at least 21 bars for the 20-day return
        return None

    close = np.array(closes, dtype=float)
    vol = np.array(volumes, dtype=float)
    logret = np.diff(np.log(close))

    features = {}

    # rolling_5d_volatility: std of last 5 log-returns
    if len(logret) >= 5:
        features["rolling_5d_volatility"] = float(np.std(logret[-5:], ddof=1))

    # rolling_20d_return: price change over last 20 bars
    if len(close) >= 21:
        features["rolling_20d_return"] = float((close[-1] - close[-21]) / close[-21])

    # price_momentum_10d: price change over last 10 bars
    if len(close) >= 11:
        features["price_momentum_10d"] = float((close[-1] - close[-11]) / close[-11])

    # volume_zscore: expanding-window z-score (mean/std of all available volume)
    if len(vol) >= 20:
        mean_v = float(np.mean(vol))
        std_v = float(np.std(vol, ddof=1))
        if std_v > 0:
            features["volume_zscore"] = float((vol[-1] - mean_v) / std_v)

    if len(features) == 4:
        return features
    return None


class LiveUpdater:
    """Receives ticks from a LiveFeed and pushes updated features into the OnlineStore."""

    def __init__(
        self,
        online: OnlineStore,
        bar_interval: int = 60,
        on_feature_update: Callable[[str, dict, datetime], None] | None = None,
    ):
        self.online = online
        self.buffer = TickBuffer(interval_seconds=bar_interval)
        self._state: dict[str, _TickerState] = defaultdict(_TickerState)
        self._lock = threading.Lock()
        self._on_feature_update = on_feature_update  # optional callback for SSE
        self._running = True

    def on_tick(self, tick: Tick) -> None:
        """Callback wired to LiveFeed.on_tick(). Thread-safe."""
        if not self._running:
            return

        with self._lock:
            state = self._state[tick.ticker]
            state.last_price = tick.price
            state.last_volume = tick.volume
            state.last_update = tick.timestamp
            state.tick_count += 1

            # Accumulate into bar
            bar = self.buffer.add(tick)
            if bar is not None:
                self._on_bar(tick.ticker, bar)

    def _on_bar(self, ticker: str, bar: dict) -> None:
        """A new OHLCV bar completed — update features."""
        state = self._state[ticker]
        state.closes.append(bar["close"])
        state.volumes.append(bar["volume"])

        features = _compute_live_features(
            list(state.closes), list(state.volumes)
        )
        if features is None:
            return

        now = datetime.now(timezone.utc)
        # Write into the online store
        self.online.write_vector(ticker, features, now)
        logger.info("features updated for %s: %s", ticker, features)

        if self._on_feature_update:
            try:
                self._on_feature_update(ticker, features, now)
            except Exception:
                logger.exception("feature update callback error")

    def get_status(self) -> dict:
        """Current state of all tracked tickers."""
        with self._lock:
            return {
                tk: {
                    "last_price": s.last_price,
                    "last_volume": s.last_volume,
                    "last_update": s.last_update.isoformat() if s.last_update else None,
                    "tick_count": s.tick_count,
                    "bars_accumulated": len(s.closes),
                    "features_ready": len(s.closes) >= 21,
                }
                for tk, s in self._state.items()
            }

    def get_latest_quote(self, ticker: str) -> dict | None:
        """Return the last known price for a ticker."""
        with self._lock:
            state = self._state.get(ticker.upper())
            if state is None or state.last_price is None:
                return None
            return {
                "ticker": ticker.upper(),
                "price": state.last_price,
                "volume": state.last_volume,
                "timestamp": state.last_update.isoformat() if state.last_update else None,
                "tick_count": state.tick_count,
            }

    def seed_history(self, ticker: str, closes: list[float], volumes: list[float]) -> None:
        """Pre-load historical bars so features are available immediately.

        Call this with the last ~50 daily closes/volumes from your raw data
        before starting the live feed, so you don't have to wait for 21 bars.
        """
        with self._lock:
            state = self._state[ticker.upper()]
            for c, v in zip(closes, volumes):
                state.closes.append(c)
                state.volumes.append(v)

    def stop(self) -> None:
        self._running = False
