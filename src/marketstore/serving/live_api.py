"""Live market data API endpoints.

Adds real-time capabilities to the existing FastAPI app:
  GET /live/status              -> feed connection status & ticker states
  GET /live/quote/{ticker}      -> latest live quote for a ticker
  GET /live/features/{ticker}   -> current live features from online store
  GET /live/stream              -> SSE stream of real-time feature updates
  POST /live/start              -> start the live feed
  POST /live/stop               -> stop the live feed
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..data.live_feed import LiveFeed
from ..online.live_updater import LiveUpdater
from ..online.store import OnlineStore
from ..schema import FEATURE_NAMES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live"])

# Module-level state — initialized by init_live().
_feed: LiveFeed | None = None
_updater: LiveUpdater | None = None
_online: OnlineStore | None = None
_sse_queues: list[queue.Queue] = []


def init_live(online: OnlineStore, raw: dict | None = None) -> None:
    """Wire up the live feed and updater. Call once at app startup."""
    global _feed, _updater, _online
    _online = online

    provider = os.environ.get("LIVE_PROVIDER", "yfinance")
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    poll_interval = float(os.environ.get("LIVE_POLL_INTERVAL", "15"))
    bar_interval = int(os.environ.get("LIVE_BAR_INTERVAL", "60"))
    tickers_env = os.environ.get("LIVE_TICKERS", "AAPL,MSFT,GOOG,AMZN,NVDA,META,TSLA,JPM")
    tickers = [t.strip() for t in tickers_env.split(",") if t.strip()]

    _updater = LiveUpdater(
        online=online,
        bar_interval=bar_interval,
        on_feature_update=_broadcast_feature_update,
    )

    # Seed with historical data so features are available immediately
    if raw:
        for tk, df in raw.items():
            if tk.upper() in [t.upper() for t in tickers]:
                df_sorted = df.sort_values("date").tail(50)
                _updater.seed_history(
                    tk,
                    df_sorted["close"].astype(float).tolist(),
                    df_sorted["volume"].astype(float).tolist(),
                )

    _feed = LiveFeed(
        provider=provider,
        api_key=api_key if api_key else None,
        poll_interval=poll_interval,
    )
    _feed.subscribe(tickers)
    _feed.on_tick(_updater.on_tick)

    logger.info(
        "Live feed initialized: provider=%s, tickers=%s, bar_interval=%ds",
        provider, tickers, bar_interval,
    )


def _broadcast_feature_update(ticker: str, features: dict, ts: datetime) -> None:
    """Push feature updates to all connected SSE clients."""
    event = {
        "ticker": ticker,
        "features": {k: round(v, 6) for k, v in features.items()},
        "timestamp": ts.isoformat(),
    }
    dead = []
    for i, q in enumerate(_sse_queues):
        try:
            q.put_nowait(event)
        except queue.Full:
            dead.append(i)
    for i in reversed(dead):
        _sse_queues.pop(i)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/subscribe")
def subscribe_tickers(tickers: list[str]):
    """Add tickers to the live feed dynamically.

    Body: ["TSLA", "AMD", "NFLX"]
    """
    if _feed is None or _updater is None:
        raise HTTPException(503, "Live feed not initialized")
    cleaned = [t.strip().upper() for t in tickers if t.strip()]
    if not cleaned:
        raise HTTPException(400, "No valid tickers provided")
    _feed.subscribe(cleaned)
    return {"status": "subscribed", "added": cleaned}


@router.delete("/subscribe/{ticker}")
def unsubscribe_ticker(ticker: str):
    """Remove a ticker from the live feed."""
    if _feed is None:
        raise HTTPException(503, "Live feed not initialized")
    tk = ticker.strip().upper()
    _feed.unsubscribe([tk])
    return {"status": "unsubscribed", "removed": tk}


@router.post("/start")
def start_feed():
    """Start the live market data feed."""
    if _feed is None:
        raise HTTPException(503, "Live feed not initialized. Set LIVE_PROVIDER env var.")
    _feed.start_async()
    return {"status": "started", "provider": _feed.provider}


@router.post("/stop")
def stop_feed():
    """Stop the live market data feed."""
    if _feed is None:
        raise HTTPException(503, "Live feed not initialized")
    _feed.stop()
    if _updater:
        _updater.stop()
    return {"status": "stopped"}


@router.get("/status")
def feed_status():
    """Connection status and per-ticker state."""
    if _updater is None:
        return {"status": "not_initialized", "tickers": {}}
    return {
        "status": "running" if _feed and _feed._feed._running else "stopped",
        "provider": _feed.provider if _feed else None,
        "tickers": _updater.get_status(),
    }


@router.get("/quote/{ticker}")
def live_quote(ticker: str):
    """Latest live price for a ticker."""
    if _updater is None:
        raise HTTPException(503, "Live feed not initialized")
    quote = _updater.get_latest_quote(ticker.upper())
    if quote is None:
        raise HTTPException(404, f"No live data for {ticker.upper()}")
    return quote


@router.get("/features/{ticker}")
def live_features(ticker: str):
    """Current feature vector from the online store (updated by live feed)."""
    if _online is None:
        raise HTTPException(503, "Online store not available")
    vec = _online.get_online(ticker.upper())
    if not vec:
        raise HTTPException(404, f"No features for {ticker.upper()}")
    return {
        "ticker": ticker.upper(),
        "features": vec,
        "feature_names": FEATURE_NAMES,
    }


@router.get("/predict/{ticker}")
def live_predict(ticker: str):
    """Live prediction using the most recent features from the live feed."""
    if _online is None:
        raise HTTPException(503, "Online store not available")
    # Lazy import to avoid circular dependency
    from ..serving import api as _api_mod
    return _api_mod._server.predict_correct(ticker.upper())


@router.get("/stream")
async def stream_updates():
    """Server-Sent Events stream of real-time feature updates.

    Connect with: curl -N http://localhost:8000/live/stream
    Or from JS:   new EventSource('/live/stream')
    """
    from starlette.responses import StreamingResponse

    q: queue.Queue = queue.Queue(maxsize=100)
    _sse_queues.append(q)

    async def event_generator():
        try:
            yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"
            while True:
                try:
                    event = q.get_nowait()
                    yield f"event: feature_update\ndata: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send keepalive every 15s
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)
        finally:
            if q in _sse_queues:
                _sse_queues.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
