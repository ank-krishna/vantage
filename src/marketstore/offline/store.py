"""Offline store: durable, queryable history of feature values.

Backed by DuckDB (SQL-native, no server). Holds one table per feature variant
so the demo can compare a correct build against a leaked build side by side.

The important method is `get_features_asof` — the point-in-time join. For each
(entity_id, request_time) it returns the most recent feature value that was
*knowable* at request_time:

    latest value WHERE knowledge_timestamp <= request_time  (per entity, feature)

A guard asserts no returned row has knowledge_timestamp > request_time. If that
ever fires, the store leaked, full stop.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from ..schema import FEATURE_COLUMNS, as_datetime


class OfflineStore:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.con = duckdb.connect(str(db_path))

    def write(self, features: pd.DataFrame, variant: str) -> None:
        """Persist a feature frame under a named variant ('correct' | 'leaked')."""
        table = f"features_{variant}"
        df = features[FEATURE_COLUMNS].copy()  # noqa: F841 (used by DuckDB scan)
        self.con.execute(f"DROP TABLE IF EXISTS {table}")
        self.con.execute(f"CREATE TABLE {table} AS SELECT * FROM df")
        self.con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{variant} ON {table}(entity_id, feature_name)"
        )

    def get_features_asof(
        self, requests: pd.DataFrame, variant: str = "correct"
    ) -> pd.DataFrame:
        """Point-in-time join.

        requests: columns [entity_id, request_time]
        returns : one row per (entity_id, request_time) with feature columns,
                  each holding the latest value knowable at request_time.
        """
        table = f"features_{variant}"
        req = requests.copy()
        req["request_time"] = pd.to_datetime(req["request_time"])

        # For each request row and feature, pick the row with the greatest
        # event_timestamp among those knowable by request_time; break ties by
        # the most recently *known* value (largest knowledge_timestamp).
        sql = f"""
        WITH ranked AS (
            SELECT
                r.entity_id,
                r.request_time,
                f.feature_name,
                f.value,
                f.event_timestamp,
                f.knowledge_timestamp,
                ROW_NUMBER() OVER (
                    PARTITION BY r.entity_id, r.request_time, f.feature_name
                    ORDER BY f.event_timestamp DESC, f.knowledge_timestamp DESC
                ) AS rn
            FROM req r
            JOIN {table} f
              ON f.entity_id = r.entity_id
             AND f.knowledge_timestamp <= r.request_time   -- the point-in-time gate
        )
        SELECT entity_id, request_time, feature_name, value,
               event_timestamp, knowledge_timestamp
        FROM ranked
        WHERE rn = 1
        """
        long = self.con.execute(sql).fetch_df()

        # --- leakage guard: nothing returned may postdate the request ----------
        if not long.empty:
            leaked = long["knowledge_timestamp"] > long["request_time"]
            if leaked.any():
                raise AssertionError(
                    f"point-in-time violation: {int(leaked.sum())} rows have "
                    f"knowledge_timestamp > request_time in variant '{variant}'"
                )

        wide = long.pivot_table(
            index=["entity_id", "request_time"],
            columns="feature_name", values="value", aggfunc="first",
        ).reset_index()
        wide.columns.name = None
        return wide

    def asof_single(self, entity_id: str, request_time, variant: str = "correct") -> dict:
        """Convenience: feature vector for one entity as of one time."""
        req = pd.DataFrame({"entity_id": [entity_id], "request_time": [as_datetime(request_time)]})
        out = self.get_features_asof(req, variant)
        if out.empty:
            return {}
        row = out.iloc[0].drop(labels=["entity_id", "request_time"])
        return row.to_dict()

    def close(self) -> None:
        self.con.close()
