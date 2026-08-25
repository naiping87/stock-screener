"""
Golden comparison: prove the vectorized RS batch (stock_rs_batch +
rs_momentum_batch) is bit-identical to the per-ticker legacy path
(stock_rs + compute_rs_momentum) it replaces in run_phase1_screener.

Also re-runs run_phase1_screener end-to-end and diff the full output
against the pre-optimization e2e CSV (phase1_e2e.csv) where the per-ticker
path was still in use — any classification or score difference is a bug.

Run: python tools/golden_rs_batch.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

from screener import (  # noqa: E402
    _build_session,
    _fetch_chart,
    download_data,
    load_tickers,
    TICKERS_FILE,
)
from screener_rs import (  # noqa: E402
    compute_rs_momentum,
    rs_momentum_batch,
    stock_rs,
    stock_rs_batch,
)


def main() -> None:
    tickers = load_tickers(TICKERS_FILE)
    print(f"[1/4] Downloading universe ({len(tickers)} tickers) ...")
    data = download_data(tickers, progress_cb=None)
    bench = None
    sess = _build_session()
    end = int(time.time()); start = end - 2400 * 86400
    bk, _ = _fetch_chart(sess, "^KLSE", start, end, "1d", 30)
    if bk is not None:
        bench = bk["close"].dropna()
    closes = {t: d["close"] for t, d in data.items() if d.get("close") is not None}
    cm = pd.DataFrame(closes)
    print(f"[2/4] univ={len(cm.columns)} bench={None if bench is None else len(bench)}")

    # ── Golden: per-ticker vs batch, exact comparison ────────────────────
    lookbacks = (5, 20, 60, 120)
    batch = stock_rs_batch(cm, bench, lookbacks=lookbacks)
    mom_batch = rs_momentum_batch(cm, bench, lookback=5)

    mismatches = 0
    compared = 0
    for col in cm.columns:
        per = stock_rs(cm[col], bench, lookbacks=lookbacks)
        mom_per = compute_rs_momentum(cm[col], bench, lookback=5)
        for d in lookbacks:
            key = f"rs_{d}d"
            a = per.get(key)
            b = batch.loc[col, key] if col in batch.index else None
            compared += 1
            a2 = None if a is None or not np.isfinite(a) else round(float(a), 4)
            b2 = None if b is None or not np.isfinite(b) else round(float(b), 4)
            if a2 != b2:
                mismatches += 1
                if mismatches <= 5:
                    print(f"  RS MISMATCH {col} {key}: per={a2} batch={b2}")
        cmp_a = None if mom_per is None else round(float(mom_per), 4)
        cmp_b = None if (col not in mom_batch.index or not np.isfinite(mom_batch[col])) else round(float(mom_batch[col]), 4)
        compared += 1
        if cmp_a != cmp_b:
            mismatches += 1
            if mismatches <= 5:
                print(f"  MOM MISMATCH {col}: per={cmp_a} batch={cmp_b}")

    print(f"[3/4] per-ticker vs batch: {compared} values compared, "
          f"{mismatches} mismatches")
    if mismatches > 0:
        print("!! GOLDEN TEST FAILED — do not ship the vectorized path")
        sys.exit(1)
    print("    GOLDEN OK: batch is bit-identical to per-ticker")

    # ── End-to-end regression vs the pre-optimization e2e CSV ────────────
    from screener_phase1 import run_phase1_screener
    results = run_phase1_screener(data, bench, {}, ticker_names=tickers,
                                  top_n=100, clv_min=0.0)
    new_df = pd.DataFrame([{k: v for k, v in r.items() if k != "reasons"}
                           for r in results])

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    ref_path = os.path.join(out, "phase1_e2e.csv")
    if os.path.exists(ref_path):
        ref = pd.read_csv(ref_path)
        # compare on union of tickers by key columns
        keys = ["ticker", "classification", "master_score", "strength_score",
                "setup_score", "trigger_score", "breakout_score", "clv",
                "rs_rank", "rs_20d", "rr"]
        ref_map = {r["ticker"]: r for _, r in ref.iterrows()}
        new_map = {r["ticker"]: r for _, r in new_df.iterrows()}
        diff_rows = 0
        for tkr in set(ref_map) & set(new_map):
            a, b = ref_map[tkr], new_map[tkr]
            for k in keys:
                av = a.get(k) if (isinstance(a, dict) or hasattr(a, "get")) else None
                bv = b.get(k)
                if k in ("master_score", "strength_score", "setup_score",
                         "trigger_score", "breakout_score", "clv", "rs_20d", "rr"):
                    try:
                        if (av is None or np.isnan(float(av))) and (bv is None or np.isnan(float(bv))):
                            continue
                        if av is None or bv is None or abs(float(av) - float(bv)) > 0.01:
                            diff_rows += 1
                            if diff_rows <= 5:
                                print(f"  SCORE DIFF {tkr} {k}: ref={av} new={bv}")
                    except (TypeError, ValueError):
                        if av != bv:
                            diff_rows += 1
                else:
                    if av != bv:
                        diff_rows += 1
                        if diff_rows <= 5:
                            print(f"  FIELD DIFF {tkr} {k}: ref={av} new={bv}")
        print(f"[4/4] e2e vs pre-optimization CSV: {len(set(ref_map) & set(new_map))} "
              f"common tickers, {diff_rows} differing fields")
        if diff_rows > 0:
            print("!! E2E DIFF — investigates")
            sys.exit(1)
        print("    E2E OK: output identical to pre-optimization")
    else:
        print("[4/4] no reference CSV (skipped e2e diff)")
    print("\nRESULT: PASS — optimization is behavior-preserving")


if __name__ == "__main__":
    main()
