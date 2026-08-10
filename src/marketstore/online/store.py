"""Online store: low-latency serving of the current feature vector.

Backed by Redis (via `fakeredis` here so it runs without a server; point the same
client at a real Redis in production — the interface is identical).

Two structures per (entity, feature):

  latest hash    key = feat:{entity}         field = {feature}   -> current value
      O(1) read of the live vector. This is the production inference path.

  versioned log  key = featlog:{entity}:{feature}  (Redis ZSET)
      member = "{value}"  score = knowledge_ts (epoch seconds)
      An append-only history. It lets us reconstruct exactly what the online
      store *would have served* at any past instant, which is how we prove
      online/offline consistency instead of asserting it.

An online store is, by construction, causal: at wall-clock time T it can only
hold values whose knowledge_timestamp <= T. That is why a streaming replay can
never reproduce the leaked offline features — a property we test, not assume.
"""
from __future__ import annotations

import fakeredis
import pandas as pd


def _epoch(ts) -> float:
    return pd.Timestamp(ts).timestamp()


class OnlineStore:
    def __init__(self, client=None):
        # decode_responses so we get str back, not bytes
        self.r = client or fakeredis.FakeStrictRedis(decode_responses=True)

    # --- writes ---------------------------------------------------------------
    def write(self, entity_id: str, feature_name: str, value: float, knowledge_ts) -> None:
        score = _epoch(knowledge_ts)
        # update live vector
        self.r.hset(f"feat:{entity_id}", feature_name, value)
        # append to the versioned log (score encodes when it became knowable)
        self.r.zadd(f"featlog:{entity_id}:{feature_name}", {f"{value}|{score}": score})

    def write_vector(self, entity_id: str, values: dict, knowledge_ts) -> None:
        for name, v in values.items():
            if pd.notna(v):
                self.write(entity_id, name, float(v), knowledge_ts)

    # --- reads ----------------------------------------------------------------
    def get_online(self, entity_id: str) -> dict:
        """Current live feature vector (the production inference read)."""
        raw = self.r.hgetall(f"feat:{entity_id}")
        return {k: float(v) for k, v in raw.items()}

    def reconstruct_asof(self, entity_id: str, feature_names, request_time) -> dict:
        """What the online store WOULD have served at request_time.

        For each feature, the most recent logged value with score <= request_time.
        Used only for the consistency proof, never on the hot path.
        """
        cutoff = _epoch(request_time)
        out = {}
        for name in feature_names:
            members = self.r.zrangebyscore(
                f"featlog:{entity_id}:{name}", min="-inf", max=cutoff,
                start=0, num=-1, withscores=False,
            )
            if members:
                # last member is the most-recent knowable value
                val = float(members[-1].split("|")[0])
                out[name] = val
        return out
