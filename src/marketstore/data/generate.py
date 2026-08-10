"""Synthetic market data with a *real* (weak) predictable component.

Why synthetic: this sandbox can't reach market-data APIs. That's fine, and
arguably better for the demo — because we control the data-generating process,
we know the true signal-to-noise, so when a leaked pipeline reports performance
*above* that ceiling we know for certain it's leakage and not luck.

Two properties are engineered in deliberately:

1. A small genuine edge. Next-day direction has a weak dependence on *as-of*
   momentum (an AR(1)-ish term). A correct model should beat 50% by a little.
   This is the "honest, lower, but real" performance the correct path recovers.

2. Late revisions. A fraction of daily bars are revised a few days after the
   fact (corporate actions, late prints, vendor corrections). The first print is
   available on day D; the revised value only becomes knowable on D+lag. This is
   what makes knowledge_timestamp != event_timestamp, and it is the seam a
   naive pipeline leaks through.

To swap in real data locally, implement a puller that writes the same raw schema
(one parquet per ticker with columns: date, open, high, low, close, volume,
first_print_close, revised, knowledge_date) and the rest of the pipeline is
unchanged.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RAW_COLUMNS = [
    "date", "open", "high", "low", "close", "volume",
    "first_print_close", "revised", "knowledge_date",
]


def _business_days(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def generate_ticker(
    ticker: str,
    n_days: int,
    start: str,
    rng: np.random.Generator,
    signal_strength: float = 0.28,
    revision_frac: float = 0.06,
    revision_lag: int = 3,
) -> pd.DataFrame:
    """One ticker of daily bars with a weak real signal and late revisions."""
    dates = _business_days(start, n_days)

    # --- returns with a small, LEARNABLE momentum edge (the *real* signal) -----
    # Tomorrow's return leans weakly on trailing 10-day momentum. This is a real,
    # causal relationship a correct model can recover from past-only features,
    # which is exactly why the correct path should beat 50% by a little.
    innov = rng.normal(0, 0.012, n_days)
    ret = np.zeros(n_days)
    win = 10
    for t in range(1, n_days):
        trail = ret[max(0, t - win):t]
        mom = trail.mean() if len(trail) else 0.0
        ret[t] = signal_strength * np.tanh(120 * mom) * 0.012 + innov[t]

    close = 100 * np.exp(np.cumsum(ret))

    # volume: slow regime trend + noise (so global vs as-of z-scores differ)
    base_vol = 1_000_000 * (1 + 0.4 * np.sin(np.linspace(0, 6, n_days)))
    volume = np.maximum(base_vol * (1 + rng.normal(0, 0.25, n_days)), 1000).astype(int)

    intraday = np.abs(rng.normal(0, 0.008, n_days))
    high = close * (1 + intraday)
    low = close * (1 - intraday)
    open_ = np.concatenate([[close[0]], close[:-1]]) * (1 + rng.normal(0, 0.003, n_days))

    df = pd.DataFrame({
        "date": dates,
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume,
    })

    # --- late revisions: first print differs from final, knowable later --------
    df["first_print_close"] = df["close"]
    df["revised"] = False
    df["knowledge_date"] = df["date"]  # by default, knowable same day

    n_rev = int(revision_frac * n_days)
    rev_idx = rng.choice(np.arange(1, n_days - revision_lag), size=n_rev, replace=False)
    for i in rev_idx:
        # first print is a noisy version; the *true* close is only known at i+lag
        noise = rng.normal(0, 0.004)
        df.loc[i, "first_print_close"] = df.loc[i, "close"] * (1 + noise)
        df.loc[i, "revised"] = True
        df.loc[i, "knowledge_date"] = dates[i + revision_lag]

    df.insert(0, "ticker", ticker)
    return df[["ticker"] + RAW_COLUMNS]


def generate_universe(
    tickers: list[str],
    n_days: int = 1400,
    start: str = "2016-01-04",
    seed: int = 7,
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    out = {}
    for i, tk in enumerate(tickers):
        out[tk] = generate_ticker(tk, n_days, start, np.random.default_rng(seed + i))
    return out


def write_raw(universe: dict[str, pd.DataFrame], raw_dir: str | Path) -> None:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for tk, df in universe.items():
        df.to_parquet(raw_dir / f"{tk}.parquet", index=False)


if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "JPM"]
    uni = generate_universe(tickers)
    write_raw(uni, Path(__file__).resolve().parents[3] / "data_raw")
    sample = uni["AAPL"]
    print(f"generated {len(tickers)} tickers x {len(sample)} bars each")
    print(f"revised bars in AAPL: {int(sample['revised'].sum())}")
    print(sample.head(3).to_string(index=False))
