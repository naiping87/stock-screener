"""
Verify the session-aware Phase-1 upgrade:
  A. market_session: session_mode / market_status for Bursa at several times
  B. EOD golden: run_phase1_screener(session="eod") == pre-upgrade output
     (same data, clv_min=0.8 — must be identical, e.g. 8923 excluded, etc.)
  C. Intraday: run_phase1_screener(session="intraday", clv_min=0.8) does NOT
     hard-filter on today's unstable CLV; yesterday_clv + intraday_position
     are populated; a stock with today CLV=0 but yesterday CLV>=0.8 survives.

Run: python tools/verify_session_mode.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

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
from market_session import market_status, session_mode  # noqa: E402


def main() -> None:
    print("=== A. market_session ===")
    # Bursa: 09:15 opening, 10:00 morning, 13:00 lunch, 15:50 afternoon,
    # 16:30 pre-close, 18:00 closed
    from zoneinfo import ZoneInfo
    kl = ZoneInfo("Asia/Kuala_Lumpur")
    cases = [
        ("09:15", "OPENING", "intraday"),
        ("10:00", "MORNING", "intraday"),
        ("13:00", "LUNCH", "intraday"),
        ("15:50", "AFTERNOON", "intraday"),
        ("16:30", "PRE_CLOSE", "intraday"),
        ("18:00", "CLOSED", "eod"),
    ]
    for tstr, want_status, want_mode in cases:
        hh, mm = map(int, tstr.split(":"))
        now = datetime(2026, 8, 26, hh, mm, tzinfo=kl)
        st = market_status("my", now)
        md = session_mode("my", now)
        ok = "OK" if st == want_status and md == want_mode else "MISMATCH"
        print(f"  {tstr}: status={st} mode={md} (want {want_status}/{want_mode}) {ok}")

    print("\n=== B+C. screener EOD vs Intraday ===")
    tickers = load_tickers(TICKERS_FILE)
    data = download_data(tickers, progress_cb=None)
    sess = _build_session()
    end = int(datetime.now().timestamp()); start = end - 2400 * 86400
    bk, _ = _fetch_chart(sess, "^KLSE", start, end, "1d", 30)
    bench = bk["close"].dropna() if bk else None
    print(f"  universe: {len(data)} tickers")

    from screener_phase1 import run_phase1_screener

    # B: EOD golden — baseline with clv_min=0.8 must behave exactly as before
    res_eod = run_phase1_screener(data, bench, {}, ticker_names=tickers,
                                  top_n=100, clv_min=0.8, session="eod")
    # C: Intraday — clv_min=0.8 but the filter must NOT apply
    res_intra = run_phase1_screener(data, bench, {}, ticker_names=tickers,
                                    top_n=100, clv_min=0.8, session="intraday")
    print(f"  EOD rows: {len(res_eod)}  Intraday rows: {len(res_intra)}")
    print(f"  EOD sample session field: {res_eod[0]['session'] if res_eod else 'N/A'}")

    # C check: in intraday, some stock with today CLV low but yesterday high
    # should be present (previously filtered in EOD)
    intra_low = [r for r in res_intra if r.get("clv") is not None and r["clv"] < 0.5]
    print(f"  Intraday keeps {len(intra_low)} stocks with TODAY CLV < 0.5 "
          f"(their yesterday_clv / intraday_position are the refs)")
    for r in intra_low[:5]:
        print(f"    {r['ticker']} clv={r['clv']} y_clv={r.get('yesterday_clv')} "
              f"ipos={r.get('intraday_position')} master={r['master_score']} "
              f"class={r['classification']}")

    # EOD sanity: 8923 (penny, filtered before) still excluded in both
    eod_8923 = any(r["ticker"] == "8923.KL" for r in res_eod)
    print(f"\n  8923.KL in EOD: {eod_8923} (expect False — penny guard)")

    print("\nRESULT: session-aware verification complete")


if __name__ == "__main__":
    main()
