"""Unit tests for UI formatting, alert dedup and chart data prep."""

import numpy as np
import pandas as pd

# ── number formatting (ui.table_model) ────────────────────────────────────

def test_format_cell():
    from ui.table_model import _format_cell
    assert _format_cell(1_234_567, "Vol MA") == "1.2M"
    assert _format_cell(2_500_000, "Vol MA") == "2.5M"
    assert _format_cell(12_345.0, "Price") == "12,345.00"
    assert _format_cell(0.55, "Price") == "0.55"
    assert _format_cell(0.335, "Price") == "0.335"   # Bursa 0.005 tick precision
    assert _format_cell(3.5, "Div%") == "3.50%"
    assert _format_cell(0.123, "ROE") == "12.30%"
    assert _format_cell(11, "Score") == "11"
    assert _format_cell(True, "T") == "✓"
    assert _format_cell(False, ">200") == "—"
    assert _format_cell(0.0, "Price") == "—"
    assert _format_cell(float("nan"), "Price") == "—"
    assert _format_cell("crossed", "Signal") == "crossed"


# ── weekly KDJ alert dedup (workers.alert_worker) ────────────────────────

def test_alert_dedup(monkeypatch):
    import workers.alert_worker as aw

    fake = [
        {"ticker": "T1.KL", "name": "Alpha", "kdj_signal": "crossed", "close": 1.20},
        {"ticker": "T2.KL", "name": "Beta", "kdj_signal": "above", "close": 2.00},
        {"ticker": "T3.KL", "name": "Gamma", "kdj_signal": "crossed", "close": 3.10},
    ]
    monkeypatch.setattr(aw, "run_weekly_kdj_screener", lambda *a, **k: iter(fake))

    state = {"notified": {}}
    first = aw.find_new_crosses({}, {}, 500_000, state)
    assert {r["ticker"] for r in first} == {"T1.KL", "T3.KL"}

    second = aw.find_new_crosses({}, {}, 500_000, state)
    assert second == []


def test_alert_reacts_to_signal_change(monkeypatch):
    import workers.alert_worker as aw

    monkeypatch.setattr(aw, "run_weekly_kdj_screener", lambda *a, **k: iter([
        {"ticker": "T1.KL", "kdj_signal": "above"},
        {"ticker": "T1.KL", "kdj_signal": "crossed"},
    ]))
    state = {"notified": {"T1.KL": {"signal": "above", "time": "x"}}}
    new = aw.find_new_crosses({}, {}, 500_000, state)
    assert len(new) == 1 and new[0]["kdj_signal"] == "crossed"


# ── chart data prep (ui.chart_view) ──────────────────────────────────────

def test_prepare_daily_and_weekly():
    from ui.chart_view import _prepare

    n = 120
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.001, 0.02, n))), index=idx)
    data = {
        "close": close,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.01,
        "low": close * 0.99,
        "volume": pd.Series(np.full(n, 1_000_000.0), index=idx),
    }
    daily = _prepare(data, "Daily")
    assert len(daily["close"]) == n
    assert daily["volume"] is not None

    weekly = _prepare(data, "Weekly")
    assert 15 <= len(weekly["close"]) <= 25
    assert weekly["high"].notna().all()
