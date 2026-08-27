"""GM_V2_KDJ — the single source of truth for the KDJ indicator.

Pine (TradingView) reference, exactly transcribed:

    ilong = period            # default 26
    isig  = signal            # default 5
    h  = ta.highest(high, ilong)
    l  = ta.lowest(low, ilong)
    RSV = h != l ? 100 * (close - l) / (h - l) : 0
    pK = custom_ma(RSV, isig, 1)
    pD = custom_ma(pK, isig, 1)
    pJ = 3 * pK - 2 * pD

where ``custom_ma(src, length, 1)`` is a recursive EMA with alpha = 1/length:

    ma := (1 * src + (length - 1) * nz(ma[1], src)) / length

Important: this is *not* pandas' ``span`` EMA (alpha = 2/(span+1)). It is
``alpha = 1/signal`` with ``adjust=False`` and the first value seeded with the
first RSV — which is exactly what Pine's ``nz(ma[1], src)`` does.

This module is the ONLY place KDJ is defined. screener.py, the chart, the
screeners and (in future) the signal journal must all call ``gm_kdj``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def gm_kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 26,
    signal: int = 5,
) -> dict[str, pd.Series]:
    """Return {k, d, j, rsv} aligned to ``close``'s index (Pine-parity).

    ``period`` and ``signal`` default to the production settings (26 / 5).
    RSV is 0 when the rolling high == low (Pine's ``h != l ? ... : 0``).
    """
    high = high.astype(float).reindex(close.index)
    low = low.astype(float).reindex(close.index)
    close = close.astype(float)

    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    denom = highest - lowest
    rsv = 100.0 * (close - lowest) / denom
    # Pine: RSV = h != l ? 100*(close-l)/(h-l) : 0
    # 0/0 and insufficient-bars -> 0 (not NaN). Guard inf from tiny denom.
    rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    alpha = 1.0 / signal
    k = rsv.ewm(alpha=alpha, min_periods=1, adjust=False).mean()
    d = k.ewm(alpha=alpha, min_periods=1, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return {"k": k, "d": d, "j": j, "rsv": rsv}


def kdj_state(k: pd.Series, d: pd.Series, j: pd.Series | None = None) -> dict[str, Any]:
    """Bullish/bearish state from the LAST bar.

    With J = 3K - 2D, the relations J>K, K>D and J>D are all equivalent to
    K > D, so there is a single canonical state — no ambiguity about which
    "golden" comparison matters.
    """
    kd = bool(float(k.iloc[-1]) > float(d.iloc[-1]))
    spread = round(float(k.iloc[-1]) - float(d.iloc[-1]), 2)
    if spread >= 1e-9:
        state = "BULLISH"
    elif spread <= -1e-9:
        state = "BEARISH"
    else:
        state = "NEUTRAL"
    return {
        "state": state,
        "k_gt_d": kd,
        "k_d_spread": spread,
        # derived (identical to k_gt_d), kept for API completeness
        "j_gt_k": kd,
        "j_gt_d": kd,
    }


def kdj_cross(k: pd.Series, d: pd.Series, j: pd.Series) -> dict[str, Any]:
    """Crosses on the LAST bar vs the previous bar.

    Canonical K/D cross is the "golden cross" (K crosses above D) / "death
    cross" (K crosses below D). J/K and J/D crosses are reported separately so
    the repo's historical J-cross signal is preserved without confusion.
    """
    if len(k) < 2 or len(d) < 2 or len(j) < 2:
        return {"k_d_golden": False, "k_d_death": False,
                "j_k_cross": False, "j_d_cross": False}
    k1, k2 = float(k.iloc[-1]), float(k.iloc[-2])
    d1, d2 = float(d.iloc[-1]), float(d.iloc[-2])
    j1, j2 = float(j.iloc[-1]), float(j.iloc[-2])
    return {
        "k_d_golden": k1 > d1 and k2 <= d2,
        "k_d_death": k1 < d1 and k2 >= d2,
        "j_k_cross": j1 > k1 and j2 <= k2,
        "j_d_cross": j1 > d1 and j2 <= d2,
    }


def kdj_momentum(k: pd.Series, d: pd.Series, j: pd.Series, lookback: int = 5) -> dict[str, float | None]:
    """Linear slope of K/D/J over ``lookback`` bars + J-D spread (last bar)."""
    def slope(s: pd.Series) -> float | None:
        if s is None or len(s.dropna()) < max(2, lookback // 2):
            return None
        y = s.iloc[-lookback:].values.astype(float)
        if np.isnan(y).any():
            return None
        x = np.arange(len(y), dtype=float)
        return round(float(np.polyfit(x, y, 1)[0]), 4)

    return {
        "k_slope": slope(k),
        "d_slope": slope(d),
        "j_slope": slope(j),
        "j_d_spread": round(float(j.iloc[-1]) - float(d.iloc[-1]), 2),
    }


def kdj_divergence(
    close: pd.Series,
    k: pd.Series,
    lookback: int = 30,
    pivot_window: int = 5,
) -> dict[str, Any]:
    """Bullish divergence, two definitions:

    - slope: price falling while K rising over ``lookback`` (the repo's
      historical definition — a *trend-slope* divergence).
    - pivot: a classic swing-low divergence — price makes a lower low while K
      makes a higher low (causal, approximate).
    """
    out: dict[str, Any] = {
        "slope_bullish": False,
        "price_slope": None,
        "k_slope": None,
        "pivot_bullish": False,
    }
    if close is None or k is None or len(close) < lookback or len(k) < lookback:
        return out

    x = np.arange(lookback, dtype=float)
    p = close.iloc[-lookback:].values.astype(float)
    kk = k.iloc[-lookback:].values.astype(float)
    mask = ~np.isnan(p) & ~np.isnan(kk)
    if mask.sum() >= lookback // 2:
        price_slope = float(np.polyfit(x[mask], p[mask], 1)[0])
        k_slope = float(np.polyfit(x[mask], kk[mask], 1)[0])
        out["price_slope"] = round(price_slope, 4)
        out["k_slope"] = round(k_slope, 4)
        out["slope_bullish"] = price_slope < 0 and k_slope > 0

    # swing-low pivot divergence (causal): compare the last two confirmed local
    # minima of close vs K within the lookback.
    def local_mins(s: pd.Series) -> list[float]:
        vals = s.iloc[-lookback:].values.astype(float)
        mins: list[float] = []
        for i in range(pivot_window, len(vals) - pivot_window):
            left = vals[i - pivot_window: i]
            right = vals[i + 1: i + 1 + pivot_window]
            if np.isnan(vals[i]) or left.size == 0 or right.size == 0:
                continue
            if vals[i] <= np.nanmin(left) and vals[i] <= np.nanmin(right):
                mins.append(float(vals[i]))
        return mins

    pm = local_mins(close)
    km = local_mins(k)
    if len(pm) >= 2 and len(km) >= 2:
        # lower low in price, higher low in K
        out["pivot_bullish"] = pm[-1] < pm[-2] and km[-1] > km[-2]
    return out
