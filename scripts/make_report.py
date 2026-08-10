"""Run the whole system and emit artifacts the README cites:
  results/metrics.json  — consistency + backtest numbers
  results/comparison.png — correct vs leaked bar chart

Run:  PYTHONPATH=src python3 scripts/make_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marketstore.pipeline import build_all              # noqa: E402
from marketstore.consistency.pit import reconcile, summarize  # noqa: E402
from marketstore.backtest.run import run_backtest        # noqa: E402


def check_points(raw, n=400, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for tk, df in raw.items():
        dates = pd.to_datetime(df["date"]).sort_values().to_numpy()
        pool = dates[len(dates) // 2:]
        for t in rng.choice(pool, size=n // len(raw), replace=False):
            rows.append({"entity_id": tk, "request_time": pd.Timestamp(t)})
    return pd.DataFrame(rows)


def main():
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    raw, offline, online = build_all(raw_dir=str(ROOT / "data_raw"))

    consistency = summarize(reconcile(offline, online, check_points(raw)))
    bt = run_backtest(offline, raw)
    c = bt[bt.variant == "correct"].iloc[0]
    l = bt[bt.variant == "leaked"].iloc[0]

    metrics = {
        "consistency": consistency,
        "backtest": bt.to_dict(orient="records"),
        "phantom_edge": {
            "accuracy": round(float(l.accuracy - c.accuracy), 4),
            "roc_auc": round(float(l.roc_auc - c.roc_auc), 4),
            "sharpe_correct": float(c.strategy_sharpe),
            "sharpe_leaked": float(l.strategy_sharpe),
        },
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # --- chart ---------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    labels = ["accuracy", "roc_auc"]
    correct_vals = [c.accuracy, c.roc_auc]
    leaked_vals = [l.accuracy, l.roc_auc]
    x = np.arange(len(labels))
    w = 0.35
    axes[0].bar(x - w / 2, correct_vals, w, label="correct (point-in-time)", color="#2b7a4b")
    axes[0].bar(x + w / 2, leaked_vals, w, label="leaked (online/offline skew)", color="#c0392b")
    axes[0].axhline(0.5, ls="--", c="gray", lw=1)
    axes[0].set_xticks(x); axes[0].set_xticklabels(labels)
    axes[0].set_ylim(0.45, max(leaked_vals) + 0.08)
    axes[0].set_title("Backtest metrics: real edge vs illusion")
    axes[0].legend(fontsize=8)
    for i, (cv, lv) in enumerate(zip(correct_vals, leaked_vals)):
        axes[0].text(i - w / 2, cv + 0.005, f"{cv:.3f}", ha="center", fontsize=8)
        axes[0].text(i + w / 2, lv + 0.005, f"{lv:.3f}", ha="center", fontsize=8)

    axes[1].bar(["correct", "leaked"], [c.strategy_sharpe, l.strategy_sharpe],
                color=["#2b7a4b", "#c0392b"])
    axes[1].set_title("Strategy Sharpe (annualized)")
    axes[1].axhline(0, c="gray", lw=1)
    for i, v in enumerate([c.strategy_sharpe, l.strategy_sharpe]):
        axes[1].text(i, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)

    fig.suptitle("Same model, same window, same rows — only the feature pipeline differs",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "comparison.png", dpi=130, bbox_inches="tight")
    print(json.dumps(metrics, indent=2))
    print(f"\nwrote {out/'metrics.json'} and {out/'comparison.png'}")


if __name__ == "__main__":
    main()
