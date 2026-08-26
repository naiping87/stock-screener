"""Point-in-time backtest for the Phase-1 (Ignition) engine.

Unlike the in-app backtest (which only exercises the 11-factor score), this
measures the *early-stage* signals: RS rank, sector strength, setup, trigger,
breakout, EMA-reclaim and master_rr. It is causal / look-ahead safe:

  - Every rebalance date re-scores on data truncated to that date ONLY.
  - RS percentile, sector table, pivots, shakeouts, EMA-reclaim all read bars
    up to and including the snapshot date (the engine is causal by design).
  - Forward returns are measured from the snapshot's last close.

Reference the cost model in backtest_v2 for real-money NAV; this tool reports
raw forward-return + hit-rate per classification bucket so you can compare the
value of Buckets (e.g. does EMA RECLAIM beat SETUP? does BREAKOUT beat LEADER?).

Run:  python tools/backtest_phase1.py
"""
from __future__ import annotations

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
    TICKERS_FILE,
    DownloadCancelled,
)
from tools.backtest_v2 import fetch_universe  # noqa: E402

START_DATE = "2020-01-01"
END_DATE: str | None = None
REBALANCE_DAYS = 20            # ~monthly rebalance (trading days)
TOP_N = 20                     # top names by master_rr per rebalance
MIN_BARS_BEFORE = 250          # bars required to be scoreable at a date
FORWARD_HORIZONS = (5, 10, 20)  # trading days
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
STAMP = datetime.now().strftime("%Y%m%d-%H%M")


def _snap(data: dict[str, dict[str, Any]], asof: pd.Timestamp) -> dict[str, dict[str, Any]]:
    """Truncate every series to `asof` (inclusive) — no future data."""
    out: dict[str, dict[str, Any]] = {}
    for tkr, d in data.items():
        close = d.get("close")
        if close is None or len(close) < 30:
            continue
        loc = close.index.searchsorted(asof, side="right") - 1
        if loc < MIN_BARS_BEFORE:
            continue
        cut = close.index[loc]
        snap = {
            "close": close.loc[:cut],
            "high": d["high"].loc[:cut] if d.get("high") is not None else None,
            "low": d["low"].loc[:cut] if d.get("low") is not None else None,
            "volume": d["volume"].loc[:cut] if d.get("volume") is not None else None,
            "name": d.get("name", ""),
        }
        if snap["high"] is None or snap["low"] is None:
            continue
        out[tkr] = snap
    return out


def _forward_returns(data: dict[str, dict[str, Any]], tickers: list[str],
                     asof: pd.Timestamp) -> dict[str, dict[int, float | None]]:
    """Forward % return per ticker for each horizon from `asof`."""
    res: dict[str, dict[int, float | None]] = {}
    for tkr in tickers:
        close = data[tkr]["close"]
        try:
            loc = close.index.get_loc(asof)
        except (KeyError, TypeError):
            continue
        if isinstance(loc, (slice, np.ndarray)):
            continue
        ep = float(close.iloc[loc])
        if not np.isfinite(ep) or ep <= 0:
            continue
        per: dict[int, float | None] = {}
        for h in FORWARD_HORIZONS:
            j = loc + h
            if j < len(close):
                per[h] = round((float(close.iloc[j]) / ep - 1) * 100.0, 2)
            else:
                per[h] = None
        res[tkr] = per
    return res


def _fetch_bench(symbol: str = "^KLSE") -> pd.Series | None:
    try:
        sess = _build_session()
        end = int(time.time())
        start = end - 3600 * 86400
        d, _ = _fetch_chart(sess, symbol, start, end, "1d", 30)
        return d["close"].dropna() if d else None
    except Exception:
        return None


def run_backtest(tickers: dict[str, str], start: str = START_DATE,
                 end: str | None = None, top_n: int = TOP_N,
                 sector_map: dict[str, str] | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Run the Phase-1 point-in-time backtest. Returns (summary, per_date)."""
    data = fetch_universe(tickers, start, end, min_bars=min(30, MIN_BARS_BEFORE))
    if not data:
        return pd.DataFrame(), []
    bench = _fetch_bench()

    from screener_phase1 import run_phase1_screener

    # reference index (a stock with the longest history)
    ref = max((d["close"] for d in data.values() if d.get("close") is not None), key=len)
    dates = ref.index
    # candidate snapshot dates: from MIN_BARS_BEFORE onward, every REBALANCE_DAYS
    test_idx = list(range(MIN_BARS_BEFORE, len(dates) - max(FORWARD_HORIZONS), REBALANCE_DAYS))

    per_date: list[dict[str, Any]] = []
    bucket_rows: dict[str, dict[str, list]] = {}

    for i in test_idx:
        asof = dates[i]
        snap = _snap(data, asof)
        if len(snap) < top_n:
            continue
        try:
            rows = run_phase1_screener(
                snap, bench, sector_map or {}, ticker_names=tickers,
                top_n=top_n, clv_min=0.0,
            )
        except Exception:
            continue
        if not rows:
            continue
        top = rows[:top_n]
        fwd = _forward_returns(data, [r["ticker"] for r in top], asof)
        rebal: dict[str, Any] = {"date": asof.strftime("%Y-%m-%d")}
        for r in top:
            tkr = r["ticker"]
            cls = r.get("classification", "UNKNOWN")
            key = cls
            bucket_rows.setdefault(key, {h: [] for h in FORWARD_HORIZONS})
            for h in FORWARD_HORIZONS:
                fr = fwd.get(tkr, {}).get(h)
                if fr is not None:
                    bucket_rows[key][h].append(fr)
            # also log the top pick for the rebalance sheet
            rebal.setdefault("top", []).append({
                "code": tkr.replace(".KL", ""), "type": cls,
                "master_rr": r.get("master_rr"), "master": r.get("master_score"),
                "rs_rank": r.get("rs_rank"), "ema_reclaim": r.get("ema_reclaim"),
            })
        per_date.append(rebal)

    summary_rows: list[dict[str, Any]] = []
    for cls, by_h in bucket_rows.items():
        row: dict[str, Any] = {"classification": cls, "n": len(next(iter(by_h.values())) or [])}
        for h in FORWARD_HORIZONS:
            vals = by_h[h]
            row[f"avg_{h}d"] = round(float(np.mean(vals)), 2) if vals else None
            row[f"win_{h}d"] = (round(sum(1 for x in vals if x > 0) / len(vals) * 100, 1)
                                if vals else None)
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    sort_col = "avg_20d" if "avg_20d" in summary.columns else "avg_10d"
    if not summary.empty and sort_col in summary.columns:
        summary = summary.sort_values(sort_col, ascending=False).reset_index(drop=True)
    return summary, per_date


def main() -> None:
    print("=" * 64)
    print("  Phase-1 (Ignition) point-in-time backtest")
    print("=" * 64)
    tickers = load_tickers(TICKERS_FILE)
    print(f"[1/3] Universe: {len(tickers)} tickers")
    print("[2/3] Downloading + scoring (this is slow, ~minutes) ...")
    summary, per_date = run_backtest(tickers)
    print("[3/3] Summary (avg forward return / win rate per classification):")
    if summary.empty:
        print("  No data — check network / START_DATE.")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    summary.to_csv(os.path.join(OUT_DIR, f"phase1_backtest_summary_{STAMP}.csv"),
                   index=False, encoding="utf-8-sig")
    with open(os.path.join(OUT_DIR, f"phase1_backtest_rebalance_{STAMP}.json"),
              "w", encoding="utf-8") as f:
        import json
        json.dump(per_date, f, indent=2)
    pd.set_option("display.width", 200)
    print(summary.to_string(index=False))
    print(f"\nSaved -> {OUT_DIR}")


if __name__ == "__main__":
    main()
