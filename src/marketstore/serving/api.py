"""FastAPI surface: demo endpoints + real-time live market data.

Run:  PYTHONPATH=src uvicorn marketstore.serving.api:app --reload

Endpoints:
  GET  /health
  GET  /predict/{ticker}            -> live prediction from the online store
  GET  /predict/{ticker}/buggy?as_of=YYYY-MM-DD
                                    -> same model, leaked features (skew demo)
  GET  /backtest                    -> correct vs leaked evaluation table
  GET  /consistency?n=...           -> online/offline reconciliation summary

  Live market data (prefix /live):
  POST /live/start                  -> start the live feed
  POST /live/stop                   -> stop the live feed
  GET  /live/status                 -> feed connection + ticker states
  GET  /live/quote/{ticker}         -> latest live price
  GET  /live/features/{ticker}      -> current live feature vector
  GET  /live/predict/{ticker}       -> live prediction from streaming features
  GET  /live/stream                 -> SSE stream of real-time feature updates

  Dashboard:
  GET  /                            -> live trading dashboard UI
"""
from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from ..backtest.run import run_backtest
from ..consistency.pit import reconcile, summarize
from ..pipeline import build_all
from ..schema import FEATURE_NAMES
from ..training.train import build_labels, build_matrix, fit, time_split
from .predict import Server
from .live_api import router as live_router, init_live
from .dashboard import DASHBOARD_HTML

app = FastAPI(title="marketstore", version="0.2.0")

# Build once at startup and hold in module state.
_raw, _offline, _online = build_all()
_labels = build_labels(_raw)
_train, _, _ = time_split(build_matrix(_offline, _labels, "correct"))
_model = fit(_train)
_server = Server(_model, _online, _offline)

# Wire up live feed endpoints and seed with historical data.
init_live(_online, _raw)
app.include_router(live_router)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Live trading dashboard."""
    return DASHBOARD_HTML


@app.get("/health")
def health():
    return {"status": "ok", "tickers": sorted(_raw.keys()), "features": FEATURE_NAMES}


@app.get("/predict/{ticker}")
def predict(ticker: str):
    return _server.predict_correct(ticker.upper())


@app.get("/predict/{ticker}/buggy")
def predict_buggy(ticker: str, as_of: str = Query(..., description="YYYY-MM-DD")):
    return _server.predict_buggy(ticker.upper(), pd.Timestamp(as_of))


@app.get("/backtest")
def backtest():
    return run_backtest(_offline, _raw).to_dict(orient="records")


@app.get("/consistency")
def consistency(n: int = 300):
    import numpy as np
    rng = np.random.default_rng(0)
    rows = []
    for tk, df in _raw.items():
        dates = pd.to_datetime(df["date"]).sort_values().to_numpy()
        pool = dates[len(dates) // 2:]
        for t in rng.choice(pool, size=max(1, n // len(_raw)), replace=False):
            rows.append({"entity_id": tk, "request_time": pd.Timestamp(t)})
    report = reconcile(_offline, _online, pd.DataFrame(rows))
    return summarize(report)
