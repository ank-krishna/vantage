"""Two guarantees, tested end to end:

1. Schema invariant: a value cannot be knowable before it is true.
2. The correct offline feature read reproduces the online store EXACTLY at many
   random points — the property that makes training/serving consistent — while
   the leaked build measurably does not.
"""
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from marketstore.schema import FeatureRow, _coerce, FEATURE_COLUMNS  # noqa: E402
from marketstore.pipeline import build_all                            # noqa: E402
from marketstore.consistency.pit import reconcile, summarize          # noqa: E402


def test_knowledge_before_event_rejected():
    with pytest.raises(ValueError):
        FeatureRow("A", "f", 1.0, datetime(2020, 1, 5), datetime(2020, 1, 1))


def test_coerce_rejects_bad_frame():
    bad = pd.DataFrame(
        [("A", "f", 1.0, datetime(2020, 1, 5), datetime(2020, 1, 1))],
        columns=FEATURE_COLUMNS,
    )
    with pytest.raises(ValueError):
        _coerce(bad)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    raw_dir = tmp_path_factory.mktemp("raw")
    return build_all(raw_dir=str(raw_dir))


def _check_points(raw, n=200, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for tk, df in raw.items():
        dates = pd.to_datetime(df["date"]).sort_values().to_numpy()
        pool = dates[len(dates) // 2:]
        for t in rng.choice(pool, size=n // len(raw), replace=False):
            rows.append({"entity_id": tk, "request_time": pd.Timestamp(t)})
    return pd.DataFrame(rows)


def test_correct_matches_online_exactly(built):
    raw, offline, online = built
    report = reconcile(offline, online, _check_points(raw))
    s = summarize(report)
    assert s["correct_matches_online_frac"] == 1.0


def test_leaked_build_is_detectably_skewed(built):
    raw, offline, online = built
    report = reconcile(offline, online, _check_points(raw))
    s = summarize(report)
    # the whole point: the naive offline build does NOT match production
    assert s["leaked_matches_online_frac"] < 0.5
    assert s["mean_abs_leaked_skew"] > 0
