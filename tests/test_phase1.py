"""Unit tests for the Phase-1 engine: classify + the pure structure detectors.

These lock the classification rules (so a silent data-gap change can't turn a
rank into a LEADER) and the CLV / meaningful-range / effort semantics. They are
deterministic, offline, and guard the most decision-relevant parts of the
screener without needing the network-dependent e2e/smoke/golden tools.
"""

from __future__ import annotations

import pandas as pd

from screener_phase1 import classify
from screener_setup import (
    closing_strength,
    effort_vs_result,
    meaningful_range,
    price_extension,
    risk_reward,
)


def _s(values: list) -> pd.Series:
    """Naive-index pandas Series (detectors use position, not tz)."""
    return pd.Series([float(v) for v in values])


def _ohlcv(close: list, high: list, low: list, volume: list | None = None) -> dict:
    d = {"close": _s(close), "high": _s(high), "low": _s(low)}
    if volume is not None:
        d["volume"] = _s(volume)
    return d


# ── classify(): the 12-label priority map ────────────────────────────────────

def test_classify_breakout_over_all():
    assert classify(10, 10, 10, {"attempt": True, "score": 80}, None, None, {"valid": True}, None) == "BREAKOUT"
    assert classify(10, 10, 10, {"attempt": True, "score": 65}, None, None, {"valid": True}, None) == "EXPANSION"


def test_classify_ema_reclaim_above_trigger():
    # EMA reclaim sits just under a real breakout, above a plain trigger-watch.
    assert classify(50, 40, 30, {"attempt": False, "score": 0}, None, 100, {"valid": True}, None,
                    ema_reclaim={"detected": True}) == "EMA RECLAIM"


def test_classify_trigger_watch_and_rr_gate():
    # Valid trigger setup near pivot with acceptable R:R -> TRIGGER WATCH.
    assert classify(50, 60, 80, {"attempt": False, "score": 0}, None, 3.0, {"valid": True}, None,
                    rr=1.5) == "TRIGGER WATCH"
    # Same setup but unacceptable R:R -> downgraded to SETUP (not a good trade).
    assert classify(50, 60, 80, {"attempt": False, "score": 0}, None, 3.0, {"valid": True}, None,
                    rr=0.5) == "SETUP"


def test_classify_leader_axis_from_rank_only():
    # rs_rank / rs_rank_chg20 ALONE decide the leadership labels.
    assert classify(20, 10, 10, {"attempt": False, "score": 0}, None, None, {"valid": True}, None,
                    rs_rank=90, rs_rank_chg20=2) == "LEADER"
    assert classify(20, 10, 10, {"attempt": False, "score": 0}, None, None, {"valid": True}, None,
                    rs_rank=70, rs_rank_chg20=12) == "EMERGING LEADER"
    assert classify(20, 10, 10, {"attempt": False, "score": 0}, None, None, {"valid": True}, None,
                    rs_rank=90, rs_rank_chg20=-12) == "WEAKENING"


def test_classify_none_chg20_not_leader():
    # Regression guard: a missing 20d-ago rank must NOT read as "holding", which
    # previously let a high-rank but unverified stock silently pass as LEADER
    # (the INARI data-gap case).
    assert classify(50, 40, 30, {"attempt": False, "score": 0}, None, 5.0, {"valid": True}, None,
                    rs_rank=90, rs_rank_chg20=None) != "LEADER"


def test_classify_structure_labels():
    assert classify(75, 40, 30, {"attempt": False, "score": 0}, 20.0, None, {"valid": True}, None) == "STRONG BUT EXTENDED"
    assert classify(40, 65, 30, {"attempt": False, "score": 0}, None, None, {"valid": True}, None) == "SETUP"
    assert classify(10, 10, 10, {"attempt": False, "score": 0}, None, None, {"valid": False}, None) == "LAGGARD"


def test_classify_emerging_via_momentum():
    assert classify(75, 30, 30, {"attempt": False, "score": 0}, 10.0, None, {"valid": True}, 1.5) == "EMERGING LEADER"


# ── CLV (closing_strength) ──────────────────────────────────────────────────

def test_closing_strength_basic():
    d = _ohlcv(close=[9.5, 9.8], high=[10, 10], low=[9, 9])
    assert closing_strength(d["high"], d["low"], d["close"]) == 0.8


def test_closing_strength_clamps_and_zero_range():
    # close above high would give >1 -> clamped to 1.0
    d = _ohlcv(close=[9, 11], high=[10, 10], low=[9, 9])
    assert closing_strength(d["high"], d["low"], d["close"]) == 1.0
    # no intraday range (high == low) -> None, never a false strength
    d = _ohlcv(close=[10, 10], high=[10, 10], low=[9, 10])
    assert closing_strength(d["high"], d["low"], d["close"]) is None


def test_closing_strength_nan_last_returns_none():
    d = _ohlcv(close=[9.5, float("nan")], high=[10, 10], low=[9, 9])
    assert closing_strength(d["high"], d["low"], d["close"]) is None


# ── meaningful_range: range/ATR20 gate ───────────────────────────────────────

def test_meaningful_range_typical():
    close = [10 + i * 0.01 for i in range(30)]
    high = [c * 1.01 for c in close]
    low = [c * 0.99 for c in close]
    d = _ohlcv(close=close, high=high, low=low)
    mr = meaningful_range(d["high"], d["low"], d["close"])
    assert mr["meaningful"] is True
    assert mr["range_atr"] is not None and mr["range_atr"] >= 0.8


def test_meaningful_range_tiny_bar_not_meaningful():
    close = [10 + i * 0.01 for i in range(30)]
    # last bar barely moves relative to its ATR -> not meaningful
    high = [c * 1.01 if i < 29 else c for i, c in enumerate(close)]
    low = [c * 0.99 if i < 29 else c for i, c in enumerate(close)]
    d = _ohlcv(close=close, high=high, low=low)
    assert meaningful_range(d["high"], d["low"], d["close"])["meaningful"] is False


# ── price_extension ────────────────────────────────────────────────────────

def test_price_extension():
    up = _s([10 * 1.01 ** i for i in range(30)])
    assert price_extension(up) is not None and price_extension(up) > 0
    flat = _s([10.0] * 30)
    assert abs(price_extension(flat) or 0.0) < 0.01


# ── effort_vs_result (Price Effort) ──────────────────────────────────────────

def _effort_data(close, high, low, volume):
    return _ohlcv(close=close, high=high, low=low, volume=volume)


def test_effort_accumulation():
    # 3x volume, +4% close, tight upper wick -> accumulation
    close = [10 + i * 0.001 for i in range(25)]
    close.append(10.4)                       # prev last ~10.0 -> +4%
    high = [c * 1.01 for c in close]
    high[-1] = close[-1]                     # no upper wick
    low = [c * 0.99 for c in close]
    low[-1] = 10.0
    volume = [1_000_000.0] * 25 + [3_000_000.0]
    d = _effort_data(close, high, low, volume)
    e = effort_vs_result(d["high"], d["low"], d["close"], d["volume"])
    assert e["verdict"] == "accumulation"
    # rolling(20) window includes the spike day itself, so the ratio is not
    # exactly 3.0; the real rule is ">= vol_multiple (2.0)".
    assert e["vol_ratio"] >= 2.0


def test_effort_potential_supply():
    # 3x volume, tiny move, long upper wick -> potential supply
    close = [10 + i * 0.001 for i in range(25)]
    close.append(10.05)                      # +0.5%
    high = [c * 1.01 for c in close]
    high[-1] = 10.5                          # long upper wick
    low = [c * 0.99 for c in close]
    low[-1] = 9.9
    volume = [1_000_000.0] * 25 + [3_000_000.0]
    d = _effort_data(close, high, low, volume)
    e = effort_vs_result(d["high"], d["low"], d["close"], d["volume"])
    assert e["verdict"] == "potential_supply"


def test_effort_no_volume_no_verdict():
    close = [10 + i * 0.001 for i in range(25)]
    close.append(10.4)
    high = [c * 1.01 for c in close]
    low = [c * 0.99 for c in close]
    d = _effort_data(close, high, low, None)
    e = effort_vs_result(d["high"], d["low"], d["close"], d.get("volume"))
    assert e["verdict"] is None and e["vol_ratio"] is None


# ── risk_reward ──────────────────────────────────────────────────────────────

def test_risk_reward():
    rr = risk_reward(10.0, 9.0, 12.0)
    assert rr["valid"] and rr["rr"] == 2.0
    bad = risk_reward(None, 9.0, 12.0)
    assert bad["valid"] is False
    flat = risk_reward(10.0, 10.0, 12.0)
    assert flat["valid"] is False
