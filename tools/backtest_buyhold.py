"""
Buy & Hold benchmarks for the Bursa scoring backtest (v2.1).

Answers: "if I just buy and hold, what would the curve look like?"
Compared on the SAME window as backtest_v2 (2021-08-19 -> 2026-07-09):

  A. BH-All (exact)      — equal-weight buy ALL stocks with enough history at
                           the first rebalance date, hold to the end. Zero cost
                           beyond the initial purchase.
  B. MarketEW zero-cost  — the market group's gross returns compounded with NO
                           rebalancing cost (approximates buy-hold-EW with
                           periodic re-weighting).
  C. Top20 staggered BH  — every 2 weeks, buy the scored Top-20 names and HOLD
                           them to the end (each batch enters once, never
                           traded again). Isolates SELECTION alpha from
                           REBALANCING cost.
  D. Index              — Yahoo ^KLSE (FTSE Bursa Malaysia KLCI), best-effort.

Run: python tools/backtest_buyhold.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import (  # noqa: E402
    _build_session,
    _fetch_chart,
    load_tickers,
    run_scoring_screener,
    TICKERS_FILE,
)

from backtest_v2 import (  # noqa: E402  (same dir)
    START_DATE,
    END_DATE,
    TOP_N,
    REBALANCE_WEEKS,
    MIN_BARS_BEFORE,
    BURN_IN_DAYS,
    ROUND_TRIP_COST,
    OUT_DIR,
    STAMP,
    fetch_universe,
    score_at_date,
)

INDEX_CANDIDATES = ["^KLSE", "^KLCI", "KLCI.KL", "KLSE.KL"]


def buy_hold_all(close_matrix: pd.DataFrame, start_dt: pd.Timestamp,
                 end_dt: pd.Timestamp, min_bars: int) -> tuple[float, dict]:
    """Equal-weight buy every stock with >= min_bars of history at start_dt,
    hold all to end_dt. Returns (nav, stats)."""
    avail = [c for c in close_matrix.columns
             if close_matrix[c].dropna().index[0] <= start_dt
             and len(close_matrix[c].dropna()) >= min_bars]
    if not avail:
        return 1.0, {"n": 0, "error": "no available stocks at start_dt"}
    sub = close_matrix[avail].loc[start_dt:end_dt]
    # Series of equal-weight portfolio value (NAV per share normalized at t0)
    v0 = sub.iloc[0].mean()
    vals = sub.mean(axis=1) / v0 if v0 > 0 else sub.mean(axis=1) / 1.0
    nav = float(vals.iloc[-1])
    ann = (nav ** (252 / max(1, len(vals))) - 1) * 100
    mdd = max_drawdown(vals.values)
    return nav, {"n": len(avail), "annual_pct": round(ann, 2),
                 "max_dd_pct": round(mdd, 2), "bars": len(vals)}


def max_drawdown(values: np.ndarray) -> float:
    peak = np.maximum.accumulate(values)
    dd = (values - peak) / peak
    return float(dd.min()) * 100


def main() -> None:
    params: dict = {
        "trend_periods": [10, 20, 50, 100, 200],
        "trend_threshold": 1.0,
        "ema200_slope_bars": 20,
        "vol_period": 60,
        "vol_threshold": 5.0,
        "vol_ma_bars": 5,
        "vol_ma_threshold": 1_000_000,
    }
    interval_days = REBALANCE_WEEKS * 5

    tickers = load_tickers(TICKERS_FILE)
    print(f"[1/4] Downloading Bursa universe ({len(tickers)} tickers) ...", flush=True)
    data = fetch_universe(tickers, START_DATE, END_DATE, min_bars=20)
    if len(data) < 100:
        print("FATAL: not enough data"); sys.exit(1)

    all_idx = pd.DatetimeIndex(sorted(set().union(*[set(d["close"].index) for d in data.values()])))
    test_dates = list(all_idx[BURN_IN_DAYS: len(all_idx) - 22: interval_days])
    if not test_dates:
        print("FATAL: no test dates"); sys.exit(1)
    start_dt, end_dt = test_dates[0], test_dates[-1]
    print(f"[2/4] Window: {start_dt.date()} -> {end_dt.date()}", flush=True)

    close_matrix = pd.DataFrame({tkr: d["close"] for tkr, d in data.items()})

    # ── A: exact buy & hold all ─────────────────────────────────────────────
    nav_a, stats_a = buy_hold_all(close_matrix, start_dt, end_dt, MIN_BARS_BEFORE)
    print(f"[3/4] A BH-All(exact): NAV={nav_a:.4f} ({stats_a})", flush=True)

    # ── D: index (best-effort) ──────────────────────────────────────────────
    sess = _build_session()
    idx_nav = None
    idx_name = None
    for code in INDEX_CANDIDATES:
        d, name = _fetch_chart(sess, code, int(datetime.strptime(START_DATE, "%Y-%m-%d").timestamp()),
                               int(datetime.now().timestamp()), "1d", 20)
        if d and len(d["close"]) > 100:
            s = d["close"].dropna()
            sub = s.loc[start_dt:end_dt]
            if len(sub) > 50:
                idx_nav = float(sub.iloc[-1] / sub.iloc[0])
                idx_name = f"{code} ({name or 'KLCI'})"
                break
    print(f"      D Index: {idx_name} NAV={idx_nav}" if idx_nav else
          "      D Index: unavailable", flush=True)

    # ── B: market EW, zero rebalancing cost (compound gross) ────────────────
    # Reuse market gross by recomputing once (fast: only the market group)
    nav_b = 1.0
    n_b = 0
    for date in test_dates:
        market_universe = []
        for tkr, d in data.items():
            close = d["close"]
            loc = close.index.searchsorted(date, side="right") - 1
            if loc < MIN_BARS_BEFORE - 1 or loc < 0:
                continue
            if close.iloc[max(0, loc - 5): loc + 21].isna().any():
                continue
            market_universe.append(tkr)
        rets: list[float] = []
        for tkr in market_universe:
            close = data[tkr]["close"]
            loc = close.index.searchsorted(date, side="right") - 1
            if loc + 10 < len(close):
                e, x = float(close.iloc[loc]), float(close.iloc[loc + 10])
                if np.isfinite(e) and np.isfinite(x) and e > 0:
                    rets.append(x / e - 1)
        if rets:
            nav_b *= 1.0 + float(np.mean(rets))
            n_b += 1
    print(f"      B MarketEW zero-cost: NAV={nav_b:.4f} ({n_b} periods)", flush=True)

    # ── C: Top20 staggered buy & hold ───────────────────────────────────────
    # Each rebalance date: buy the Top-20 (equal weight) and hold to end_dt.
    # The final portfolio is the average of every batch's buy-hold NAV.
    batch_navs: list[float] = []
    batch_rows: list[dict] = []
    for i, date in enumerate(test_dates):
        scored = score_at_date(data, date, max_keep=400, params=params)
        if not scored:
            continue
        top_names = [r["ticker"] for r in scored[:TOP_N]]
        vals: list[float] = []
        wins = 0
        for tkr in top_names:
            close = data[tkr]["close"]
            loc = close.index.searchsorted(date, side="right") - 1
            end_loc = close.index.searchsorted(end_dt, side="right") - 1
            if loc < 0 or end_loc <= loc or end_loc >= len(close):
                continue
            e, x = float(close.iloc[loc]), float(close.iloc[end_loc])
            if not (np.isfinite(e) and np.isfinite(x)) or e <= 0:
                continue
            vals.append(x / e)
            if x > e:
                wins += 1
        if vals:
            nav_batch = float(np.mean(vals))
            batch_navs.append(nav_batch)
            batch_rows.append({"date": date.strftime("%Y-%m-%d"),
                               "batch_nav": round(nav_batch, 4),
                               "win": round(wins / len(vals) * 100, 1)})
        if i % 25 == 0:
            print(f"      C progress {date.date()} (#{i})", flush=True)
    nav_c = float(np.mean(batch_navs)) if batch_navs else 1.0

    # ── Summaries ───────────────────────────────────────────────────────────
    def ann_of(nav: float, periods: int, per_year: float = 12) -> float | None:
        if nav <= 0 or periods <= 0:
            return None
        return round((nav ** (per_year / periods) - 1) * 100, 2)

    summary: dict[str, Any] = {
        "window": {"start": start_dt.strftime("%Y-%m-%d"), "end": end_dt.strftime("%Y-%m-%d")},
        "A_buyhold_all_exact": {"nav": round(nav_a, 4), **stats_a},
        "B_market_ew_zero_cost": {"nav": round(nav_b, 4), "n_periods": n_b,
                                  "ann_approx_pct": ann_of(nav_b, n_b)},
        "C_top20_staggered_bh": {"nav": round(nav_c, 4), "n_batches": len(batch_navs),
                                 "ann_approx_pct": ann_of(nav_c, len(batch_navs)),
                                 "avg_win_pct": round(float(np.mean([r["win"] for r in batch_rows])), 1)
                                 if batch_rows else None},
        "D_index": {"name": idx_name, "nav": round(idx_nav, 4) if idx_nav else None},
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"buyhold_{STAMP}")
    if batch_rows:
        pd.DataFrame(batch_rows).to_csv(f"{base}_top20_batches.csv", index=False, encoding="utf-8-sig")
    with open(f"{base}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 80)
    print("BUY & HOLD BENCHMARKS | Bursa | %s -> %s" % (start_dt.date(), end_dt.date()))
    print("=" * 80)
    for key, s in summary.items():
        if key == "window":
            continue
        print(f"{key}: {s}")
    print(f"\noutputs: {base}_top20_batches.csv + _summary.json")


if __name__ == "__main__":
    main()
