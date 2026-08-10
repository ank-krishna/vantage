"""The yfinance puller can't hit the real API in CI/sandbox, so we mock the
Yahoo response and test the part that matters: does a real, retroactive
Adj Close change get captured as a genuine revision with the correct
bitemporal shape (original row preserved, new row added with today's
knowledge date)?
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _fake_history(dates, adj_close):
    df = pd.DataFrame({
        "Open": 100.0, "High": 101.0, "Low": 99.0,
        "Close": 100.0, "Adj Close": adj_close, "Volume": 1_000_000,
    }, index=dates)
    df.index.name = "Date"
    return df


def test_retroactive_revision_is_captured_bitemporally(tmp_path):
    from marketstore.data import yfinance_puller as yp

    dates = pd.bdate_range("2024-01-01", periods=10)
    baseline = np.linspace(100, 109, 10)

    with patch("yfinance.Ticker") as MockTicker:
        inst = MagicMock()
        MockTicker.return_value = inst

        inst.history.side_effect = lambda **kw: _fake_history(dates, baseline)
        out1 = yp.snapshot_pull(["FAKE"], start="2024-01-01", raw_dir=str(tmp_path))
        assert len(out1["FAKE"]) == 10
        assert not out1["FAKE"]["revised"].any()

        revised = baseline.copy()
        revised[2] = 999.0  # simulate a retroactive Adj Close rewrite
        inst.history.side_effect = lambda **kw: _fake_history(dates, revised)
        out2 = yp.build_vintage_history(["FAKE"], start="2024-01-01", raw_dir=str(tmp_path))
        df2 = out2["FAKE"]

        # original first print for that date must still be present, untouched
        rows_for_date = df2[df2.date == dates[2]].sort_values("knowledge_date")
        assert len(rows_for_date) == 2
        assert rows_for_date.iloc[0]["close"] == 102.0        # first print
        assert rows_for_date.iloc[0]["revised"] == False
        assert rows_for_date.iloc[1]["close"] == 999.0        # the revision
        assert rows_for_date.iloc[1]["revised"] == True
        # the revision must be knowable strictly after the original event date
        assert rows_for_date.iloc[1]["knowledge_date"] > rows_for_date.iloc[0]["date"]

        # every other date must be unaffected
        untouched = df2[df2.date != dates[2]]
        assert not untouched["revised"].any()
