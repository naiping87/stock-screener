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
    average_daily_traded_value,
    closing_strength,
    effort_vs_result,
    liquidity_tier,
    meaningful_range,
    price_extension,
    risk_reward,
    volume_participation,
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


# ── Liquidity (ADTV = close × volume) ───────────────────────────────────────

def test_average_daily_traded_value():
    close = _s([10.0] * 30)
    vol = _s([100_000.0] * 30)
    assert average_daily_traded_value(close, vol, 20) == 10.0 * 100_000.0


def test_average_daily_traded_value_drops_data_hole():
    # A trailing NaN close (Yahoo data hole) must not poison the average.
    close = _s([10.0] * 29 + [float("nan")])
    vol = _s([100_000.0] * 30)
    assert average_daily_traded_value(close, vol, 20) == 10.0 * 100_000.0


def test_average_daily_traded_value_short_data():
    assert average_daily_traded_value(_s([10.0] * 5), _s([100_000.0] * 5), 20) is None


def test_liquidity_tier_buckets():
    assert liquidity_tier(5_000)["tier"] == "ILLIQUID"
    assert liquidity_tier(5_000)["gate"] is True
    assert liquidity_tier(50_000)["tier"] == "LOW"
    assert liquidity_tier(500_000)["tier"] == "TRADABLE"
    assert liquidity_tier(2_000_000)["tier"] == "GOOD"
    assert liquidity_tier(5_000_000)["tier"] == "HIGH"
    assert liquidity_tier(None)["tier"] is None
    assert liquidity_tier(None)["gate"] is False


def test_liquidity_tier_hard_floor_override():
    # Raising the hard floor re-buckets a normally-LOW name as ILLIQUID.
    assert liquidity_tier(50_000, hard_floor=300_000)["tier"] == "ILLIQUID"


def test_volume_participation():
    assert volume_participation(0.3) == "Very Low"
    assert volume_participation(1.0) == "Normal"
    assert volume_participation(2.5) == "Very Strong"
    assert volume_participation(None) is None


# ── Trend / Position evaluation (Structure vs Trend, user-approved design) ──

def _make_close(n: int, start: float, trend: float, noise: float = 0.0) -> pd.Series:
    """Monotonic-ish close series for deterministic EMA200 tests."""
    return _s([start + trend * i + noise * (i % 3) for i in range(n)])


def test_trend_position_sunway_regression():
    # Sunway 5211.KL case: close 4.960 vs EMA200 5.255 (-5.62%). A long series
    # that decays to that relationship; we assert the DIRECTION, not exact EMA.
    from screener_setup import trend_position
    close = _make_close(280, 7.0, -0.0072)   # falls over time => EMA200 above close
    t = trend_position(close)
    assert t is not None
    assert t["ema200"] > close.iloc[-1]          # price under EMA200
    assert t["above"] is False
    assert t["distance_pct"] < 0                 # below EMA200
    assert "slope" in t


def test_trend_position_edge_slightly_below_rising():
    # Price just under a RISING EMA200 -> NOT a weak trend (healthy pullback).
    from screener_setup import trend_position
    close = _make_close(280, 4.0, 0.0045)        # rising => EMA200 below price
    t = trend_position(close)
    assert t is not None
    assert t["above"] is True
    assert t["slope"] > 0
    assert t["weak"] is False


def test_trend_position_edge_significantly_below_falling():
    # Well below a FALLING EMA200 -> weak trend.
    from screener_setup import trend_position
    close = _make_close(280, 8.0, -0.0100)
    t = trend_position(close)
    assert t is not None
    assert t["above"] is False
    assert t["slope"] < 0
    assert t["weak"] is True


def test_trend_position_edge_above_healthy():
    # Above a healthy (rising) EMA200 -> not weak.
    from screener_setup import trend_position
    close = _make_close(280, 4.0, 0.0060)
    t = trend_position(close)
    assert t is not None
    assert t["above"] is True
    assert t["weak"] is False


def test_trend_position_short_history_returns_none():
    # < 200 bars -> None, classification must still work without a trend.
    from screener_setup import trend_position
    assert trend_position(_s([10.0] * 50)) is None


def test_trend_position_short_history_returns_none():
    # < 200 bars -> None, classification must still work without a trend.
    from screener_setup import trend_position
    assert trend_position(_s([10.0] * 50)) is None


def test_trend_status_carries_weak_flag_for_sunway_shape():
    # The row-level trend_status (not the classify label) distinguishes
    # "structure exists but long-term trend weak". below + falling slope =
    # weak; below + rising = weak=False (healthy pullback).
    from screener_setup import trend_position
    # case A: long decline -> price below a falling EMA200 => weak
    weak_close = _make_close(280, 8.0, -0.0100)
    # case B: long steady rise then a 2-day crash -> close below a STILL-RISING
    # EMA200 (healthy pullback, NOT weakness)
    vals = [3.5 + 0.006 * i for i in range(278)]
    pre = vals[-1]
    vals.append(pre * 0.85)
    vals.append(vals[-1] * 0.85)
    rising_close = _s(vals)
    tw = trend_position(weak_close)
    tr = trend_position(rising_close)
    assert tw["weak"] is True
    assert tr["above"] is False        # price dipped below EMA200
    assert tr["slope"] > 0             # ...but EMA200 is still rising
    assert tr["weak"] is False


# ── EMA60 slope (new EMA60-slope-up filter) ────────────────────────────────

def test_ema_slope_positive_rising():
    from screener_setup import ema_slope
    # steady uptrend -> EMA60 slope > 0
    c = _s([3.0 + 0.01 * i for i in range(100)])
    s = ema_slope(c, window=60, bars=10)
    assert s is not None and s > 0


def test_ema_slope_negative_falling():
    from screener_setup import ema_slope
    c = _s([5.0 - 0.01 * i for i in range(100)])
    s = ema_slope(c, window=60, bars=10)
    assert s is not None and s < 0


def test_ema_slope_flat_near_zero():
    from screener_setup import ema_slope
    c = _s([4.0] * 100)
    s = ema_slope(c, window=60, bars=10)
    assert s is not None and abs(s) < 1e-9


def test_ema_slope_short_history_none():
    from screener_setup import ema_slope
    assert ema_slope(_s([10.0] * 30), window=60, bars=10) is None
    assert ema_slope(None) is None
