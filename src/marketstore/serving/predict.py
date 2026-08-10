"""Serving paths.

correct path (production-faithful)
    Reads the live feature vector from the ONLINE store — the same values,
    produced by the same causal streaming pipeline, that the model saw as
    point-in-time-correct features during training. Train/serve are consistent.

buggy path (what online/offline skew looks like at serving time)
    Reads features from the naively-built (leaked) OFFLINE table. In a real
    system this is the "we'll just reuse the batch features for serving" shortcut
    that quietly serves values the streaming path would never produce.

Both share one trained model, so any difference in output is attributable purely
to feature skew — which is the failure mode the store exists to prevent.
"""
from __future__ import annotations

import pandas as pd

from ..offline.store import OfflineStore
from ..online.store import OnlineStore
from ..schema import FEATURE_NAMES


class Server:
    def __init__(self, model, online: OnlineStore, offline: OfflineStore):
        self.model = model
        self.online = online
        self.offline = offline

    def _vector_to_row(self, vec: dict) -> pd.DataFrame | None:
        if not all(f in vec for f in FEATURE_NAMES):
            return None
        return pd.DataFrame([{f: vec[f] for f in FEATURE_NAMES}])

    def predict_correct(self, entity_id: str) -> dict:
        """Live prediction from the online store (production-faithful)."""
        vec = self.online.get_online(entity_id)
        row = self._vector_to_row(vec)
        if row is None:
            return {"entity_id": entity_id, "error": "incomplete online features"}
        p = float(self.model.predict_proba(row)[0, 1])
        return {"entity_id": entity_id, "path": "correct", "p_up": round(p, 4), "features": vec}

    def predict_buggy(self, entity_id: str, as_of) -> dict:
        """Prediction from leaked offline features (demonstrates skew)."""
        vec = self.offline.asof_single(entity_id, as_of, variant="leaked")
        row = self._vector_to_row(vec)
        if row is None:
            return {"entity_id": entity_id, "error": "incomplete leaked features"}
        p = float(self.model.predict_proba(row)[0, 1])
        return {"entity_id": entity_id, "path": "buggy", "p_up": round(p, 4), "features": vec}
