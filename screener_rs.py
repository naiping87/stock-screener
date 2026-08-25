"""
Relative Strength (RS) + Sector Strength engine for Stock Screener Pro.

Pure functions, no side effects. Everything is computed from already-loaded
price data + a sector map — no new network calls beyond the KLCI benchmark
(which is fetched once per run and passed in).

Design rules (per the audit):
  - RS ≠ RSI. RS is *relative performance vs a benchmark* (FBMKLCI by
    default, or vs the stock's own sector).
  - All lookbacks: 5 / 20 / 60 / 120 trading days.
  - RS Momentum = slope of the RS percentile over the last ~20 days
    (percentile ranks are cross-sectional at the SAME date, so no lookahead).
  - NaN-gapped series (Bursa data holes) are handled by dropping the pair,
    never by propagating NaN.
  - Stock vs benchmark returns are computed on ALIGNED (reindexed) dates.

Everything here is a pure calculation on pandas Series/DataFrames so the
existing screeners and tests are untouched.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

RS_LOOKBACKS = (5, 20, 60, 120)
MOMENTUM_WINDOW = 20          # days for RS-Momentum slope
SECTOR_LOOKBACKS = (5, 20, 60, 120)


def _tick_size(price: float) -> float | None:
    """Bursa tick ladder: the minimum price increment at `price`.

    RM0.005 (0.5 sen) for prices below RM0.20, RM0.01 above — per Bursa
    Malaysia's tick-size rules. US uses 0.01 universally; A-shares 0.01.
    Returns None for invalid prices (caller keeps the stock).
    """
    if not np.isfinite(price) or price <= 0:
        return None
    if price < 0.20:
        return 0.005
    return 0.01


def _aligned(close: pd.Series, bench: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Align two price series on their common index, dropping NaNs.

    NaN gaps on EITHER side make the pair unusable at that date; dropping
    them keeps the return windows computed on real prices only (Bursa data
    holes are common and must never poison an RS number).
    """
    c = close.astype(float).dropna()
    b = bench.astype(float).dropna()
    idx = c.index.intersection(b.index)
    if len(idx) == 0:
        return c, b  # caller decides (no common dates)
    return c.loc[idx], b.loc[idx]


def _pct_change(s: pd.Series, window: int) -> float | None:
    """Return the % change over `window` trading days, None when invalid.

    NaN gaps (Bursa data holes): use the last two VALID prices instead of
    positions — a stock suspended mid-window still yields a correct return
    from its most recent real prints.
    """
    v = s.astype(float).dropna()
    if len(v) < window + 1:
        return None
    e = float(v.iloc[-1])
    try:
        p = float(v.iloc[-(window + 1)])
    except IndexError:
        return None
    if not (np.isfinite(e) and np.isfinite(p)) or p <= 0:
        return None
    return (e / p - 1) * 100.0


def stock_rs(close: pd.Series, bench: pd.Series,
             lookbacks: tuple[int, ...] = RS_LOOKBACKS) -> dict[str, float | None]:
    """RS = stock % return minus benchmark % return over each lookback.

    Positive = beat the market over that window. Returns
    {f"rs_{d}d": float|None} for each d in lookbacks.
    """
    c, b = _aligned(close, bench)
    out: dict[str, float | None] = {}
    for d in lookbacks:
        rc = _pct_change(c, d)
        rb = _pct_change(b, d)
        out[f"rs_{d}d"] = None if (rc is None or rb is None) else round(rc - rb, 2)
    return out


def rs_percentile(df: pd.DataFrame, rs_col: str) -> pd.Series:
    """Cross-sectional percentile rank (0-100) of one RS column at the LAST date.

    `df` rows = stocks, `rs_col` = one of the rs_{d}d columns. NaN ranks stay
    NaN (the stock has no RS this date).
    """
    if rs_col not in df.columns:
        return pd.Series(dtype=float)
    return df[rs_col].rank(pct=True) * 100.0


def rs_momentum(df: pd.DataFrame, rs_col: str, window: int = MOMENTUM_WINDOW) -> pd.Series:
    """Momentum of RS percentile: slope of the last `window` days.

    Since we only have ONE snapshot of percentile (current), momentum is
    approximated as the trend of the raw RS return itself: the RS_5d minus
    the RS_5d measured `window` days ago (the return's own momentum), which
    is computable from price history alone and needs no repeat snapshots.
    """
    return df.get(f"{rs_col}_mom", pd.Series(dtype=float))


def compute_rs_momentum(close: pd.Series, bench: pd.Series, lookback: int = 5,
                        window: int = MOMENTUM_WINDOW) -> float | None:
    """RS momentum: is the stock's 5-day RS *improving*?

    rs_now_then = (stock/bench over days [-window-5, -window])
    rs_now      = (stock/bench over days [-5, 0])
    momentum    = rs_now - rs_then (in % return-difference units).
    Rising momentum = the stock is beating the market harder than it did
    `window` days ago — the Emerging Leader signature.
    """
    c, b = _aligned(close, bench)
    if len(c) < window + lookback + 3:
        return None
    # window
    s_then = _pct_change(c.iloc[: -window], lookback) if len(c) > window else None
    s_now = _pct_change(c, lookback)
    b_then = _pct_change(b.iloc[: -window], lookback) if len(b) > window else None
    b_now = _pct_change(b, lookback)
    if None in (s_then, s_now, b_then, b_now):
        return None
    then = (s_then - b_then)
    now = (s_now - b_now)
    return round(now - then, 2)


# ── Cross-sectional RS ranking (Leader / Emerging Leader axis) ──────────────

def _rank_snapshot(close_matrix: pd.DataFrame, bench_clean: pd.Series,
                   asof: pd.Timestamp, lookback: int) -> pd.Series:
    """Cross-sectional RS percentile (0-100) of EVERY stock at one date.

    rs_i = stock return over `lookback` days ending at `asof` MINUS benchmark
    return over the same window; then rank across stocks (percentile).
    Only data available at `asof` is used — no lookahead by construction.

    Returns Series {ticker: 0-100 rank}, NaN for stocks without data.
    """
    loc = close_matrix.index.searchsorted(asof, side="right") - 1
    if loc < lookback:
        return pd.Series(dtype=float)
    # Locate by DATES, not positions: each stock column starts at its own
    # listing date, so an iloc slice would grab pre-listing NaNs for young
    # stocks. Take the return from each column's own last two valid bars,
    # anchored at `asof` — with the lookback measured in the column's own
    # calendar.
    anchor = close_matrix.index[loc]
    out: dict[str, float] = {}
    for col in close_matrix.columns:
        s = close_matrix[col].loc[:anchor].astype(float).dropna()
        if len(s) < lookback + 1:
            continue
        e = float(s.iloc[-1])
        p = float(s.iloc[-(lookback + 1)])
        if not (np.isfinite(e) and np.isfinite(p)) or p <= 0:
            continue
        ret = (e / p - 1) * 100.0
        # Penny-stock guard (#8923): Bursa stocks below RM0.20 tick in RM0.005,
        # so a 10% daily "move" is ONE tick. Even multi-tick cumulative gains
        # on RM0.05 names are dominated by the tick grid and PNO (paper
        # quotes) rather than real demand — their RS rank is not comparable
        # to RM2+ names. Three guards:
        #   1. Hard floor: price < RM0.20 → excluded from the rank table.
        #   2. Tick-dominance: single tick >= half the return AND the return
        #      is tiny (<2%) — these are flat/1-tick names, no signal.
        #   3. Anything with real movement (>2% over 20d) stays regardless,
        #      since a multi-tick gain is a genuine move even at RM0.20+.
        if p < 0.20:
            continue
        tick = _tick_size(p)
        if tick is not None and abs(ret) < 2.0:
            tick_pct = (tick / p) * 100.0  # % move from one tick
            if tick_pct >= 0.5 * abs(ret):
                continue
        out[col] = ret
    if not out:
        return pd.Series(dtype=float)
    stock_rets = pd.Series(out)
    # Benchmark return over the same window (its own calendar, anchored).
    b = bench_clean.loc[:anchor].astype(float).dropna()
    if len(b) < lookback + 1:
        return pd.Series(dtype=float)
    b_ret = (float(b.iloc[-1]) / float(b.iloc[-(lookback + 1)]) - 1) * 100.0
    rs = stock_rets - b_ret
    return rs.rank(pct=True) * 100.0


def rs_rank_history(close_matrix: pd.DataFrame, bench: pd.Series,
                    lookback: int = 20,
                    history_days: tuple[int, ...] = (0, 20, 40, 60)) -> pd.DataFrame:
    """RS-rank snapshots at the last date and `history_days` before it.

    Returns DataFrame (ticker × columns):
      rs_rank          — percentile at the last date (0-100)
      rs_rank_m20/40/60 — percentile N trading days ago
      rs_rank_chg20     — rank change over the last 20 days (+ = getting stronger)
      rs_rank_chg60     — rank change over the last 60 days
    NaN ranks = stock had no data at that snapshot (handled downstream).
    """
    bench_clean = bench.astype(float).dropna()
    if close_matrix.empty or bench_clean.empty:
        return pd.DataFrame()
    last_loc = len(close_matrix) - 1
    cols: dict[str, pd.Series] = {}
    for h in history_days:
        if last_loc - h < lookback:
            continue
        asof = close_matrix.index[last_loc - h]
        cols[f"rs_rank_m{h}" if h else "rs_rank"] = _rank_snapshot(
            close_matrix, bench_clean, asof, lookback)
    df = pd.DataFrame(cols)
    for h in history_days:
        now_col = "rs_rank" if h == 0 else f"rs_rank_m{h}"
        chg_col = f"rs_rank_chg{h}"
        if now_col in df.columns and "rs_rank" in df.columns:
            df[chg_col] = df["rs_rank"] - df[now_col]
    return df


# ── Sector strength ─────────────────────────────────────────────────────────

def sector_performances(close_matrix: pd.DataFrame, sector_map: dict[str, str],
                        bench: pd.Series,
                        lookbacks: tuple[int, ...] = SECTOR_LOOKBACKS) -> pd.DataFrame:
    """Per-sector average % change over each lookback, and vs-benchmark.

    `close_matrix`: DataFrame (dates × tickers) of closes.
    `sector_map`:   {ticker: sector}.
    Returns DataFrame indexed by sector:
      perf_{d}d      — average stock % change over d days
      rel_{d}d       — average stock % change MINUS benchmark % change
      rel_score_{d}d — rank of rel (0-100, higher = stronger sector)
    """
    rows: list[dict[str, Any]] = []
    bench_rets: dict[int, float | None] = {}
    bench_clean = bench.astype(float).dropna()
    for d in lookbacks:
        bench_rets[d] = _pct_change(bench_clean, d)

    for sector, members in _group_by_sector(close_matrix, sector_map):
        if not members:
            continue
        sub = close_matrix[members]
        row: dict[str, Any] = {"sector": sector, "n_members": len(members)}
        for d in lookbacks:
            rets = [_pct_change(sub[c].astype(float), d) for c in sub.columns]
            rets = [r for r in rets if r is not None]
            avg = float(np.mean(rets)) if rets else np.nan
            row[f"perf_{d}d"] = round(avg, 2) if np.isfinite(avg) else None
            b = bench_rets.get(d)
            row[f"rel_{d}d"] = None if (b is None or not np.isfinite(avg)) else round(avg - b, 2)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Cross-sector percentile of rel_{d}d (0-100)
    for d in lookbacks:
        col = f"rel_{d}d"
        if col in df.columns:
            df[f"rel_score_{d}d"] = df[col].rank(pct=True) * 100.0
    return df


def sector_momentum(sector_df: pd.DataFrame, window: int = 4) -> pd.Series:
    """Sector momentum: 20d rel minus 60d rel (higher = sector is ACCELERATING
    relative to the market recently vs a quarter ago)."""
    if "rel_20d" not in sector_df.columns or "rel_60d" not in sector_df.columns:
        return pd.Series(dtype=float)
    a = sector_df["rel_20d"].astype(float)
    b = sector_df["rel_60d"].astype(float)
    out = (a - b)
    return out.round(2)


def sector_rank(close_matrix: pd.DataFrame, sector_map: dict[str, str],
                bench: pd.Series) -> pd.DataFrame:
    """One-line entry: sector table + momentum + combined strength score."""
    sf = sector_performances(close_matrix, sector_map, bench)
    if sf.empty:
        return sf
    sf["momentum"] = sector_momentum(sf)
    # Combined: 60% recent (20d) + 40% trend (60d) — always over composite
    # rel scores; momentum is carried separately, not folded in (kills the
    # 'accelerating sector' distinction).
    rel20 = sf.get("rel_score_20d", pd.Series(dtype=float))
    rel60 = sf.get("rel_score_60d", pd.Series(dtype=float))
    combined = rel20.fillna(50) * 0.6 + rel60.fillna(50) * 0.4
    sf["strength"] = combined.round(1)
    sf = sf.sort_values(["strength", "momentum"], ascending=[False, False]).reset_index(drop=True)
    return sf


def _group_by_sector(close_matrix: pd.DataFrame, sector_map: dict[str, str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    for tkr in close_matrix.columns:
        s = sector_map.get(tkr)
        if s:
            groups.setdefault(s, []).append(tkr)
    return [(s, members) for s, members in groups.items()]
