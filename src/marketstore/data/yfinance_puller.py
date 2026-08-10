"""Real market data puller, using yfinance, that writes the exact raw schema
the rest of the pipeline already expects (see data/generate.py's RAW_COLUMNS).

This cannot run inside the sandbox that built this repo — its network is locked
to package registries, and query1.finance.yahoo.com is blocked
(x-deny-reason: host_not_allowed). It's written to run on your own machine.

Where do REAL revisions come from here?
    Daily bars aren't revised the way GDP prints are, with one big exception:
    `Adj Close`. When a company pays a dividend or splits, Yahoo retroactively
    rewrites the adjusted close for every past date. Pull the same historical
    date on two different days and you can get two different adjusted-close
    values for it. That is a genuine, naturally-occurring revision — the same
    ALFRED-style phenomenon the synthetic generator fakes, happening for real.

    To capture it you have to pull more than once over time and DIFF the
    snapshots — a single one-shot pull can't see it, because a revision only
    exists relative to an earlier pull. So this module supports two modes:

    snapshot_pull()
        A single pull, tagged with today's date as the knowledge_timestamp for
        every row (first_print, not-yet-revised — correct, just not yet
        vintage-aware). Good enough to swap in for the synthetic data on day 1.

    build_vintage_history(raw_dir)
        Run this on a schedule (daily/weekly cron). It re-pulls the full
        history each time, compares this pull's Adj Close for every date
        against the LAST pull's, and any date whose value changed gets a new
        row stamped with today as its knowledge_timestamp — a real revision,
        collected the same way ALFRED collects real-time data vintages. Run it
        for a few weeks and you'll have genuine (if sparse) revision data
        instead of the synthetic generator's simulated version.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .generate import RAW_COLUMNS

try:
    import yfinance as yf
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "yfinance is required for real data: pip install yfinance"
    ) from e


def _fetch_one(ticker: str, start: str, end: str | None) -> pd.DataFrame:
    """Pull raw OHLCV + adjusted close for one ticker via yfinance."""
    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
    if df.empty:
        raise ValueError(f"yfinance returned no data for {ticker}")
    df = df.reset_index()
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    # yfinance gives: date, open, high, low, close, adj_close, volume, ...
    out = df[["date", "open", "high", "low", "close", "adj_close", "volume"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out.insert(0, "ticker", ticker)
    return out


def snapshot_pull(
    tickers: list[str],
    start: str = "2016-01-01",
    end: str | None = None,
    raw_dir: str | Path = "data_raw",
) -> dict[str, pd.DataFrame]:
    """One-shot pull. Every row's knowledge_timestamp == its event date
    (no revision history yet — this establishes the baseline vintage)."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp(datetime.now(timezone.utc).date())

    out = {}
    for tk in tickers:
        bars = _fetch_one(tk, start, end)
        frame = pd.DataFrame({
            "ticker": tk,
            "date": bars["date"],
            "open": bars["open"], "high": bars["high"], "low": bars["low"],
            "close": bars["adj_close"],        # use adjusted close as "truth"
            "volume": bars["volume"],
            "first_print_close": bars["adj_close"],
            "revised": False,
            "knowledge_date": bars["date"],     # first pull: same-day knowledge
        })
        frame.to_parquet(raw_dir / f"{tk}.parquet", index=False)
        # keep an explicit vintage copy so later pulls can diff against it
        vdir = raw_dir / "_vintages" / tk
        vdir.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(vdir / f"{today.date()}.parquet", index=False)
        out[tk] = frame
    return out


def build_vintage_history(
    tickers: list[str],
    start: str = "2016-01-01",
    raw_dir: str | Path = "data_raw",
) -> dict[str, pd.DataFrame]:
    """Re-pull and diff against the most recent stored vintage.

    Any date whose adjusted close changed since the last pull gets appended as
    a NEW row with today as its knowledge_timestamp — a genuine revision.
    Unchanged dates are left as they were (their original knowledge_timestamp
    still stands: nothing new became knowable about them today).

    Run this on a recurring schedule; it accumulates real vintage data over
    time the same way ALFRED does for macro series.
    """
    raw_dir = Path(raw_dir)
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    out = {}

    for tk in tickers:
        vdir = raw_dir / "_vintages" / tk
        prior_files = sorted(vdir.glob("*.parquet")) if vdir.exists() else []

        new_bars = _fetch_one(tk, start, None)
        new_bars = new_bars.rename(columns={"adj_close": "close_today"})

        if not prior_files:
            # no history yet: fall back to a plain snapshot
            out.update(snapshot_pull([tk], start, None, raw_dir))
            continue

        last = pd.read_parquet(prior_files[-1])
        merged = last.merge(
            new_bars[["date", "close_today"]], on="date", how="outer"
        )

        changed = (merged["close_today"] - merged["close"]).abs() > 1e-9
        changed = changed.fillna(False)

        revised_rows = merged.loc[changed].copy()
        if not revised_rows.empty:
            revised_rows["close"] = revised_rows["close_today"]
            revised_rows["first_print_close"] = revised_rows["close_today"]
            revised_rows["revised"] = True
            revised_rows["knowledge_date"] = today
            revised_rows["ticker"] = tk
            merged.loc[changed, ["close", "revised", "knowledge_date"]] = \
                revised_rows[["close", "revised", "knowledge_date"]].values

        merged = merged.drop(columns="close_today")
        combined = pd.concat([last, merged.loc[changed]], ignore_index=True)
        combined = combined[["ticker"] + RAW_COLUMNS].sort_values(["date", "knowledge_date"])

        vdir.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(vdir / f"{today.date()}.parquet", index=False)
        combined.to_parquet(raw_dir / f"{tk}.parquet", index=False)
        out[tk] = combined

        if not revised_rows.empty:
            print(f"{tk}: {len(revised_rows)} bars revised since last pull")

    return out


if __name__ == "__main__":
    TICKERS = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "JPM"]
    print("pulling real data via yfinance (requires network access to Yahoo)...")
    snapshot_pull(TICKERS)
    print("done. Re-run this module on a later day (or call build_vintage_history)")
    print("to start accumulating real revision history.")
