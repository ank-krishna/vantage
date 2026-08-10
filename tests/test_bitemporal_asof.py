"""Exercise the knowledge_timestamp > event_timestamp case directly.

A value about day D can be revised, with the revision only knowable at D+lag.
The store must return the first print for queries in [D, D+lag) and the revised
value for queries at/after D+lag. This is the bitemporal behavior that a
real-time-vintage (ALFRED-style) feature store must get right.
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from marketstore.offline.store import OfflineStore   # noqa: E402
from marketstore.online.store import OnlineStore      # noqa: E402
from marketstore.schema import FEATURE_COLUMNS         # noqa: E402


def test_revision_changes_answer_across_knowledge_time():
    # Feature about event day Jan 10: first print 5.0 (knowable Jan 10),
    # revised to 5.5 but only knowable Jan 13.
    rows = [
        ("X", "f", 5.0, datetime(2020, 1, 10), datetime(2020, 1, 10)),
        ("X", "f", 5.5, datetime(2020, 1, 10), datetime(2020, 1, 13)),
    ]
    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    s = OfflineStore()
    s.write(df, "correct")

    # In [Jan10, Jan13): only the first print is knowable.
    assert s.asof_single("X", datetime(2020, 1, 11), "correct")["f"] == 5.0
    # At/after Jan13: the revision is knowable and wins (later knowledge ts).
    assert s.asof_single("X", datetime(2020, 1, 13), "correct")["f"] == 5.5


def test_online_reconstruction_tracks_revision():
    online = OnlineStore()
    online.write("X", "f", 5.0, datetime(2020, 1, 10))
    online.write("X", "f", 5.5, datetime(2020, 1, 13))
    # Reconstruct what production would have served at each instant.
    assert online.reconstruct_asof("X", ["f"], datetime(2020, 1, 11))["f"] == 5.0
    assert online.reconstruct_asof("X", ["f"], datetime(2020, 1, 14))["f"] == 5.5
