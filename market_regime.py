"""Market regime detector (whole-market health axis).

Pure functions over an already-loaded close matrix + optional benchmark.
Everything is causal: only data up to the last bar is used, so the same
function can be run in backtest at any historical date without lookahead.

Concepts (per the audit):
  - Breadth   : fraction of stocks trading ABOVE their own 20-day MA. A market
                selling off shows breadth collapsing even if the index holds.
  - Trend     : median return of the whole universe over the lookback window
                (equal-weight) — more honest than a single index that is
                dragged by a few heavy weights. Falls back to the benchmark.
  - Regime    : RISK_ON / NEUTRAL / RISK_OFF from trend + breadth.
  - Volatility: cross-sectional mean daily |return| (chop measure).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TREND_WINDOW = 60          # days for trend return
BREADTH_WINDOW = 20        # MA for breadth
RISK_ON_TREND = 1.5        # % median + return to call RISK_ON (60d)
RISK_OFF_TREND = -1.5      # % median return to call RISK_OFF
RISK_ON_BREADTH = 0.55     # fraction above MA20 for risk-on bias
RISK_OFF_BREADTH = 0.35    # fraction above MA20 for risk-off bias


def _robust_ret(series: pd.Series, window: int) -> float | None:
    """% change from the last-vs-prior valid close, window bars apart."""
    v = series.astype(float).dropna()
    if len(v) < window + 1:
        return None
    e = float(v.iloc[-1]); p = float(v.iloc[-(window + 1)])
    if not (np.isfinite(e) and np.isfinite(p)) or p <= 0:
        return None
    return (e / p - 1) * 100.0


def market_breadth(close_matrix: pd.DataFrame, window: int = BREADTH_WINDOW) -> float | None:
    """Fraction of stocks with close > their own `window`-day MA (NaN-safe)."""
    if close_matrix is None or close_matrix.empty or len(close_matrix.columns) == 0:
        return None
    above = 0
    valid = 0
    for col in close_matrix.columns:
        s = close_matrix[col].astype(float).dropna()
        if len(s) < window + 1:
            continue
        ma = s.rolling(window).mean().iloc[-1]
        c = s.iloc[-1]
        if np.isfinite(ma) and np.isfinite(c):
            valid += 1
            above += 1 if c > ma else 0
    return (above / valid) if valid else None


def market_regime(close_matrix: pd.DataFrame, bench: pd.Series | None = None,
                  trend_window: int = TREND_WINDOW,
                  breadth_window: int = BREADTH_WINDOW) -> dict[str, Any]:
    """Classify the whole market into RISK_ON / NEUTRAL / RISK_OFF.

    Returns (always a dict, never raises):
      regime, trend_pct, breadth, vol_index, n_stocks
    """
    empty = {"regime": "NEUTRAL", "trend_pct": None, "breadth": None,
             "vol_index": None, "n_stocks": 0}
    if close_matrix is None or close_matrix.empty or len(close_matrix.columns) == 0:
        return empty

    rets: list[float] = []
    for col in close_matrix.columns:
        s = close_matrix[col].astype(float).dropna()
        r = _robust_ret(s, trend_window)
        if r is not None:
            rets.append(r)
    trend_pct = round(float(np.median(rets)), 2) if rets else None
    rets = [r for r in rets if r is None or np.isfinite(r)]

    breadth = market_breadth(close_matrix, breadth_window)

    # cross-sectional volatility (mean daily |return| over the last 5 bars)
    vols: list[float] = []
    for col in close_matrix.columns:
        s = close_matrix[col].astype(float).dropna()
        if len(s) < 6:
            continue
        rr = s.pct_change().dropna().iloc[-5:]
        if len(rr) > 0:
            vols.append(float(np.nanmean(np.abs(rr.values))))
    vol_index = round(float(np.nanmean(vols)) * 100.0, 2) if vols else None

    regime = "NEUTRAL"
    if trend_pct is not None:
        if (trend_pct >= RISK_ON_TREND and breadth is not None
                and breadth >= RISK_ON_BREADTH):
            regime = "RISK_ON"
        elif trend_pct <= RISK_OFF_TREND or (breadth is not None and breadth < RISK_OFF_BREADTH):
            regime = "RISK_OFF"
        # else NEUTRAL (momentum up but breadth weak, or flat)
    if bench is not None and trend_pct is None:
        b = bench.astype(float).dropna()
        r = _robust_ret(b, trend_window)
        if r is not None:
            trend_pct = round(r, 2)
            if breadth is not None and breadth >= RISK_ON_BREADTH:
                if trend_pct >= RISK_ON_TREND:
                    regime = "RISK_ON"
                elif trend_pct <= RISK_OFF_TREND:
                    regime = "RISK_OFF"
            elif breadth is not None and breadth < RISK_OFF_BREADTH:
                regime = "RISK_OFF"

    return {"regime": regime, "trend_pct": trend_pct, "breadth": breadth,
            "vol_index": vol_index, "n_stocks": len(close_matrix.columns)}
