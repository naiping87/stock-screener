"""Tests for tools.signal_journal — P2 signal journal + forward returns."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tools.signal_journal import SignalJournal


def _series(vals, start="2024-01-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="D"))


def _make_data():
    # T1 rises steadily, T2 falls — so forward returns differ by bucket.
    t1 = np.linspace(10.0, 20.0, 40)
    t2 = np.linspace(20.0, 10.0, 40)
    return {
        "T1.KL": {"close": _series(t1)},
        "T2.KL": {"close": _series(t2)},
    }


def _signal(tkr, classification):
    return {
        "ticker": tkr, "name": tkr, "sector": "Test",
        "classification": classification,
        "master_rr": 80.0, "master_score": 75.0,
        "strength_score": 70.0, "setup_score": 60.0,
        "trigger_score": 50.0, "breakout_score": 40.0,
        "rs_rank": 85.0, "rs_rank_chg20": 10.0, "clv": 0.9, "rr": 2.5,
        "score": 8, "kdj_state": "BULLISH", "kdj_k_d_golden": True,
        "market_regime": "RISK_ON",
    }


def test_record_backfill_report(tmp_path):
    j = SignalJournal(str(tmp_path / "journal.csv"))
    rows = [_signal("T1.KL", "SETUP"), _signal("T2.KL", "BREAKOUT")]
    n = j.record(rows, market="my", asof=pd.Timestamp("2024-01-05"))
    assert n == 2
    assert len(j.df) == 2

    # dedup: recording the same date/ticker again adds nothing
    assert j.record(rows, market="my", asof=pd.Timestamp("2024-01-05")) == 0

    j.backfill(_make_data())
    # T1 (rising) has positive 5d forward return, T2 (falling) negative
    d = j.df.set_index("ticker")
    assert d.loc["T1.KL", "ret_5d"] > 0
    assert d.loc["T2.KL", "ret_5d"] < 0
    assert d.loc["T1.KL", "mfe_5d"] is not None
    assert d.loc["T1.KL", "mae_5d"] is not None

    rep = j.report("classification")
    assert set(rep["classification"]) == {"SETUP", "BREAKOUT"}
    assert rep["n"].sum() == 2


def test_report_bands(tmp_path):
    j = SignalJournal(str(tmp_path / "journal.csv"))
    rows = [_signal("T1.KL", "SETUP"), _signal("T2.KL", "BREAKOUT")]
    j.record(rows, market="my", asof=pd.Timestamp("2024-01-05"))
    j.backfill(_make_data())
    bands = j.report_bands()
    assert not bands.empty
    assert "win_rate_5d" in bands.columns


def _run():
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)
        test_record_backfill_report(p)
        test_report_bands(p)
    print("All signal journal tests passed")


if __name__ == "__main__":
    _run()
