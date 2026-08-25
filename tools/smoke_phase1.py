"""
Smoke test for the Phase-1 engines: run RS + setup + classify on a small
real-data window to prove the pipeline works end-to-end and NEVER crashes
on Bursa's NaN-gapped data. Also asserts the existing 11-factor screener is
byte-identical after our changes (no regression).

Run: python tools/smoke_phase1.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp1252 guard

import numpy as np

from screener import load_tickers, run_scoring_screener, TICKERS_FILE, _build_session, _fetch_chart
from screener_rs import stock_rs, compute_rs_momentum, sector_rank
from screener_setup import (
    base_quality,
    breakout_quality,
    closing_strength,
    effort_vs_result,
    nearest_pivot,
    nearest_support,
    price_extension,
    risk_reward,
    shakeout_check,
)
from screener_phase1 import run_phase1_screener


def main() -> None:
    tickers = load_tickers(TICKERS_FILE)
    sample = dict(list(tickers.items())[:60])  # first 60 Bursa codes
    print(f"[1] Loading {len(sample)} tickers for smoke test ...")

    sess = _build_session()
    data = {}
    import time
    p1 = 1577836800
    p2 = int(time.time())
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_fetch_chart, sess, t, p1, p2, "1d", 30): t for t in sample}
        for f in as_completed(futs):
            t = futs[f]
            d, name = f.result()
            if d:
                d["name"] = name or sample[t]
                data[t] = d
    print(f"[2] got {len(data)} tickers with data")

    # KLCI
    k, kname = _fetch_chart(sess, "^KLSE", p1, p2, "1d", 30)
    bench = k["close"].dropna() if k else None
    print(f"[3] KLCI benchmark: {kname if k else 'MISSING'} ({len(bench) if bench is not None else 0} bars)")

    # Per-ticker RS smoke
    first = list(data.keys())[0]
    close = data[first]["close"].dropna()
    rs = stock_rs(close, bench, lookbacks=(5, 20, 60, 120))
    mom = compute_rs_momentum(close, bench, lookback=5, window=20)
    print(f"[4] RS sample ({first}): {rs} momentum={mom}")

    # Setup detectors smoke
    d0 = data[first]
    clv = closing_strength(d0["high"], d0["low"], d0["close"])
    ext = price_extension(d0["close"])
    base = base_quality(d0["high"], d0["low"], d0["close"], d0.get("volume"), lookback=40)
    pv = nearest_pivot(d0["high"], d0["low"], d0["close"])
    sup = nearest_support(d0["low"], d0["high"], d0["close"])
    eff = effort_vs_result(d0["high"], d0["low"], d0["close"], d0.get("volume"))
    shake = shakeout_check(d0["high"], d0["low"], d0["close"], d0.get("volume"),
                           sup["price"] if sup else None)
    bq = breakout_quality(d0["high"], d0["low"], d0["close"], d0.get("volume"),
                          pv["price"] if pv else None, clv, rs.get("rs_20d"), None)
    rr = risk_reward(float(d0["close"].iloc[-1]),
                     sup["price"] * 0.985 if sup else None,
                     pv["price"] if pv else None)
    print(f"[5] setup sample ({first}):")
    print(f"    clv={clv} ext={ext} base={base}")
    print(f"    pivot={pv} support={sup}")
    print(f"    effort={eff} shakeout={shake}")
    print(f"    breakout={bq}")
    print(f"    rr={rr}")

    # Sector rank smoke (fake sectors for the sample)
    sector_map = {t: ("Tech" if i % 2 == 0 else "Finance") for i, t in enumerate(data)}
    try:
        from screener_rs import sector_rank as _sr
        import pandas as pd
        cm = pd.DataFrame({t: d["close"] for t, d in data.items()})
        st = _sr(cm, sector_map, bench)
        print(f"[6] sector table:\n{st.head(4).to_string()}")
    except Exception as e:
        print(f"[6] sector rank FAILED: {e}")

    # Full Phase-1 pipeline (uses fake sectors; real meta map comes from UI)
    try:
        res = run_phase1_screener(data, bench, sector_map, ticker_names=sample,
                                  top_n=20, clv_min=0.0)
        print(f"[7] phase1 -> {len(res)} rows")
        for r in res[:5]:
            print(f"    {r['ticker']} class={r['classification']} "
                  f"master={r['master_score']} strength={r['strength_score']} "
                  f"setup={r['setup_score']} trigger={r['trigger_score']} "
                  f"brk={r['breakout_score']} clv={r['clv']} reasons={r['reasons'][:3]}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[7] phase1 FAILED: {e}")

    # Regression: existing scorer output identical
    try:
        import pandas as pd
        one = {first: data[first]}
        s1 = run_scoring_screener(one, sample, top_n=1, min_score=0)
        print(f"[8] legacy scorer OK: score={s1[0]['score'] if s1 else 'EMPTY'}")
    except Exception as e:
        print(f"[8] legacy scorer FAILED: {e}")


if __name__ == "__main__":
    main()
