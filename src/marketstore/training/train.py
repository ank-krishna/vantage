"""Build a labeled training matrix through the point-in-time join, then fit a
deliberately simple model. The model is not the point; the join is.

Label: next-day direction. For event day D, y = 1 if the (final) close on the
next trading day exceeds day D's close. Using D+1 for the *label* is legitimate —
labels are known after the fact at training time. The discipline is that the
*features* for day D must be knowable at D, which the as-of join enforces.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..offline.store import OfflineStore
from ..schema import FEATURE_NAMES


def build_labels(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Next-day up/down label per (entity, event day)."""
    frames = []
    for tk, df in raw.items():
        d = df.sort_values("date").reset_index(drop=True)
        nxt = d["close"].shift(-1)
        lab = pd.DataFrame({
            "entity_id": tk,
            "request_time": pd.to_datetime(d["date"]),
            "label": (nxt > d["close"]).astype(int),
        })
        frames.append(lab.iloc[:-1])  # drop last day (no next-day label)
    return pd.concat(frames, ignore_index=True)


def build_matrix(offline: OfflineStore, labels: pd.DataFrame, variant: str) -> pd.DataFrame:
    """Point-in-time feature matrix joined to labels, for one feature variant."""
    feats = offline.get_features_asof(
        labels[["entity_id", "request_time"]], variant=variant
    )
    m = labels.merge(feats, on=["entity_id", "request_time"], how="inner")
    m = m.dropna(subset=FEATURE_NAMES)
    return m.sort_values("request_time").reset_index(drop=True)


def time_split(matrix: pd.DataFrame, train_frac: float = 0.7):
    """Strict time-ordered split: train on the earliest rows, test on the latest."""
    cut = matrix["request_time"].quantile(train_frac)
    train = matrix[matrix["request_time"] <= cut]
    test = matrix[matrix["request_time"] > cut]
    return train, test, cut


def fit(train: pd.DataFrame) -> LogisticRegression:
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(train[FEATURE_NAMES], train["label"])
    return model
