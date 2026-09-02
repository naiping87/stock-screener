"""
Setup / structure detection engine for Stock Screener Pro.

Pure functions computing the PRE-BREAKOUT structure of a stock from
already-loaded OHLCV. Everything is causal: each detector only reads bars
up to and including the current bar (no lookahead by construction — the
pivot list is confirmed with bars available at the current date only).

Concepts (from the product spec):
  - Pivot: a swing high that is the highest high of each side for `n` bars
    (rolling-window pivot; the "confirmed" pivot uses only past bars).
  - Closing Strength (CLV): where today's close sits in the day's range —
    1.0 = closes at the high. Used both as a standalone filter and as a
    Breakout-Quality component.
  - Price Extension: how far price has moved above the 20-EMA (overbought
    protection — "strong but extended" is NOT a good entry).
  - Effort vs Result: volume magnitude vs price progress; a 4x-volume day
    that gains only 1% with a long upper wick = potential supply.
  - Shakeout / Failed Breakdown / Reclaim: defined via a support level
    (recent swing low) that is undercut with volume then closed back above.
  - Breakout Quality: numeric score of a pivot-break bar.

All functions return plain dicts / floats, no side effects.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PIVOT_WINDOW = 5              # bars each side to confirm a swing high
CLV_MIN = 0.8                 # default filter threshold (user-adjustable)
EXTENSION_ALERT = 15.0        # % above 20-EMA that flags "extended"
R_R_MIN = 1.5                 # minimum risk/reward to consider a trade
MEANINGFUL_RANGE_ATR = 0.8    # range / ATR20 threshold for "the day actually moved"


# ── Pivot ───────────────────────────────────────────────────────────────────

def detect_pivots(high: pd.Series, low: pd.Series, window: int = PIVOT_WINDOW,
                  max_pivots: int = 8) -> list[dict[str, Any]]:
    """Swing highs confirmed with `window` bars on EVERY side of the current
    bar — but only pivots fully in the PAST are returned (the last `window`
    bars cannot be confirmed yet, so no lookahead).

    Returns {index: bar index, price: high value} for up to max_pivots,
    newest first.
    """
    if high is None or len(high) < 2 * window + 1:
        return []
    h = high.values.astype(float)
    piv: list[dict[str, Any]] = []
    i = len(h) - 1 - window  # last bar with a full `window` window AFTER it
    while i >= window and len(piv) < max_pivots:
        window_hi = h[i]
        left_ok = np.nanmax(h[i - window: i]) <= window_hi
        right_ok = np.nanmax(h[i + 1: i + 1 + window]) <= window_hi
        if left_ok and right_ok and np.isfinite(window_hi) and window_hi > 0:
            piv.append({"index": i, "price": float(window_hi)})
        i -= 1
    return piv


def next_resistance(high: pd.Series, low: pd.Series, close: pd.Series,
                    base_target: float | None = None,
                    window: int = PIVOT_WINDOW, max_pivots: int = 12) -> dict[str, Any] | None:
    """The measured-move target AFTER a breakout: the next confirmed pivot
    ABOVE the nearest pivot (the real resistance to reach), or a 1x base-range
    projection when no higher pivot exists.

    Why not use the nearest pivot as the target? Because a pivot IS the
    trigger level, not the goal: selling at the trigger gives R:R ≈ 0. The
    trade's target is what comes AFTER the breakout.

    Returns {price, distance_pct, kind: 'pivot'|'projection'} or None.
    """
    if high is None or low is None or close is None or len(close) < 2:
        return None
    pv_all = detect_pivots(high, low, window=window, max_pivots=max_pivots)
    if not pv_all:
        return None
    last = float(close.iloc[-1])
    # nearest pivot above price
    above = [p for p in pv_all if p["price"] > last]
    if not above:
        return None
    nearest = min(above, key=lambda p: p["price"])
    # 1) next resistance: the lowest pivot strictly ABOVE the nearest pivot
    higher = [p for p in above if p["price"] > nearest["price"] * 1.005]
    if higher:
        price = min(higher, key=lambda p: p["price"])["price"]
        kind = "pivot"
    else:
        # 2) measured move: width of the base UNDER the pivot, projected up.
        #    target = pivot + (pivot - base_low) — the classic breakout
        #    measurement, honest even at all-time-high platforms. The base low
        #    is the lowest confirmed swing low under the pivot (inline low
        #    pivot detection, same no-lookahead rule as detect_pivots).
        lows_near: list[float] = []
        if low is not None and len(low) >= 2 * window + 1:
            lv = low.astype(float).values
            j = len(lv) - 1 - window
            while j >= window and len(lows_near) < max_pivots:
                lo_hi = lv[j]
                if (np.nanmin(lv[j - window: j]) >= lo_hi
                        and np.nanmin(lv[j + 1: j + 1 + window]) >= lo_hi
                        and np.isfinite(lo_hi) and lo_hi > 0
                        and lo_hi < nearest["price"] * 0.9995):
                    lows_near.append(float(lo_hi))
                j -= 1
        base_low_p = max(lows_near) if lows_near else None
        if base_low_p is not None:
            width = nearest["price"] - base_low_p
            if base_target is not None and base_target > width:
                width = base_target
        else:
            width = base_target or (nearest["price"] * 0.02)  # 2% min projection
        if width > 0:
            price = nearest["price"] + width
            kind = "projection"
        else:
            return None
    return {"price": price,
            "distance_pct": round((price / last - 1) * 100, 2) if last > 0 else None,
            "kind": kind}


def measured_move_target(base_low: pd.Series | None, pivot_price: float | None) -> float | None:
    """Classic measured move: distance from base low to pivot, projected up.

    target = pivot + (pivot - base_low). Only meaningful when the base low
    is provided (e.g. the low of the last base structure).
    """
    if base_low is None or pivot_price is None or base_low <= 0:
        return None
    return round(pivot_price + (pivot_price - base_low), 2)


def nearest_pivot(high: pd.Series, low: pd.Series, close: pd.Series,
                  window: int = PIVOT_WINDOW, max_pivots: int = 8) -> dict[str, Any] | None:
    """The nearest CONFIRMED pivot above the current close (resistance), or
    None when price is already above every confirmed pivot (all-time high)."""
    pivots = detect_pivots(high, low, window=window, max_pivots=max_pivots)
    if not pivots:
        return None
    last = float(close.iloc[-1])
    above = [p for p in pivots if p["price"] > last]
    if not above:
        return None
    best = min(above, key=lambda p: p["price"])  # the nearest resistance
    above_above = [p["price"] for p in pivots]
    return {
        "price": best["price"],
        "distance_pct": round((best["price"] / last - 1) * 100, 2),
        "tested": sum(1 for p in pivots if abs(p["price"] - best["price"]) <= best["price"] * 0.01),
    }


def nearest_support(low: pd.Series, high: pd.Series, close: pd.Series,
                    window: int = PIVOT_WINDOW, max_pivots: int = 8) -> dict[str, Any] | None:
    """Nearest CONFIRMED swing low below price (support). Mirrors detect_pivots
    with lows flipped — same no-lookahead rule."""
    if low is None or len(low) < 2 * window + 1:
        return None
    l = low.values.astype(float)
    piv: list[dict[str, Any]] = []
    i = len(l) - 1 - window
    while i >= window and len(piv) < max_pivots:
        window_lo = l[i]
        left_ok = np.nanmin(l[i - window: i]) >= window_lo
        right_ok = np.nanmin(l[i + 1: i + 1 + window]) >= window_lo
        if left_ok and right_ok and np.isfinite(window_lo) and window_lo > 0:
            piv.append({"index": i, "price": float(window_lo)})
        i -= 1
    if not piv:
        return None
    last = float(close.iloc[-1])
    below = [p for p in piv if p["price"] < last]
    if not below:
        return None
    best = max(below, key=lambda p: p["price"])
    return {
        "price": best["price"],
        "distance_pct": round((last / best["price"] - 1) * 100, 2),
    }


# ── Closing strength (CLV) ──────────────────────────────────────────────────

def closing_strength(high: pd.Series, low: pd.Series, close: pd.Series) -> float | None:
    """CLV = (close - low) / (high - low), 0..1. None when the day has no range
    (high == low — many Bursa micro-caps), so it never counts as strength.
    NaN last bar (unclosed session) → None, never a false strength."""
    if high is None or low is None or close is None or len(close) == 0:
        return None
    h = float(high.iloc[-1])
    lo = float(low.iloc[-1])
    c = float(close.iloc[-1])
    if not (np.isfinite(h) and np.isfinite(lo) and np.isfinite(c)):
        return None
    rng = h - lo
    if rng <= 0:
        return None
    return round(min(1.0, max(0.0, (c - lo) / rng)), 3)


# ── Meaningful range (range / ATR) ────────────────────────────────────────

def _wild_atr(high: pd.Series, low: pd.Series, close: pd.Series,
              n: int = 20) -> pd.Series:
    """Wilder ATR series. Causal: each value only uses bars up to itself.
    m is the period; alpha = 1/m gives the standard Wilder smoothing."""
    pc = close.shift(1)
    tr = pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def meaningful_range(high: pd.Series, low: pd.Series, close: pd.Series,
                     n: int = 20, offset: int = 0) -> dict[str, Any]:
    """range / ATR(n) for the bar at index [-1 - offset].

    A value >= MEANINGFUL_RANGE_ATR means the day expanded enough that a
    high close (strong CLV) is actually informative — otherwise CLV can read
    ~1.0 on a tiny-range bar and look strong when nothing really happened.

    offset=0 → the current (last) bar; offset=1 → the previous bar, which is
    what intraday mode uses so it lines up with ``yesterday_clv``.

    Causal: ATR is computed only on data sliced up to that bar, so no future
    bar can leak in. Returns None where the bar has no range or the window is
    too short.
    """
    if high is None or low is None or close is None:
        return {"range_atr": None, "meaningful": False}
    k = len(close) - 1 - offset
    if k < n or k < 1:
        return {"range_atr": None, "meaningful": False}
    h = high.iloc[:k + 1]
    lo = low.iloc[:k + 1]
    c = close.iloc[:k + 1]
    if h.isna().any() or lo.isna().any() or c.isna().any():
        return {"range_atr": None, "meaningful": False}
    hi = float(h.iloc[-1])
    lo_ = float(lo.iloc[-1])
    rng = hi - lo_
    atr = float(_wild_atr(h, lo, c, n).iloc[-1])
    if not (np.isfinite(rng) and np.isfinite(atr)) or rng <= 0 or atr <= 0:
        return {"range_atr": None, "meaningful": False}
    ratio = rng / atr
    return {
        "range_atr": round(ratio, 3),
        "meaningful": bool(ratio >= MEANINGFUL_RANGE_ATR),
    }


def clv_series(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Full CLV series (for backtests). NaN where range == 0 or data missing."""
    rng = (high - low).astype(float)
    clv = ((close - low) / rng.replace(0, np.nan)).astype(float)
    return clv


def yesterday_clv(high: pd.Series, low: pd.Series, close: pd.Series) -> float | None:
    """The CLV of the LAST COMPLETED trading day (the bar before the current
    bar). In intraday mode the current bar is unfinished, so the completed
    day's close strength is the reliable reference; closing_strength() would
    report an unstable intraday number instead.
    """
    if high is None or low is None or close is None or len(close) < 2:
        return None
    h = float(high.iloc[-2])
    lo = float(low.iloc[-2])
    c = float(close.iloc[-2])
    if not (np.isfinite(h) and np.isfinite(lo) and np.isfinite(c)):
        return None
    rng = h - lo
    if rng <= 0:
        return None
    return round(min(1.0, max(0.0, (c - lo) / rng)), 3)


def intraday_position(high: pd.Series, low: pd.Series, close: pd.Series) -> float | None:
    """Where the CURRENT price sits in TODAY'S (in-progress) range: 0 at the
    low, 1 at the high. Informational in intraday mode — the same value that
    will become the day's CLV once the market closes.
    """
    if high is None or low is None or close is None or len(close) == 0:
        return None
    h = float(high.iloc[-1])
    lo = float(low.iloc[-1])
    c = float(close.iloc[-1])
    if not (np.isfinite(h) and np.isfinite(lo) and np.isfinite(c)):
        return None
    rng = h - lo
    if rng <= 0:
        return None
    return round(min(1.0, max(0.0, (c - lo) / rng)), 3)


# ── Price extension ─────────────────────────────────────────────────────────

def price_extension(close: pd.Series, window: int = 20) -> float | None:
    """% distance from close to its EMA(window). Positive = above EMA."""
    if close is None or len(close) < window:
        return None
    ema = close.ewm(span=window, adjust=False).mean()
    e = float(ema.iloc[-1])
    c = float(close.iloc[-1])
    if not (np.isfinite(e) and np.isfinite(c)) or e <= 0:
        return None
    return round((c / e - 1) * 100, 2)


# ── Effort vs Result ────────────────────────────────────────────────────────

def effort_vs_result(high: pd.Series, low: pd.Series, close: pd.Series,
                     volume: pd.Series | None, vol_window: int = 20,
                     vol_multiple: float = 2.0) -> dict[str, Any]:
    """Classify today's volume-price behaviour.

    Returns:
      vol_ratio     — today volume / 20-day avg volume
      price_move    — today's close-to-close % move
      upper_wick    — (high - max(open≈prev close, close)) / high, 0..1 (approx)
      verdict       — 'supply' | 'accumulation' | 'normal' | None
    """
    if high is None or low is None or close is None or len(close) < vol_window + 1:
        return {"verdict": None, "vol_ratio": None, "price_move": None, "upper_wick": None}
    c_now = float(close.iloc[-1])
    c_prev = float(close.iloc[-2])
    h = float(high.iloc[-1])
    if not all(np.isfinite(v) for v in (c_now, c_prev, h)) or c_prev <= 0:
        return {"verdict": None, "vol_ratio": None, "price_move": None, "upper_wick": None}
    move = (c_now / c_prev - 1) * 100.0
    vol_ratio = None
    upper_wick = None
    if volume is not None and len(volume) >= vol_window:
        v_now = float(volume.iloc[-1])
        v_avg = float(volume.rolling(vol_window).mean().iloc[-1])
        if np.isfinite(v_now) and np.isfinite(v_avg) and v_avg > 0:
            vol_ratio = round(v_now / v_avg, 2)
            # upper wick fraction relative to day's range
            lo = float(low.iloc[-1])
            rng = h - lo
            if rng > 0 and np.isfinite(lo):
                upper_wick = round(max(0.0, (h - c_now) / rng), 3)

    verdict = None
    if vol_ratio is not None and vol_ratio >= vol_multiple:
        if move <= 1.5 and (upper_wick is not None and upper_wick >= 0.5):
            verdict = "potential_supply"
        elif move >= 3.0 and (upper_wick is None or upper_wick <= 0.35):
            verdict = "accumulation"
        else:
            verdict = "high_vol_ambiguous"
    return {"verdict": verdict, "vol_ratio": vol_ratio,
            "price_move": round(move, 2), "upper_wick": upper_wick}


# ── Liquidity (ADTV = close × volume) ───────────────────────────────────────

ADTV_WINDOW = 20            # recent-activity window (exposed as a reference column)
ADTV_STRUCT_WINDOW = 60     # structural-liquidity window used for the gate/tiers
LIQ_HARD_FLOOR = 20_000     # RM; below this a name is not a tradeable Ignition (🔴)


def average_daily_traded_value(close: pd.Series | None, volume: pd.Series | None,
                               window: int = ADTV_STRUCT_WINDOW) -> float | None:
    """Average Daily Traded Value = SMA(close × volume, `window`) in RM.

    Causal (only the last `window` bars) and robust to Bursa/Yahoo data holes:
    a bar missing either a close or a volume is dropped, so a NaN tail never
    poisons the average the way a naive rolling() does (see AGENTS.md data
    integrity notes). Returns None when there are too few valid bars.
    """
    if close is None or volume is None or len(close) < window:
        return None
    frame = pd.DataFrame({"close": close, "volume": volume}).dropna(
        subset=["close", "volume"])
    frame = frame[frame["close"] > 0]
    if len(frame) < window:
        return None
    amt = frame["close"] * frame["volume"]
    val = amt.rolling(window).mean().iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def liquidity_tier(adtv: float | None,
                   hard_floor: float = LIQ_HARD_FLOOR) -> dict[str, Any]:
    """Map an (usually structural) ADTV value to a liquidity bucket.

    Returns {tier, label, emoji, mult, gate}:
      tier  — ILLIQUID / LOW / TRADABLE / GOOD / HIGH (None when no data)
      emoji — 🔴 🟠 🟡 🟢 🔥 for the UI status column
      mult  — a score multiplier applied to master_rr (the ranking) so liquidity
              tempers confidence WITHOUT replacing price action: ILLIQUID is
              heavily down-weighted, LOW is softened, HIGH only gets a small lift.
      gate  — True when below `hard_floor`: "not a tradeable Ignition".
    """
    if adtv is None or not np.isfinite(adtv):
        return {"tier": None, "label": "No Data", "emoji": "—",
                "mult": 1.0, "gate": False}
    if adtv < hard_floor:
        return {"tier": "ILLIQUID", "label": "Illiquid", "emoji": "🔴",
                "mult": 0.35, "gate": True}
    if adtv < 100_000:
        return {"tier": "LOW", "label": "Low Liquidity", "emoji": "🟠",
                "mult": 0.70, "gate": False}
    if adtv < 1_000_000:
        return {"tier": "TRADABLE", "label": "Tradable", "emoji": "🟡",
                "mult": 1.00, "gate": False}
    if adtv < 3_000_000:
        return {"tier": "GOOD", "label": "Good Liquidity", "emoji": "🟢",
                "mult": 1.05, "gate": False}
    return {"tier": "HIGH", "label": "High Liquidity", "emoji": "🔥",
            "mult": 1.10, "gate": False}


def volume_participation(vol_ratio: float | None) -> str | None:
    """Label today's volume participation (today / 20d avg). Soft signal only."""
    if vol_ratio is None or not np.isfinite(vol_ratio):
        return None
    if vol_ratio < 0.5:
        return "Very Low"
    if vol_ratio < 0.8:
        return "Low"
    if vol_ratio < 1.2:
        return "Normal"
    if vol_ratio < 1.5:
        return "Confirming"
    if vol_ratio < 2.0:
        return "Strong"
    return "Very Strong"


# ── Base / consolidation ────────────────────────────────────────────────────

def base_quality(high: pd.Series, low: pd.Series, close: pd.Series,
                 volume: pd.Series | None, lookback: int = 40,
                 ma_window: int = 60) -> dict[str, Any]:
    """Base health over the last `lookback` bars.

    Returns:
      range_pct      — (max high - min low) / close, last lookback bars
      higher_low     — min low of the last half > min low of the first half
      vol_dryup      — avg vol of the last half < avg vol of the first half
      atr_slope      — ATR trend over the window (-1 falling, 1 rising, 0 flat)
      bars           — lookback
    """
    if high is None or low is None or close is None or len(close) < lookback:
        return {"valid": False}
    hb = high.iloc[-lookback:]
    lb = low.iloc[-lookback:]
    cb = close.iloc[-lookback:]
    if cb.isna().any() or hb.isna().any() or lb.isna().any():
        return {"valid": False}
    rng = (float(hb.max()) - float(lb.min())) / float(cb.iloc[-1]) * 100.0

    half = lookback // 2
    hi_lo = float(lb.iloc[-half:].min())
    lo_lo = float(lb.iloc[:half].min())

    vol_dryup = None
    if volume is not None and len(volume) >= lookback:
        v1 = float(volume.iloc[:half].mean())
        v2 = float(volume.iloc[-half:].mean())
        if np.isfinite(v1) and np.isfinite(v2) and v1 > 0:
            vol_dryup = v2 < v1

    # ATR trend on price range (high-low) median
    tr = (hb - lb).values.astype(float)
    atr_slope = 0
    if len(tr) >= 10:
        coef = np.polyfit(np.arange(len(tr), dtype=float), tr, 1)[0]
        atr_slope = -1 if coef < 0 else (1 if coef > 0 else 0)

    return {"valid": True, "range_pct": round(rng, 2),
            "higher_low": hi_lo > lo_lo, "vol_dryup": vol_dryup,
            "atr_slope": atr_slope, "bars": lookback}


# ── Shakeout / Reclaim ──────────────────────────────────────────────────────

def shakeout_check(high: pd.Series, low: pd.Series, close: pd.Series,
                   volume: pd.Series | None, support_price: float | None,
                   lookback: int = 10, vol_multiple: float = 1.5) -> dict[str, Any]:
    """Today OR any of the last `lookback` bars undercut a support level with
    volume, then closed back above it.

    support_price must be a PREDEFINED level (e.g. nearest_support from BEFORE
    today) — the caller supplies it so no lookahead is possible.
    """
    if support_price is None or high is None or low is None or close is None:
        return {"detected": False}
    c = close.values.astype(float)
    lo = low.values.astype(float)
    hi = high.values.astype(float)
    v = volume.values.astype(float) if volume is not None and len(volume) == len(close) else None

    for back in range(1, lookback + 1):
        i = len(c) - back
        if i < 1:
            break
        undercut = lo[i] < support_price <= hi[i]
        reclaim = c[i] > support_price
        vol_ok = True
        if v is not None and v[i - 1] > 0:
            vol_ok = v[i] > v[i - 1] * vol_multiple
        if undercut and reclaim and vol_ok:
            return {
                "detected": True,
                "bars_ago": back,
                "support": support_price,
                "vol_ok": vol_ok,
            }
    return {"detected": False}


# ── Breakout quality ────────────────────────────────────────────────────────

def breakout_quality(high: pd.Series, low: pd.Series, close: pd.Series,
                     volume: pd.Series | None, pivot_price: float | None,
                     clv: float | None, rs_20d: float | None,
                     sector_rel_20d: float | None,
                     vol_multiple: float = 1.5) -> dict[str, Any]:
    """Score today's bar as a pivot breakout attempt (0-100).

    A high score means the bar LOOKS like a genuine expansion. Components:
      40% close-through (close above pivot)
      20% volume (>=1.5x 20d avg)
      15% close strength (CLV)
      15% relative strength (stock and sector vs market)
      10% no-failed-breakout (close within 2% below pivot is the ONLY soft case)
    Score is 0 when price never traded above the pivot (no breakout attempt).
    """
    if pivot_price is None or high is None or close is None or len(close) < 2:
        return {"attempt": False, "score": 0, "reason": "no pivot"}
    h = float(high.iloc[-1])
    c = float(close.iloc[-1])
    if not np.isfinite(h) or not np.isfinite(c):
        return {"attempt": False, "score": 0, "reason": "bad data"}

    attempted = h >= pivot_price
    if not attempted:
        return {"attempt": False, "score": 0, "reason": "below pivot"}

    score = 0.0
    if c > pivot_price:
        score += 40.0
    elif c >= pivot_price * 0.98:
        score += 15.0  # close just under — wait for confirmation

    vol_ratio = None
    if volume is not None and len(volume) >= 21:
        v_now = float(volume.iloc[-1])
        v_avg = float(volume.rolling(20).mean().iloc[-1])
        if np.isfinite(v_now) and np.isfinite(v_avg) and v_avg > 0:
            vol_ratio = round(v_now / v_avg, 2)
            if v_now >= v_avg * vol_multiple:
                score += min(20.0, (v_now / v_avg) * 10.0)

    if clv is not None:
        score += min(15.0, clv * 15.0)

    if rs_20d is not None and rs_20d > 0:
        score += min(15.0, rs_20d * 0.3)
    if sector_rel_20d is not None and sector_rel_20d > 0:
        score += min(10.0, sector_rel_20d * 0.2)

    return {"attempt": True, "score": round(min(100.0, score), 1),
            "close_vs_pivot_pct": round((c / pivot_price - 1) * 100, 2) if pivot_price > 0 else None,
            "vol_ratio": vol_ratio}


# ── EMA pullback + reclaim (dynamic-support / healthy-pullback setup) ──────

def _ema_slope(ema: pd.Series, bars: int = 10) -> float | None:
    """Slope of an EMA series over the last `bars` bars (per-bar units).
    None when insufficient data. Positive = rising trend line."""
    if ema is None or len(ema) < bars:
        return None
    y = ema.iloc[-bars:].values.astype(float)
    if np.isnan(y).any():
        return None
    return float(np.polyfit(np.arange(bars, dtype=float), y, 1)[0])


def ema_pullback_reclaim(close: pd.Series, high: pd.Series, low: pd.Series,
                         volume: pd.Series | None, ema_fast: int = 20,
                         ema_slow: int = 60, runup_window: int = 60,
                         min_extension: float = 5.0, lookback: int = 40,
                         slope_bars: int = 10, pullback_max_pct: float = 4.0,
                         reclaim_lookback: int = 15, dryup_ratio: float = 0.9,
                         touch_tol: float = 1.005,
                         reclaim_fresh_bars: int = 5,
                         current_near_pct: float = 5.0) -> dict[str, Any]:
    """Detect the "strong uptrend → pullback to EMA(slow) → reclaim" setup.

    Causal: reads bars up to and including the last bar only (no lookahead).
    This is deliberately NOT "price ≈ EMA(slow) => buy". It requires, together:
      - a prior run-up where price held above EMA(fast) above EMA(slow);
      - EMA(slow) still rising (slope > 0);
      - a pullback that came within `pullback_max_pct` of EMA(slow) (or dipped
        to it) over the lookback window;
      - volume drying up during the pullback (supply contracting);
      - a reclaim bar: it touched EMA(slow) and closed back above it, closing in
        the upper half of the day's range (no distribution).
      - FRESH only: the reclaim must have happened within `reclaim_fresh_bars`
        bars (default 5) AND the current close must still be within
        `current_near_pct` (default 5%) of EMA(slow). Without this, a stock
        that reclaimed EMA60 two weeks ago and then ran +30% is still labelled
        "EMA RECLAIM near EMA60" — which is not what a trader sees on the chart.

    Returns a dict (always, never raises):
      detected, pullback_pct, slope_ok, vol_dryup, reclaim_bars_ago,
      ran_up, no_distribution
    """
    empty = {"detected": False, "pullback_pct": None, "slope_ok": False,
             "vol_dryup": None, "reclaim_bars_ago": None,
             "ran_up": False, "no_distribution": None}
    need = ema_slow + max(runup_window, lookback, reclaim_lookback) + slope_bars
    if close is None or len(close) < need:
        return empty
    c = close.astype(float).dropna()
    if len(c) < need:
        return empty
    # Align high/low/volume to the close's (last-valid) calendar.
    last_ts = c.index[-1]
    h = high.loc[:last_ts].astype(float) if high is not None else None
    lo = low.loc[:last_ts].astype(float) if low is not None else None
    v = volume.loc[:last_ts].astype(float) if volume is not None else None
    if h is None or lo is None or len(h) < lookback + 3:
        return empty

    fast = c.ewm(span=ema_fast, adjust=False).mean()
    slow = c.ewm(span=ema_slow, adjust=False).mean()
    if len(slow.dropna()) < slope_bars:
        return empty

    slope_ok = (_ema_slope(slow, slope_bars) or 0.0) > 0
    if not slope_ok:
        return empty

    # ── run-up: price ran meaningfully ABOVE EMA(slow) at some point recently.
    # We measure PEAK extension (not a live EMA20>EMA60 state) because the
    # pullback itself is expected to break close>EMA(fast) — that is the very
    # setup. peak_ext >= min_extension means there WAS a real run-up.
    run_win = c.iloc[-runup_window:]
    slow_run = slow.iloc[-runup_window:]
    ext_run = (run_win.values / slow_run.values - 1.0) * 100.0
    ext_run = ext_run[np.isfinite(ext_run)]
    peak_ext = float(np.nanmax(ext_run)) if ext_run.size else None
    ran_up = peak_ext is not None and peak_ext >= min_extension

    # ── pullback depth: how close the low got to EMA(slow) ────────────────
    lo_win = lo.iloc[-lookback:]
    slow_pull = slow.iloc[-lookback:]
    low_vs_slow = (lo_win.values / slow_pull.values - 1.0) * 100.0
    low_vs_slow = low_vs_slow[np.isfinite(low_vs_slow)]
    pullback_pct = round(float(np.min(low_vs_slow)), 2) if low_vs_slow.size else None
    # "near EMA(slow)" means the low came WITHIN pullback_max_pct of the EMA
    # on EITHER side. The old `pullback_pct <= pullback_max_pct` was wrong: a
    # stock whose low fell 8% BELOW the EMA (pullback_pct = -8) still passed
    # (-8 <= 4), so deep dips were called "near". Use abs() so only ±4% counts.
    near_slow = pullback_pct is not None and abs(pullback_pct) <= pullback_max_pct

    # ── volume dry-up during the pullback (bars where close fell under fast) ─
    vol_dryup = None
    if v is not None and len(v) >= lookback:
        vwin = v.iloc[-lookback:].values.astype(float)
        fast_pull = fast.iloc[-lookback:]
        below = (c.iloc[-lookback:].values < fast_pull.values)
        pull = vwin[below] if below.any() else np.array([])
        run_up = vwin[~below] if (~below).any() else np.array([])
        if pull.size and run_up.size:
            pull_avg = float(np.nanmean(pull))
            run_avg = float(np.nanmean(run_up))
            if run_avg > 0:
                vol_dryup = pull_avg < run_avg * dryup_ratio

    # ── reclaim: touched EMA(slow) then closed back above, upper half of range
    reclaim_bars_ago = None
    no_distribution = None
    for back in range(1, reclaim_lookback + 1):
        i = len(c) - back
        if i < 1:
            break
        if not np.isfinite(float(slow.iloc[i])):
            continue
        touched = float(lo.iloc[i]) <= float(slow.iloc[i]) * touch_tol
        closed_above = float(c.iloc[i]) > float(slow.iloc[i])
        if touched and closed_above:
            reclaim_bars_ago = back
            day_low = float(lo.iloc[i]); day_high = float(h.iloc[i])
            day_mid = day_low + 0.5 * (day_high - day_low)
            no_distribution = float(c.iloc[i]) >= day_mid
            break
    if no_distribution is None:
        # fall back: current bar itself closed in the upper half
        day_low = float(lo.iloc[-1]); day_high = float(h.iloc[-1])
        if np.isfinite(day_low) and np.isfinite(day_high) and day_high > day_low:
            no_distribution = float(c.iloc[-1]) >= day_low + 0.5 * (day_high - day_low)
    if reclaim_bars_ago is None:
        # The reclaim bar may already be outside the scan window; accept a
        # "just reclaimed" state: price is above EMA(slow) now AND the low of
        # the pullback window touched EMA(slow).
        touched = (lo_win.values <= slow_pull.values * touch_tol).any()
        if touched and float(c.iloc[-1]) > float(slow.iloc[-1]):
            reclaim_bars_ago = 0
            day_low = float(lo.iloc[-1]); day_high = float(h.iloc[-1])
            if np.isfinite(day_low) and np.isfinite(day_high) and day_high > day_low:
                no_distribution = float(c.iloc[-1]) >= day_low + 0.5 * (day_high - day_low)

    # Freshness guard so the label reflects the CURRENT setup, not a reclaim
    # that already ran away. YTLPOWER-style: reclaimed 13 bars ago, price now
    # +30% above EMA60 — must NOT still read "EMA RECLAIM near EMA60".
    current_close_vs_slow = None
    if np.isfinite(float(c.iloc[-1])) and np.isfinite(float(slow.iloc[-1])) and float(slow.iloc[-1]) != 0:
        current_close_vs_slow = abs(float(c.iloc[-1]) / float(slow.iloc[-1]) - 1.0) * 100.0
    fresh = (reclaim_bars_ago is not None
             and reclaim_bars_ago <= reclaim_fresh_bars
             and current_close_vs_slow is not None
             and current_close_vs_slow <= current_near_pct)

    detected = bool(slope_ok and ran_up and near_slow and fresh
                    and reclaim_bars_ago is not None
                    and (vol_dryup is None or vol_dryup)
                    and (no_distribution is None or no_distribution))
    return {"detected": detected, "pullback_pct": pullback_pct, "slope_ok": slope_ok,
            "vol_dryup": vol_dryup, "reclaim_bars_ago": reclaim_bars_ago,
            "ran_up": ran_up, "no_distribution": no_distribution}


# ── Failed breakdown / failed breakout (explicit labels) ───────────────────

def failed_breakdown(high: pd.Series, low: pd.Series, close: pd.Series,
                     volume: pd.Series | None, support_price: float | None,
                     lookback: int = 8, vol_multiple: float = 1.5) -> dict[str, Any]:
    """A support level was undercut with volume, then the price reclaimed it and
    closed in the upper half of the day's range. "Potential failed breakdown /
    shakeout / absorption" — NEVER called accumulation (per the spec).

    support_price must be a pre-existing level (no lookahead).
    """
    empty = {"detected": False, "bars_ago": None, "reclaim_clv": None,
             "support": support_price, "vol_ok": None}
    if support_price is None or high is None or low is None or close is None:
        return empty
    c = close.values.astype(float); lo = low.values.astype(float)
    hi = high.values.astype(float)
    v = volume.values.astype(float) if volume is not None and len(volume) == len(close) else None
    for back in range(1, lookback + 1):
        i = len(c) - back
        if i < 1:
            break
        undercut = lo[i] < support_price <= hi[i]
        reclaim = c[i] > support_price
        rng = hi[i] - lo[i]
        # close in the upper 50% of the range (strong reclaim) else it is a
        # lower-half close / real breakdown signal, not a shakeout.
        close_strength = (c[i] - lo[i]) / rng if rng > 0 else 0.0
        vol_ok = True
        if v is not None and v[i - 1] > 0:
            vol_ok = v[i] > v[i - 1] * vol_multiple
        if undercut and reclaim and close_strength >= 0.5:
            return {"detected": True, "bars_ago": back,
                    "reclaim_clv": round(float(close_strength), 3),
                    "support": support_price, "vol_ok": vol_ok}
    return empty


def failed_breakout(high: pd.Series, low: pd.Series, close: pd.Series,
                    volume: pd.Series | None, pivot_price: float | None,
                    lookback: int = 6, vol_multiple: float = 1.5) -> dict[str, Any]:
    """Traded above the pivot with volume but CLOSED back below it — the
    classic "potential failed breakout". Distinct from breakout_quality which
    only scores a successful hold above the pivot.

    pivot_price must be a pre-existing level (no lookahead).
    """
    empty = {"failed": False, "bars_ago": None, "close_vs_pivot_pct": None,
             "vol_ratio": None}
    if pivot_price is None or high is None or close is None or pivot_price <= 0:
        return empty
    c = close.values.astype(float); hi = high.values.astype(float)
    v = volume.values.astype(float) if volume is not None and len(volume) == len(close) else None
    for back in range(1, lookback + 1):
        i = len(c) - back
        if i < 1:
            break
        before = c[i - 1] if i > 0 else None
        # only a "breakout attempt" if price was BELOW pivot just before
        if before is None or not np.isfinite(before) or before >= pivot_price:
            continue
        traded_above = hi[i] >= pivot_price
        closed_below = c[i] < pivot_price
        vol_ratio = None
        if v is not None and i >= 20 and v[i - 20:i].mean() > 0:
            vol_ratio = round(v[i] / v[i - 20:i].mean(), 2)
        if traded_above and closed_below:
            return {"failed": True, "bars_ago": back,
                    "close_vs_pivot_pct": round((c[i] / pivot_price - 1) * 100, 2),
                    "vol_ratio": vol_ratio}
    return empty


# ── Risk / reward ───────────────────────────────────────────────────────────

def risk_reward(entry: float | None, stop: float | None,
                target: float | None) -> dict[str, Any]:
    """R:R for an (entry, stop, target) triple. None inputs → invalid."""
    if entry is None or stop is None or target is None:
        return {"valid": False}
    if entry <= 0 or stop <= 0 or target <= 0:
        return {"valid": False}
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0:
        return {"valid": False}
    return {"valid": True,
            "risk_pct": round(risk / entry * 100, 2),
            "reward_pct": round(reward / entry * 100, 2),
            "rr": round(reward / risk, 2)}
