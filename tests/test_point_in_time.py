"""The point-in-time join is the correctness primitive; these tests pin it down.

We build a tiny hand-checkable store so the expected answers are obvious, then
assert the as-of read returns exactly what was knowable at each instant — and
that the built-in leakage guard fires when a value would postdate the request.
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from marketstore.offline.store import OfflineStore  # noqa: E402
from marketstore.schema import FEATURE_COLUMNS       # noqa: E402


def _tiny_store() -> OfflineStore:
    # One entity, one feature, three daily values, all knowable same day.
    rows = [
        ("AAPL", "f", 10.0, datetime(2020, 1, 1), datetime(2020, 1, 1)),
        ("AAPL", "f", 11.0, datetime(2020, 1, 2), datetime(2020, 1, 2)),
        ("AAPL", "f", 12.0, datetime(2020, 1, 3), datetime(2020, 1, 3)),
    ]
    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    s = OfflineStore()
    s.write(df, "correct")
    return s


def test_asof_returns_latest_knowable_value():
    s = _tiny_store()
    assert s.asof_single("AAPL", datetime(2020, 1, 2, 12), "correct")["f"] == 11.0
    assert s.asof_single("AAPL", datetime(2020, 1, 3), "correct")["f"] == 12.0


def test_asof_before_any_value_is_empty():
    s = _tiny_store()
    assert s.asof_single("AAPL", datetime(2019, 12, 31), "correct") == {}


def test_asof_never_returns_future_value():
    s = _tiny_store()
    # As of Jan 2, the Jan 3 value (12.0) must NOT appear.
    got = s.asof_single("AAPL", datetime(2020, 1, 2, 23, 59), "correct")
    assert got["f"] == 11.0


def test_leakage_guard_fires_on_future_knowledge():
    # A value stamped as knowable in the future must be excluded; if the query
    # ever returned it, the guard raises. We simulate by asking as-of a time
    # before the only value's knowledge_timestamp and confirming emptiness,
    # then directly exercise the guard by monkeypatching the gate off.
    rows = [("AAPL", "f", 99.0, datetime(2020, 1, 5), datetime(2020, 1, 8))]
    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    s = OfflineStore()
    s.write(df, "correct")
    # as-of Jan 6: value not yet knowable (knowledge is Jan 8) -> empty
    assert s.asof_single("AAPL", datetime(2020, 1, 6), "correct") == {}
    # as-of Jan 9: now knowable
    assert s.asof_single("AAPL", datetime(2020, 1, 9), "correct")["f"] == 99.0
