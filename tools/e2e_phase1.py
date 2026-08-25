"""
End-to-end Phase-1 verification over the FULL Bursa universe:
1. Download 1009 tickers (+ KLCI)
2. Fetch sector meta for the scored subset
3. Run the Phase-1 pulse detector
4. Print the classification summary + sanity assertions

Run: python tools/e2e_phase1.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

from screener import load_tickers, TICKERS_FILE, _build_session, _fetch_chart
from tools.backtest_v2 import fetch_universe


def main() -> None:
    tickers = load_tickers(TICKERS_FILE)
    print(f"[1/5] Full universe download ({len(tickers)} tickers) ...", flush=True)
    data = fetch_universe(tickers, "2020-01-01", None, min_bars=30)
    print(f"[2/5] {len(data)} tickers with data", flush=True)

    sess = _build_session()
    import time as _t
    end = int(_t.time()); start = end - 2400 * 86400
    bk, bname = _fetch_chart(sess, "^KLSE", start, end, "1d", 30)
    bench = bk["close"].dropna() if bk else None
    print(f"[3/5] KLCI: {bname} ({len(bench)} bars)", flush=True)

    # sector meta for scored subset (fake for e2e; real UI uses meta worker)
    print("[4/5] Running Phase-1 detector ...", flush=True)
    from screener_phase1 import run_phase1_screener
    sector_map = {}  # e2e uses no sector map; RS-vs-KLCI still works

    t0 = time.time()
    results = run_phase1_screener(data, bench, sector_map, ticker_names=tickers,
                                  top_n=200, clv_min=0.0)
    elapsed = time.time() - t0
    print(f"[5/5] Phase-1 done in {elapsed:.1f}s -> {len(results)} rows", flush=True)

    # ── Sanity assertions ─────────────────────────────────────────────────
    assert len(results) > 0, "no results"
    from collections import Counter
    classes = Counter(r["classification"] for r in results)
    print("\nClassification distribution:")
    for c, n in classes.most_common():
        print(f"  {c:<24} {n}")

    # Sanity: each row has master + sub-scores
    for r in results[:3]:
        print(f"  {r['ticker']} {r['classification']:<22} master={r['master_score']} "
              f"str={r['strength_score']} setup={r['setup_score']} trig={r['trigger_score']} "
              f"brk={r['breakout_score']} clv={r['clv']} pivot={r['pivot_price']} "
              f"dist={r['pivot_distance_pct']} rr={r['rr']}")

    # Top-5 TRIGGER WATCH / BREAKOUT (the "marketing" rows)
    shown = 0
    print("\nTop pulse rows (BREAKOUT/TRIGGER WATCH):")
    for r in results:
        if r["classification"] in ("BREAKOUT", "TRIGGER WATCH", "EXPANSION"):
            print(f"  {r['ticker']:<10} {r['classification']:<16} master={r['master_score']} "
                  f"pivot={r['pivot_price']} dist={r['pivot_distance_pct']}% rr={r['rr']} "
                  f"reasons={' | '.join(r['reasons'][:4])}")
            shown += 1
            if shown >= 10:
                break

    # CSV out for inspection
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(out, exist_ok=True)
    pd.DataFrame([{k: v for k, v in r.items() if k != "reasons"} for r in results]).to_csv(
        os.path.join(out, "phase1_e2e.csv"), index=False, encoding="utf-8-sig")
    print(f"\nsaved: output/phase1_e2e.csv")


if __name__ == "__main__":
    main()
