"""
Bursa Scoring System — benchmark-grade backtest (v2).

Fixes the measurement problems of the in-app backtest:
  1. survivorship bias   — benchmark (equal-weight whole market) and the
                           random-20 group are built from the SAME universe
                           at the SAME dates as Top-20, so the *relative*
                           comparison is fair even though delisted names are
                           absent from the ticker list (documented limit).
  2. zero-cost assumption — Bursa cost model: commission + stamp duty +
                           clearing fee + slippage per rebalance round trip.
  3. no benchmark         — three groups: Top-20 (score), Random-20
                           (100 seeds), Market (equal-weight universe).
  4. no equity curve      — full portfolio NAV series + drawdown + ann. ret.

Output: per-rebalance CSVs + summary JSON + portfolio NAV CSVs.

Run:  python tools/backtest_v2.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Any

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

# ── Configuration ────────────────────────────────────────────────────────────
START_DATE = "2020-01-01"
END_DATE: str | None = None          # None = today
TOP_N = 20
REBALANCE_WEEKS = 2
RANDOM_SEEDS = 100
MIN_BARS_BEFORE = 250                 # bars required to be scoreable at a date
# Bursa cost model (retail-ish, per side):
COMMISSION_RATE = 0.0042              # 0.42% commission
STAMP_DUTY_RATE = 0.001               # 0.1% stamp duty (buy side only)
CLEARING_RATE = 0.0003                # 0.03% clearing fee
SLIPPAGE = 0.005                      # 0.5% slippage per side
BURN_IN_DAYS = 400                    # warm-up days before first rebalance

ROUND_TRIP_COST = (COMMISSION_RATE * 2 + STAMP_DUTY_RATE + CLEARING_RATE * 2 + SLIPPAGE * 2)
TURNOVER_PER_REBALANCE = 1.0          # assumed full turnover of the 20 names

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
STAMP = datetime.now().strftime("%Y%m%d-%H%M")


def fetch_universe(tickers: dict[str, str], start: str, end: str | None,
                   min_bars: int = 20, max_workers: int = 3) -> dict[str, dict[str, Any]]:
    """Download daily history for the whole ticker list (threaded)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    end_dt = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    p1, p2 = int(start_dt.timestamp()), int(end_dt.timestamp())
    sess = _build_session()
    ticker_list = sorted(tickers.keys())
    data: dict[str, dict[str, Any]] = {}
    errors = 0

    def fetch(tkr: str):
        time.sleep(0.25)  # throttle: Yahoo 429s concurrent bursts of the chart API
        d, name = _fetch_chart(sess, tkr, p1, p2, "1d", min_bars)
        return tkr, d, name

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(fetch, t) for t in ticker_list]
        for fut in as_completed(futures):
            tkr, d, name = fut.result()
            done += 1
            if d is None:
                errors += 1
            else:
                data[tkr] = {**d, "name": name or tickers.get(tkr, "")}
            if done % 200 == 0:
                print(f"  fetched {done}/{len(ticker_list)} ({errors} missing) "
                      f"{time.time()-t0:.0f}s", flush=True)
    print(f"  done: {len(data)}/{len(ticker_list)} tickers, {errors} missing, "
          f"{time.time()-t0:.0f}s", flush=True)
    return data


def score_at_date(data: dict[str, dict[str, Any]], date: pd.Timestamp,
                  max_keep: int, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Score all stocks using ONLY data up to `date` (no lookahead)."""
    snap: dict[str, dict[str, Any]] = {}
    for tkr, d in data.items():
        close = d["close"]
        loc = close.index.searchsorted(date, side="right") - 1
        if loc < MIN_BARS_BEFORE - 1:
            continue
        if loc < 0:
            continue
        snap[tkr] = {
            "close": close.iloc[: loc + 1],
            "high": d["high"].iloc[: loc + 1],
            "low": d["low"].iloc[: loc + 1],
            "volume": d["volume"].iloc[: loc + 1] if d.get("volume") is not None else None,
            "name": d.get("name", ""),
        }
    if len(snap) < 30:
        return []
    return run_scoring_screener(snap, top_n=max_keep, **params)


def main() -> None:
    params: dict[str, Any] = {
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
    print(f"[1/4] Downloading Bursa universe ({len(tickers)} tickers, "
          f"{START_DATE} -> {END_DATE or 'today'}) ...", flush=True)
    data = fetch_universe(tickers, START_DATE, END_DATE, min_bars=20)
    if len(data) < 100:
        print(f"FATAL: only {len(data)} tickers fetched; aborting")
        sys.exit(1)

    all_idx = pd.DatetimeIndex(sorted(set().union(*[set(d["close"].index) for d in data.values()])))
    if len(all_idx) < BURN_IN_DAYS + 200:
        print(f"FATAL: too few union dates ({len(all_idx)})")
        sys.exit(1)

    test_dates = list(all_idx[BURN_IN_DAYS: len(all_idx) - 22: interval_days])
    print(f"[2/4] {len(test_dates)} rebalance dates: {test_dates[0].date()} "
          f"-> {test_dates[-1].date()}", flush=True)

    rows_top: list[dict[str, Any]] = []
    rows_rand: list[dict[str, Any]] = []
    rows_mkt: list[dict[str, Any]] = []

    nav_top = 1.0
    nav_rand = 1.0
    nav_mkt = 1.0
    nav_series: dict[str, list[dict[str, Any]]] = {"top": [], "random": [], "market": []}
    prev_top: list[str] = []

    rng = np.random.default_rng(2020)
    print(f"[3/4] Backtesting (seeds={RANDOM_SEEDS}) ...", flush=True)
    t0 = time.time()

    for i, date in enumerate(test_dates):
        scored = score_at_date(data, date, max_keep=400, params=params)
        if not scored:
            continue
        n_scoreable = len(scored)

        def fwd_rets(ticker: str, horizon: int) -> float | None:
            close = data[ticker]["close"]
            loc = close.index.searchsorted(date, side="right") - 1
            if loc < 0 or loc + horizon >= len(close):
                return None
            entry = float(close.iloc[loc])
            # Yahoo Bursa series carry internal NaN gaps (suspension / data
            # holes): an entry or exit of NaN would poison the group mean and
            # cascade the whole NAV series to NaN. Drop the pair, don't retry.
            exit_px = float(close.iloc[loc + horizon])
            if not np.isfinite(entry) or not np.isfinite(exit_px) or entry <= 0:
                return None
            return exit_px / entry - 1

        # (a) Top-20 group
        top_names = [r["ticker"] for r in scored[:TOP_N]]
        fwd_t = {h: [] for h in (5, 10, 20)}
        for tkr in top_names:
            for h in fwd_t:
                r = fwd_rets(tkr, h)
                if r is not None:
                    fwd_t[h].append(r * 100)
        rows_top.append({
            "date": date.strftime("%Y-%m-%d"),
            "top_tickers": ", ".join(n.replace(".KL", "") for n in top_names[:5]),
            "avg_1w": round(float(np.mean(fwd_t[5])), 2) if fwd_t[5] else 0,
            "avg_2w": round(float(np.mean(fwd_t[10])), 2) if fwd_t[10] else 0,
            "avg_4w": round(float(np.mean(fwd_t[20])), 2) if fwd_t[20] else 0,
            "win_1w": round(sum(1 for v in fwd_t[5] if v > 0) / len(fwd_t[5]) * 100, 1) if fwd_t[5] else 0,
            "win_2w": round(sum(1 for v in fwd_t[10] if v > 0) / len(fwd_t[10]) * 100, 1) if fwd_t[10] else 0,
            "win_4w": round(sum(1 for v in fwd_t[20] if v > 0) / len(fwd_t[20]) * 100, 1) if fwd_t[20] else 0,
        })
        # NAV: hold the top-20 names for the period, then rebalance. Cost is
        # charged only on the names that actually turn over (compare with the
        # previous holding list), not a flat 100% turnover every period.
        per_period_top = fwd_t[10] if fwd_t[10] else fwd_t[5]
        if per_period_top:
            turnover = 1.0
            if prev_top:
                kept = sum(1 for t in top_names if t in prev_top)
                turnover = max(0.05, (len(top_names) - kept) / max(1, len(top_names)))
            prev_top = top_names
            gross_period = float(np.mean(per_period_top)) / 100.0
            cost = turnover * ROUND_TRIP_COST
            next_val = nav_top * (1.0 + gross_period - cost)
            if np.isfinite(next_val) and next_val > 0:
                nav_top = next_val
                nav_series["top"].append({"date": date.strftime("%Y-%m-%d"),
                                          "nav": round(nav_top, 4),
                                          "gross": round(gross_period * 100, 2),
                                          "cost": round(-cost * 100, 2),
                                          "turnover": round(turnover, 3)})

        # (b) Random-20 group (same universe, 100 seeds)
        fwd_r = {h: [] for h in (5, 10, 20)}
        for seed in range(RANDOM_SEEDS):
            pick = rng.choice(n_scoreable, size=min(TOP_N, n_scoreable), replace=False)
            for idx in pick:
                tkr = scored[idx]["ticker"]
                for h in fwd_r:
                    r = fwd_rets(tkr, h)
                    if r is not None:
                        fwd_r[h].append(r * 100)
        rows_rand.append({
            "date": date.strftime("%Y-%m-%d"),
            "avg_1w": round(float(np.mean(fwd_r[5])), 2) if fwd_r[5] else 0,
            "avg_2w": round(float(np.mean(fwd_r[10])), 2) if fwd_r[10] else 0,
            "avg_4w": round(float(np.mean(fwd_r[20])), 2) if fwd_r[20] else 0,
            "win_1w": round(sum(1 for v in fwd_r[5] if v > 0) / len(fwd_r[5]) * 100, 1) if fwd_r[5] else 0,
            "win_2w": round(sum(1 for v in fwd_r[10] if v > 0) / len(fwd_r[10]) * 100, 1) if fwd_r[10] else 0,
            "win_4w": round(sum(1 for v in fwd_r[20] if v > 0) / len(fwd_r[20]) * 100, 1) if fwd_r[20] else 0,
        })
        per_period_rand = fwd_r[10] if fwd_r[10] else fwd_r[5]
        if per_period_rand:
            gross_period = float(np.mean(per_period_rand)) / 100.0
            cost = ROUND_TRIP_COST  # random20 = full turnover proxy
            next_val = nav_rand * (1.0 + gross_period - cost)
            if np.isfinite(next_val) and next_val > 0:
                nav_rand = next_val
                nav_series["random"].append({"date": date.strftime("%Y-%m-%d"),
                                             "nav": round(nav_rand, 4),
                                             "gross": round(gross_period * 100, 2),
                                             "cost": round(-cost * 100, 2),
                                             "turnover": 1.0})

        # (c) Market equal-weight benchmark (any stock with enough history
        # AND valid data around this date — NaN-gapped series are skipped)
        market_universe = []
        for tkr, d in data.items():
            close = d["close"]
            loc = close.index.searchsorted(date, side="right") - 1
            if loc < MIN_BARS_BEFORE - 1 or loc < 0:
                continue
            slice_ = close.iloc[max(0, loc - 5): loc + 21]
            if slice_.isna().any():
                continue
            market_universe.append(tkr)
        fwd_m = {h: [] for h in (5, 10, 20)}
        for tkr in market_universe:
            for h in fwd_m:
                r = fwd_rets(tkr, h)
                if r is not None:
                    fwd_m[h].append(r * 100)
        rows_mkt.append({
            "date": date.strftime("%Y-%m-%d"),
            "avg_1w": round(float(np.mean(fwd_m[5])), 2) if fwd_m[5] else 0,
            "avg_2w": round(float(np.mean(fwd_m[10])), 2) if fwd_m[10] else 0,
            "avg_4w": round(float(np.mean(fwd_m[20])), 2) if fwd_m[20] else 0,
            "win_1w": round(sum(1 for v in fwd_m[5] if v > 0) / len(fwd_m[5]) * 100, 1) if fwd_m[5] else 0,
            "win_2w": round(sum(1 for v in fwd_m[10] if v > 0) / len(fwd_m[10]) * 100, 1) if fwd_m[10] else 0,
            "win_4w": round(sum(1 for v in fwd_m[20] if v > 0) / len(fwd_m[20]) * 100, 1) if fwd_m[20] else 0,
        })
        per_period_mkt = fwd_m[10] if fwd_m[10] else fwd_m[5]
        if per_period_mkt:
            gross_period = float(np.mean(per_period_mkt)) / 100.0
            if np.isfinite(gross_period):
                cost = ROUND_TRIP_COST
                next_val = nav_mkt * (1.0 + gross_period - cost)
                if np.isfinite(next_val) and next_val > 0:
                    nav_mkt = next_val
                    nav_series["market"].append({"date": date.strftime("%Y-%m-%d"),
                                                 "nav": round(nav_mkt, 4),
                                                 "gross": round(gross_period * 100, 2),
                                                 "cost": round(-cost * 100, 2),
                                                 "turnover": 1.0})

        if i % 25 == 0:
            print(f"  {date.date()} (#{i}) top={[t.replace('.KL','') for t in top_names[:3]]} "
                  f"elapsed={time.time()-t0:.0f}s", flush=True)

    # ── Summary ─────────────────────────────────────────────────────────────
    def summarize(rows: list[dict[str, Any]], label: str, nav_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"group": label, "n_dates": 0}
        df = pd.DataFrame(rows)
        nav_df = pd.DataFrame(nav_rows)
        ann_simple = float(df["avg_4w"].mean()) / 100.0 * (52 / REBALANCE_WEEKS) * 100
        result = {
            "group": label,
            "n_dates": len(rows),
            "avg_1w_pct": round(float(df["avg_1w"].mean()), 3),
            "avg_2w_pct": round(float(df["avg_2w"].mean()), 3),
            "avg_4w_pct": round(float(df["avg_4w"].mean()), 3),
            "win_1w_pct": round(float(df["win_1w"].mean()), 1),
            "win_2w_pct": round(float(df["win_2w"].mean()), 1),
            "win_4w_pct": round(float(df["win_4w"].mean()), 1),
            "simple_annual_pct": round(ann_simple, 2),
            "nav_final": round(float(nav_df["nav"].iloc[-1]), 4) if len(nav_df) else None,
            "nav_annual_pct": round((float(nav_df["nav"].iloc[-1]) ** (52 / len(nav_df) / REBALANCE_WEEKS) - 1) * 100, 2)
            if len(nav_df) > 0 else None,
        }
        # max drawdown on NAV
        if len(nav_df):
            peak = np.maximum.accumulate(nav_df["nav"].values)
            dd = (nav_df["nav"].values - peak) / peak
            result["max_drawdown_pct"] = round(float(dd.min()) * 100, 2)
        return result

    summary = [
        summarize(rows_top, "Top20", nav_series["top"]),
        summarize(rows_rand, "Random20", nav_series["random"]),
        summarize(rows_mkt, "MarketEW", nav_series["market"]),
    ]

    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, f"backtest_v2_{STAMP}")
    for label, rows, nav_rows in (("top20", rows_top, nav_series["top"]),
                                  ("random20", rows_rand, nav_series["random"]),
                                  ("market", rows_mkt, nav_series["market"])):
        if rows:
            pd.DataFrame(rows).to_csv(f"{base}_{label}.csv", index=False, encoding="utf-8-sig")
        if nav_rows:
            pd.DataFrame(nav_rows).to_csv(f"{base}_{label}_nav.csv", index=False, encoding="utf-8-sig")
    with open(f"{base}_summary.json", "w", encoding="utf-8") as f:
        json.dump({"config": {
            "start": START_DATE, "end": END_DATE or "today",
            "top_n": TOP_N, "interval_weeks": REBALANCE_WEEKS, "seeds": RANDOM_SEEDS,
            "min_bars_before": MIN_BARS_BEFORE,
            "round_trip_cost_pct": round(ROUND_TRIP_COST * 100, 3),
            "turnover_per_rebalance": TURNOVER_PER_REBALANCE,
            "cost_model": {"commission_pct": COMMISSION_RATE * 100,
                           "stamp_duty_pct": STAMP_DUTY_RATE * 100,
                           "clearing_pct": CLEARING_RATE * 100,
                           "slippage_pct": SLIPPAGE * 100}},
            "summary": summary}, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 88)
    print(f"SCORING BACKTEST v2 | Bursa | {START_DATE} -> {END_DATE or 'today'} | "
          f"Top{TOP_N} vs Random{TOP_N}({RANDOM_SEEDS} seeds) vs Market-EW | "
          f"rebalance {REBALANCE_WEEKS}w | round-trip cost {ROUND_TRIP_COST*100:.2f}%")
    print("=" * 88)
    hdr = f"{'group':<12}{'dates':>6}{'avg1w':>8}{'avg2w':>8}{'avg4w':>8}{'win4w':>8}{'ann%':>8}{'NAV':>8}{'dd%':>7}"
    print(hdr)
    for s in summary:
        print(f"{s['group']:<12}{s['n_dates']:>6}{s.get('avg_1w_pct',0):>8}"
              f"{s.get('avg_2w_pct',0):>8}{s.get('avg_4w_pct',0):>8}"
              f"{s.get('win_4w_pct',0):>8}{s.get('simple_annual_pct',0):>8}"
              f"{s.get('nav_final','—'):>8}{s.get('max_drawdown_pct',0):>7}")
    print(f"\noutputs: {base}_*.csv + _summary.json")


if __name__ == "__main__":
    main()
