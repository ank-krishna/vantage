"""The headline demo.

Same model, same split, same held-out window — evaluated through two feature
paths:

  correct: features joined point-in-time (knowable at each decision date)
  leaked:  features from a naively-built offline store (full-sample z-scores,
           final revised prices) — i.e. online/offline skew left uncorrected

If the leaked path reports materially better backtest performance than the
correct path, that gap is pure illusion: it is model quality you would never see
in production, because production only ever has the correct (online) features.

Metrics per path: accuracy, ROC-AUC, and the cumulative return of a toy
long/short strategy that goes long when p(up) > 0.5 and short otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

from ..offline.store import OfflineStore
from ..schema import FEATURE_NAMES
from ..training.train import build_labels, build_matrix, fit, time_split


def _realized_returns(raw: dict) -> dict:
    """Next-day realized return per (entity, date) — the shared ground truth."""
    out = {}
    for tk, df in raw.items():
        d = df.sort_values("date").reset_index(drop=True)
        r = d["close"].pct_change().shift(-1)
        out[tk] = dict(zip(pd.to_datetime(d["date"]), r))
    return out


def _sharpe(
    test: pd.DataFrame,
    proba_up: np.ndarray,
    ret_lookup: dict,
    tc_bps: float = 5.0,
    slippage_bps: float = 2.0,
    max_position: float = 0.1,
) -> float:
    """Annualized Sharpe of a long/short book with realistic frictions.

    Improvements over a naive long/short:
      - Continuous position sizing: position = 2*(p - 0.5), clipped to max_position,
        so low-confidence signals get small allocations instead of binary +1/-1.
      - Transaction costs: charged on absolute position changes each day (tc_bps).
      - Slippage: modeled as additional cost proportional to position size (slippage_bps).
      - Per-entity grouping: positions are tracked per ticker so turnover is measured
        correctly across a multi-name book.
    """
    bps = 1e-4

    # Group by entity so we can measure per-name turnover correctly
    entities = test["entity_id"].values
    timestamps = test["request_time"].values
    unique_entities = sorted(set(entities))

    realized = np.nan_to_num(np.array([
        ret_lookup[e].get(t, 0.0)
        for e, t in zip(entities, timestamps)
    ]))

    # Continuous position sizing: scale by conviction
    raw_pos = 2.0 * (proba_up - 0.5)  # range [-1, 1]
    pos = np.clip(raw_pos, -max_position, max_position)

    # Gross P&L before costs
    gross_pnl = pos * realized

    # Compute turnover (position changes) per entity
    turnover = np.zeros_like(pos)
    for eid in unique_entities:
        mask = entities == eid
        entity_pos = pos[mask]
        # First position is full turnover; subsequent is abs change
        changes = np.abs(np.diff(entity_pos, prepend=0.0))
        turnover[mask] = changes

    # Cost model: transaction cost on turnover + slippage on position size
    cost = turnover * tc_bps * bps + np.abs(pos) * slippage_bps * bps
    net_pnl = gross_pnl - cost

    if net_pnl.std() == 0:
        return 0.0
    return float(net_pnl.mean() / net_pnl.std() * np.sqrt(252))


def run_backtest(offline: OfflineStore, raw: dict, train_frac: float = 0.7) -> pd.DataFrame:
    """Evaluate both feature paths on IDENTICAL rows and an identical split.

    Fairness matters: the only thing allowed to differ between the two paths is
    the feature *values*, never which rows or which split they see. So we join
    the two matrices to a common (entity, date) key set and split once.
    """
    labels = build_labels(raw)
    m_correct = build_matrix(offline, labels, "correct")
    m_leaked = build_matrix(offline, labels, "leaked")

    key = ["entity_id", "request_time"]
    common = m_correct.merge(m_leaked[key], on=key, how="inner")[key].drop_duplicates()
    m_correct = m_correct.merge(common, on=key).sort_values(key).reset_index(drop=True)
    m_leaked = m_leaked.merge(common, on=key).sort_values(key).reset_index(drop=True)

    cut = m_correct["request_time"].quantile(train_frac)  # one split for both
    ret_lookup = _realized_returns(raw)

    rows = []
    for variant, m in [("correct", m_correct), ("leaked", m_leaked)]:
        train = m[m["request_time"] <= cut]
        test = m[m["request_time"] > cut]
        model = fit(train)
        proba = model.predict_proba(test[FEATURE_NAMES])[:, 1]
        pred = (proba > 0.5).astype(int)
        rows.append({
            "variant": variant,
            "n_train": len(train),
            "n_test": len(test),
            "split_date": str(pd.Timestamp(cut).date()),
            "accuracy": round(float(accuracy_score(test["label"], pred)), 4),
            "roc_auc": round(float(roc_auc_score(test["label"], proba)), 4),
            "strategy_sharpe": round(_sharpe(test, proba, ret_lookup), 3),
        })
    return pd.DataFrame(rows)
