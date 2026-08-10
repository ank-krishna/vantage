"""End-to-end demo. Run:  PYTHONPATH=src python3 scripts/demo.py

Builds the raw layer, both offline feature variants, and the streaming online
store; proves online/offline consistency; then runs the buggy-vs-correct
backtest and prints the divergence that is the whole point of the project.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marketstore.pipeline import build_all           # noqa: E402
from marketstore.consistency.pit import reconcile, summarize  # noqa: E402
from marketstore.backtest.run import run_backtest     # noqa: E402
from marketstore.schema import FEATURE_NAMES          # noqa: E402


def random_check_points(raw: dict, n: int = 400, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for tk, df in raw.items():
        dates = pd.to_datetime(df["date"]).sort_values().to_numpy()
        # sample from the back half so features have warmed up
        pool = dates[len(dates) // 2:]
        picks = rng.choice(pool, size=min(n // len(raw), len(pool)), replace=False)
        for t in picks:
            rows.append({"entity_id": tk, "request_time": pd.Timestamp(t)})
    return pd.DataFrame(rows)


def main() -> None:
    print("building raw -> offline (correct+leaked) -> online (streamed)...")
    raw, offline, online = build_all(raw_dir=str(ROOT / "data_raw"))

    print("\n=== 1. ONLINE/OFFLINE CONSISTENCY ===")
    cps = random_check_points(raw)
    report = reconcile(offline, online, cps)
    s = summarize(report)
    for k, v in s.items():
        print(f"  {k}: {v}")
    assert s["correct_matches_online_frac"] == 1.0, "correct path must match online exactly"
    print("  -> correct offline features reproduce the online store EXACTLY.")
    print(f"  -> leaked offline features disagree with production on "
          f"{100*(1-s['leaked_matches_online_frac']):.1f}% of reads.")

    print("\n=== 2. BUGGY vs CORRECT BACKTEST (same model, same window) ===")
    results = run_backtest(offline, raw)
    print(results.to_string(index=False))

    c = results[results.variant == "correct"].iloc[0]
    l = results[results.variant == "leaked"].iloc[0]
    print("\n=== 3. THE ILLUSION ===")
    print(f"  accuracy:        correct {c.accuracy:.3f}  vs leaked {l.accuracy:.3f} "
          f"(+{l.accuracy - c.accuracy:.3f} phantom)")
    print(f"  roc_auc:         correct {c.roc_auc:.3f}  vs leaked {l.roc_auc:.3f} "
          f"(+{l.roc_auc - c.roc_auc:.3f} phantom)")
    print(f"  strategy_sharpe: correct {c.strategy_sharpe:+.2f}  vs leaked "
          f"{l.strategy_sharpe:+.2f}")
    print("\n  The leaked path's edge is unrealizable: production only ever has")
    print("  the correct features. A team shipping the leaked pipeline would")
    print("  have deployed a model whose backtested edge silently evaporates.")


if __name__ == "__main__":
    main()
