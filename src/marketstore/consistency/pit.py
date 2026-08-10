"""Online/offline consistency reconciliation.

The claim a feature store must earn: the value a model trains on (offline, as-of)
is byte-for-byte the value it will be served in production (online) for the same
entity at the same instant. We don't assert this — we check it, at many random
(entity, time) points, against two things at once:

  * offline `correct` as-of read      == online reconstruct-as-of   -> MUST match
  * offline `leaked`  as-of read      vs online reconstruct-as-of   -> the skew

The first equality is the correctness guarantee. The second quantifies exactly
how far a naively-built offline store drifts from what production actually serves
— the silent skew that corrupts model evaluation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..offline.store import OfflineStore
from ..online.store import OnlineStore
from ..schema import FEATURE_NAMES


def reconcile(
    offline: OfflineStore,
    online: OnlineStore,
    check_points: pd.DataFrame,
    tol: float = 1e-9,
) -> pd.DataFrame:
    """For each (entity_id, request_time), compare offline reads to the online
    reconstruction. Returns a per-check report."""
    rows = []
    for cp in check_points.itertuples(index=False):
        entity, t = cp.entity_id, pd.Timestamp(cp.request_time)
        off_correct = offline.asof_single(entity, t, variant="correct")
        off_leaked = offline.asof_single(entity, t, variant="leaked")
        onl = online.reconstruct_asof(entity, FEATURE_NAMES, t)

        for feat in FEATURE_NAMES:
            oc, ol, on = off_correct.get(feat), off_leaked.get(feat), onl.get(feat)
            rows.append({
                "entity_id": entity,
                "request_time": t,
                "feature_name": feat,
                "offline_correct": oc,
                "offline_leaked": ol,
                "online": on,
                "correct_matches_online": _close(oc, on, tol),
                "leaked_matches_online": _close(ol, on, tol),
            })
    return pd.DataFrame(rows)


def _close(a, b, tol) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol * (1 + abs(float(b)))


def summarize(report: pd.DataFrame) -> dict:
    comparable = report.dropna(subset=["online"])
    correct_ok = comparable["correct_matches_online"].mean()
    leaked_ok = comparable["leaked_matches_online"].mean()
    # magnitude of the leaked-vs-online skew where both present
    both = report.dropna(subset=["offline_leaked", "online"])
    skew = (both["offline_leaked"] - both["online"]).abs()
    return {
        "n_checks": len(report),
        "n_comparable": len(comparable),
        "correct_matches_online_frac": round(float(correct_ok), 6),
        "leaked_matches_online_frac": round(float(leaked_ok), 6),
        "mean_abs_leaked_skew": round(float(skew.mean()), 6),
        "max_abs_leaked_skew": round(float(skew.max()), 6),
    }
