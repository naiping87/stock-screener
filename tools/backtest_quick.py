"""Quick Phase-1 edge preview on a representative sample (faster than full).

Full command for the whole market:  python tools/backtest_phase1.py
This samples ~every 4th Bursa ticker so you can see the edge table quickly.
RS rank is computed within the sample, so treat numbers as indicative.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from screener import load_tickers, TICKERS_FILE
from tools.backtest_phase1 import run_backtest


def main() -> None:
    tickers = load_tickers(TICKERS_FILE)
    keys = sorted(tickers.keys())[::4]          # ~every 4th -> ~250 tickers
    sub = {k: tickers[k] for k in keys}
    print(f"sample {len(sub)} / {len(tickers)} tickers")
    summary, _ = run_backtest(sub, start="2021-01-01")
    pd.set_option("display.width", 200)
    if summary.empty:
        print("No data (check network / start date).")
        return
    print("\n=== Ignition edge: avg forward return / win-rate per classification ===")
    print(summary.to_string(index=False))
    print("\nNote: RS rank is cross-sectional within this sample; full-market cmd:")
    print("  python tools/backtest_phase1.py")


if __name__ == "__main__":
    main()
