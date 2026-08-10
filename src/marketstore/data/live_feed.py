"""Real-time market data feed with two providers:

  1. Finnhub WebSocket  (true real-time, requires free API key from finnhub.io)
  2. yfinance polling    (near-real-time, no API key, ~15-sec granularity)

Both emit the same Tick dataclass via a callback, so the downstream feature
updater doesn't care which provider is running.

Usage:
    feed = LiveFeed(provider="finnhub", api_key="YOUR_KEY")
    feed.subscribe(["AAPL", "MSFT"])
    feed.on_tick(my_callback)   # callback(Tick) called on each trade
    feed.start()                # blocks; call .start_async() for background
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tick:
    """A single trade or quote update."""
    ticker: str
    price: float
    volume: float          # trade volume (0 for quote-only updates)
    timestamp: datetime    # exchange timestamp (UTC)
    source: str            # "finnhub" | "yfinance"


@dataclass
class TickBuffer:
    """Accumulates ticks into OHLCV bars at a configurable interval."""
    interval_seconds: int = 60
    _bars: dict = field(default_factory=dict)  # ticker -> list of ticks in current window
    _last_flush: dict = field(default_factory=dict)

    def add(self, tick: Tick) -> dict | None:
        """Add a tick. Returns a completed bar dict if the interval elapsed, else None."""
        tk = tick.ticker
        now = time.time()
        if tk not in self._last_flush:
            self._last_flush[tk] = now
            self._bars[tk] = []

        self._bars[tk].append(tick)

        if now - self._last_flush[tk] >= self.interval_seconds:
            bar = self._flush(tk)
            self._last_flush[tk] = now
            self._bars[tk] = []
            return bar
        return None

    def _flush(self, ticker: str) -> dict | None:
        ticks = self._bars.get(ticker, [])
        if not ticks:
            return None
        prices = [t.price for t in ticks]
        volumes = [t.volume for t in ticks]
        return {
            "ticker": ticker,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes),
            "timestamp": ticks[-1].timestamp,
        }

    def force_flush(self, ticker: str) -> dict | None:
        """Flush current window regardless of time."""
        bar = self._flush(ticker)
        if bar:
            self._bars[ticker] = []
            self._last_flush[ticker] = time.time()
        return bar


# ---------------------------------------------------------------------------
# Provider: Finnhub WebSocket
# ---------------------------------------------------------------------------
class FinnhubFeed:
    """Real-time trade stream via Finnhub's free WebSocket API.

    Sign up at https://finnhub.io — the free tier gives 60 API calls/min
    and real-time US stock trades via WebSocket.
    """

    def __init__(self, api_key: str):
        try:
            import websocket  # websocket-client package
        except ImportError as e:
            raise ImportError(
                "websocket-client is required for Finnhub live feed: "
                "pip install websocket-client"
            ) from e
        self._api_key = api_key
        self._tickers: list[str] = []
        self._callbacks: list[Callable[[Tick], None]] = []
        self._ws = None
        self._thread: threading.Thread | None = None
        self._running = False

    def subscribe(self, tickers: list[str]) -> None:
        self._tickers = [t.upper() for t in tickers]

    def on_tick(self, cb: Callable[[Tick], None]) -> None:
        self._callbacks.append(cb)

    def _on_message(self, ws, message: str) -> None:
        import json
        data = json.loads(message)
        if data.get("type") != "trade":
            return
        for trade in data.get("data", []):
            tick = Tick(
                ticker=trade["s"],
                price=float(trade["p"]),
                volume=float(trade["v"]),
                timestamp=datetime.fromtimestamp(trade["t"] / 1000, tz=timezone.utc),
                source="finnhub",
            )
            for cb in self._callbacks:
                try:
                    cb(tick)
                except Exception:
                    logger.exception("tick callback error")

    def _on_open(self, ws) -> None:
        import json
        for tk in self._tickers:
            ws.send(json.dumps({"type": "subscribe", "symbol": tk}))
        logger.info("Finnhub WS subscribed to %s", self._tickers)

    def _on_error(self, ws, error) -> None:
        logger.error("Finnhub WS error: %s", error)

    def _on_close(self, ws, close_status, close_msg) -> None:
        logger.info("Finnhub WS closed: %s %s", close_status, close_msg)

    def start(self) -> None:
        """Connect and block (runs the WebSocket event loop)."""
        import websocket
        self._running = True
        self._ws = websocket.WebSocketApp(
            f"wss://ws.finnhub.io?token={self._api_key}",
            on_message=self._on_message,
            on_open=self._on_open,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever()

    def start_async(self) -> threading.Thread:
        """Start in a background thread. Returns the thread."""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._running = False
        if self._ws:
            self._ws.close()


# ---------------------------------------------------------------------------
# Provider: yfinance polling (no API key needed)
# ---------------------------------------------------------------------------
class YFinanceFeed:
    """Near-real-time quotes via yfinance polling.

    No API key required. Polls at a configurable interval (default 15s).
    Good fallback when you don't have a Finnhub key.
    """

    def __init__(self, poll_interval: float = 15.0):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:
            raise ImportError("yfinance is required: pip install yfinance") from e
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._callbacks: list[Callable[[Tick], None]] = []
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def subscribe(self, tickers: list[str]) -> None:
        with self._lock:
            for t in tickers:
                if t.upper() not in self._tickers:
                    self._tickers.append(t.upper())

    def unsubscribe(self, tickers: list[str]) -> None:
        with self._lock:
            for t in tickers:
                try:
                    self._tickers.remove(t.upper())
                except ValueError:
                    pass

    def on_tick(self, cb: Callable[[Tick], None]) -> None:
        self._callbacks.append(cb)

    def _poll_once(self) -> list[Tick]:
        import yfinance as yf
        ticks = []
        with self._lock:
            current_tickers = list(self._tickers)
        if not current_tickers:
            return ticks
        # Batch download for efficiency
        tickers_str = " ".join(current_tickers)
        try:
            data = yf.download(
                tickers_str, period="1d", interval="1m",
                progress=False, group_by="ticker",
            )
        except Exception:
            logger.exception("yfinance poll failed")
            return ticks

        now = datetime.now(timezone.utc)
        for tk in current_tickers:
            try:
                if len(self._tickers) > 1:
                    df = data[tk] if tk in data.columns.get_level_values(0) else None
                else:
                    df = data
                if df is None or df.empty:
                    continue
                last = df.iloc[-1]
                tick = Tick(
                    ticker=tk,
                    price=float(last["Close"].iloc[0]) if hasattr(last["Close"], "iloc") else float(last["Close"]),
                    volume=float(last["Volume"].iloc[0]) if hasattr(last["Volume"], "iloc") else float(last["Volume"]),
                    timestamp=now,
                    source="yfinance",
                )
                ticks.append(tick)
            except Exception:
                logger.exception("failed to parse %s quote", tk)
        return ticks

    def _poll_loop(self) -> None:
        while self._running:
            ticks = self._poll_once()
            for tick in ticks:
                for cb in self._callbacks:
                    try:
                        cb(tick)
                    except Exception:
                        logger.exception("tick callback error")
            time.sleep(self._interval)

    def start(self) -> None:
        self._running = True
        self._poll_loop()

    def start_async(self) -> threading.Thread:
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Unified LiveFeed facade
# ---------------------------------------------------------------------------
class LiveFeed:
    """Unified interface over Finnhub or yfinance.

    Examples:
        # With Finnhub (real-time):
        feed = LiveFeed(provider="finnhub", api_key="YOUR_KEY")

        # With yfinance (polling, no key needed):
        feed = LiveFeed(provider="yfinance", poll_interval=15)

        feed.subscribe(["AAPL", "MSFT", "GOOG"])
        feed.on_tick(lambda t: print(t))
        feed.start_async()
    """

    def __init__(
        self,
        provider: str = "yfinance",
        api_key: str | None = None,
        poll_interval: float = 15.0,
    ):
        if provider == "finnhub":
            if not api_key:
                raise ValueError("Finnhub requires an api_key (free at finnhub.io)")
            self._feed = FinnhubFeed(api_key)
        elif provider == "yfinance":
            self._feed = YFinanceFeed(poll_interval=poll_interval)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Use 'finnhub' or 'yfinance'.")
        self.provider = provider

    def subscribe(self, tickers: list[str]) -> None:
        self._feed.subscribe(tickers)

    def unsubscribe(self, tickers: list[str]) -> None:
        if hasattr(self._feed, 'unsubscribe'):
            self._feed.unsubscribe(tickers)

    def on_tick(self, cb: Callable[[Tick], None]) -> None:
        self._feed.on_tick(cb)

    def start(self) -> None:
        self._feed.start()

    def start_async(self) -> threading.Thread:
        return self._feed.start_async()

    def stop(self) -> None:
        self._feed.stop()
