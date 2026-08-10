"""Replay historical bars into the online store as if they were arriving live.

The replay walks the calendar forward. On each knowledge date it writes only the
values that became knowable that day — including revisions, which land on their
(later) knowledge date, never on the original event date. This is what a real
streaming feature pipeline does, and it is physically incapable of leaking the
future because it never sees it.

We drive the online store from the *correct* offline feature frame: that frame
already carries the honest knowledge_timestamp for every value, so replaying it
in knowledge-time order is exactly a faithful stream.
"""
from __future__ import annotations

import pandas as pd

from .store import OnlineStore


def replay_into_online(correct_features: pd.DataFrame, online: OnlineStore) -> int:
    """Stream the correct feature frame into the online store in knowledge order.

    Returns the number of feature writes performed.
    """
    df = correct_features.sort_values("knowledge_timestamp").reset_index(drop=True)
    n = 0
    for row in df.itertuples(index=False):
        online.write(
            entity_id=row.entity_id,
            feature_name=row.feature_name,
            value=float(row.value),
            knowledge_ts=row.knowledge_timestamp,
        )
        n += 1
    return n
