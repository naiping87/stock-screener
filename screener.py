"""
Bursa Malaysia Stock Screener — two output modes:
  1. SMA Compression — hourly SMA coil + daily KDJ cross + trend + volume
  2. KDJ Divergence — daily price falling while KDJ rising (bullish divergence)
"""
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests

# ── Configuration ────────────────────────────────────────────────────────────
SMA_PERIODS = [20, 30, 50, 120, 200]
DIVERGENCE_THRESHOLD = 3.0          # percent
VOL_RATIO_THRESHOLD = 1.2           # 5h avg vol >= 1.2x 50h avg vol
MAX_WORKERS = 6                     # concurrent download threads
REQUEST_DELAY = 0.3                 # seconds between requests per thread
MAX_RETRIES = 3
MIN_COMPRESSION_BARS = 20           # SMAs must be tight for this many bars
KDJ_PERIOD = 9                      # KDJ lookback (same as Pine Script 'Period')
KDJ_SIGNAL = 3                      # KDJ smooth (same as Pine Script 'Signal Period')
KDJ_LOOKBACK = 3                    # bars to look back for golden cross
KDJ_OVERSOLD = 50                   # K must be below this for valid signal
KDJ_GAP_THRESHOLD = 2.0             # K-D gap for 'about to cross'
KDJ_DAILY_DAYS = 45                 # days of daily data to fetch (KDJ needs ~15, extra for buffer)
DAILY_TREND_SMA = 20                # daily close must be above this SMA (trend filter)
DIVERGENCE_LOOKBACK = 20            # bars for KDJ/price divergence detection
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TICKERS_FILE = os.path.join(SCRIPT_DIR, "tickers.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
# ──────────────────────────────────────────────────────────────────────────────


def load_tickers(path):
    """Read tickers.csv -> dict {ticker_symbol: company_name}."""
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found.")
        sys.exit(1)

    tickers = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            code = row[0].strip().upper()
            name = row[1].strip() if len(row) > 1 else code
            if code.isdigit() or code == "5235SS":
                tickers[f"{code}.KL"] = name
    print(f"[INFO] Loaded {len(tickers)} tickers")
    return tickers


def _build_session():
    """Create a requests Session with browser-like headers for Yahoo Finance."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    })
    try:
        sess.get("https://fc.yahoo.com/", timeout=10)
    except Exception:
        pass
    return sess


def _fetch_chart(sess, tkr, period1, period2, interval, min_bars):
    """Download chart data for one ticker. Returns (data_dict | None, meta_name)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tkr}"
    params = {
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "events": "history",
        "includePrePost": "false",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = sess.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                continue

            j = resp.json()
            chart_result = j.get("chart", {}).get("result", [])
            if not chart_result:
                return None, ""

            r = chart_result[0]
            ts = r.get("timestamp", [])
            quote = r.get("indicators", {}).get("quote", [{}])[0]
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])
            name = r.get("meta", {}).get("longName", "")

            if sum(1 for v in closes if v is not None) < min_bars:
                return None, name

            idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kuala_Lumpur")

            def _to_series(values, idx):
                return pd.Series(
                    [v if v is not None else float("nan") for v in values],
                    index=idx, dtype=float,
                )

            result = {
                "close": _to_series(closes, idx),
                "open": _to_series(opens, idx),
                "high": _to_series(highs, idx),
                "low": _to_series(lows, idx),
                "volume": _to_series(volumes, idx),
            }
            return result, name

        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    return None, ""


def _fetch_ticker(sess, tkr, hp1, hp2, dp1, dp2, min_bars_h, min_bars_d):
    """Download hourly + daily data for one ticker. Returns (tkr, data_dict | None)."""
    # Hourly data
    h_data, name = _fetch_chart(sess, tkr, hp1, hp2, "1h", min_bars_h)
    if h_data is None:
        return tkr, None

    # Daily data (for KDJ)
    d_data, d_name = _fetch_chart(sess, tkr, dp1, dp2, "1d", min_bars_d)
    name = name or d_name

    h_close = h_data["close"].dropna()
    h_vol = h_data["volume"].fillna(0)
    idx = h_close.index.intersection(h_vol.index)

    result = {
        "close": h_close.loc[idx],
        "volume": h_vol.loc[idx],
        "name": name,
    }

    if d_data is not None:
        d_close = d_data["close"].dropna()
        d_high = d_data["high"].dropna()
        d_low = d_data["low"].dropna()
        di = d_close.index.intersection(d_high.index).intersection(d_low.index)
        result["daily_close"] = d_close.loc[di]
        result["daily_high"] = d_high.loc[di]
        result["daily_low"] = d_low.loc[di]

    return tkr, result


def download_data(tickers):
    """Download 60d hourly + daily data concurrently via Yahoo chart API."""
    end_date = datetime.now()
    h_start = end_date - timedelta(days=60)
    d_start = end_date - timedelta(days=KDJ_DAILY_DAYS)
    hp1, hp2 = int(h_start.timestamp()), int(end_date.timestamp())
    dp1, dp2 = int(d_start.timestamp()), int(end_date.timestamp())
    min_bars_h = max(SMA_PERIODS)
    min_bars_d = KDJ_PERIOD + KDJ_SIGNAL + KDJ_LOOKBACK

    ticker_list = sorted(tickers.keys())
    all_data = {}
    session = _build_session()

    print(f"[DOWNLOAD] Fetching 60d hourly + {KDJ_DAILY_DAYS}d daily data "
          f"for {len(ticker_list)} tickers (workers={MAX_WORKERS}) ...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _fetch_ticker, session, tkr,
                hp1, hp2, dp1, dp2, min_bars_h, min_bars_d,
            ): tkr
            for tkr in ticker_list
        }
        done = 0
        for f in as_completed(futures):
            tkr, data = f.result()
            if data is not None:
                all_data[tkr] = data
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(ticker_list)} tickers processed ...")
            time.sleep(REQUEST_DELAY)

    print(f"[DATA] Got price history for {len(all_data)} / {len(tickers)} tickers")
    return all_data


def _calc_divergence(close_series, periods):
    """Return (divergence_pct, sma_dict) or (None, None)."""
    if len(close_series) < max(periods):
        return None, None
    sma = {}
    for p in periods:
        val = close_series.rolling(p).mean().iloc[-1]
        if pd.isna(val):
            return None, None
        sma[p] = val
    close = close_series.iloc[-1]
    vals = list(sma.values())
    return (max(vals) - min(vals)) / close * 100.0, sma


def _check_compression_duration(close_series, periods, threshold, min_bars):
    """Return True if SMA divergence stayed <= threshold for the last min_bars bars."""
    needed = max(periods) + min_bars
    if len(close_series) < needed:
        return False

    smas = {p: close_series.rolling(p).mean() for p in periods}
    for i in range(-min_bars, 0):
        vals = [smas[p].iloc[i] for p in periods]
        if any(pd.isna(v) for v in vals):
            return False
        div = (max(vals) - min(vals)) / close_series.iloc[i] * 100.0
        if div > threshold:
            return False
    return True


def _calc_kdj(daily_high, daily_low, daily_close, period=KDJ_PERIOD, signal=KDJ_SIGNAL):
    """Calculate KDJ (K, D, J) series from daily OHLC. Returns (k, d, j) or (None, None, None)."""
    needed = period + signal
    if daily_high is None or len(daily_close) < needed:
        return None, None, None

    lowest_low = daily_low.rolling(period).min()
    highest_high = daily_high.rolling(period).max()
    denom = highest_high - lowest_low
    rsv = 100.0 * (daily_close - lowest_low) / denom.replace(0, float("nan"))

    # Custom EMA: (1*src + (length-1)*prev) / length  →  alpha = 1/signal
    alpha = 1.0 / signal
    k = rsv.ewm(alpha=alpha, min_periods=signal, adjust=False).mean()
    d = k.ewm(alpha=alpha, min_periods=signal, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j


def _detect_kdj_signal(k, d, j, lookback=KDJ_LOOKBACK, oversold=KDJ_OVERSOLD,
                       gap_threshold=KDJ_GAP_THRESHOLD):
    """Detect KDJ golden cross (or near-cross).

    Returns (signal, k_val, d_val, j_val):
      signal: 'crossed' | 'near' | None
    """
    if k is None or len(k) < lookback + 2:
        return None, None, None, None

    k_now, d_now = k.iloc[-1], d.iloc[-1]
    j_now = j.iloc[-1] if j is not None else float("nan")

    # Check for recent golden cross (K crossed above D within lookback bars)
    for i in range(-lookback, 0):
        ki, ki1 = k.iloc[i], k.iloc[i - 1]
        di, di1 = d.iloc[i], d.iloc[i - 1]
        if ki > di and ki1 <= di1:
            # Confirm: crossover happened at oversold levels
            if ki < oversold:
                return "crossed", round(k_now, 1), round(d_now, 1), round(j_now, 1)

    # Check for "about to cross": K < D but gap is small, K rising, oversold zone
    if k_now < d_now:
        gap = d_now - k_now
        k_rising = k_now > k.iloc[-2]
        if gap < gap_threshold and k_rising and k_now < oversold:
            return "near", round(k_now, 1), round(d_now, 1), round(j_now, 1)

    return None, None, None, None


def _detect_divergence(daily_high, daily_low, daily_close,
                       lookback=DIVERGENCE_LOOKBACK, kdj_period=KDJ_PERIOD,
                       kdj_signal=KDJ_SIGNAL):
    """Detect bullish divergence: price downtrend + KDJ uptrend (daily, >= lookback bars).

    Returns (sig, k_val, d_val, j_val, price_slope, k_slope) or (None,)*6.
    """
    k, d, j = _calc_kdj(daily_high, daily_low, daily_close,
                        period=kdj_period, signal=kdj_signal)
    if k is None or len(k) < lookback:
        return None, None, None, None, None, None

    x = np.arange(lookback, dtype=float)

    price_slice = daily_close.iloc[-lookback:].values.astype(float)
    k_slice = k.iloc[-lookback:].values.astype(float)

    # Mask out NaN
    mask = ~np.isnan(price_slice) & ~np.isnan(k_slice)
    if mask.sum() < lookback // 2:
        return None, None, None, None, None, None

    price_slope = np.polyfit(x[mask], price_slice[mask], 1)[0]
    k_slope = np.polyfit(x[mask], k_slice[mask], 1)[0]

    # Bullish divergence: price falling, KDJ rising
    if price_slope < 0 and k_slope > 0:
        k_now = round(k.iloc[-1], 1)
        d_now = round(d.iloc[-1], 1)
        j_now = round(j.iloc[-1], 1)
        return "bullish_div", k_now, d_now, j_now, round(price_slope, 4), round(k_slope, 4)

    return None, None, None, None, None, None


def run_sma_screener(data, ticker_names=None, periods=SMA_PERIODS,
                     threshold=DIVERGENCE_THRESHOLD, vol_threshold=VOL_RATIO_THRESHOLD,
                     min_compression=MIN_COMPRESSION_BARS,
                     kdj_period=KDJ_PERIOD, kdj_signal=KDJ_SIGNAL,
                     kdj_lookback=KDJ_LOOKBACK, kdj_oversold=KDJ_OVERSOLD,
                     trend_sma=DAILY_TREND_SMA):
    """
    SMA Compression Screener:
      Stage 1 — Hourly SMA compression (divergence <= threshold% for >= min_compression bars)
      Stage 2 — Daily KDJ golden cross / near-cross in oversold zone
      Stage 3 — Daily trend: close > SMA (price not under water)
      Stage 4 — Volume surge: 5h avg >= vol_threshold * 50h avg
    """
    ticker_names = ticker_names or {}
    s1 = 0
    s1_duration = 0
    s2 = 0
    s3 = 0
    s4 = 0

    for tkr, d in data.items():
        div, sma = _calc_divergence(d["close"], periods)
        if div is None or div > threshold:
            continue
        s1 += 1

        if not _check_compression_duration(d["close"], periods, threshold, min_compression):
            continue
        s1_duration += 1

        # Stage 2 — Daily KDJ golden cross / near-cross
        k, d_d, j = _calc_kdj(
            d.get("daily_high"), d.get("daily_low"), d.get("daily_close"),
            period=kdj_period, signal=kdj_signal,
        )
        kdj_sig, k_val, d_val, j_val = _detect_kdj_signal(
            k, d_d, j, lookback=kdj_lookback, oversold=kdj_oversold,
        )
        if kdj_sig is None:
            continue
        s2 += 1

        # Stage 3 — Daily trend: close > trend_sma
        daily_close = d.get("daily_close")
        if daily_close is None or len(daily_close) < trend_sma:
            continue
        daily_sma_val = daily_close.rolling(trend_sma).mean().iloc[-1]
        if pd.isna(daily_sma_val) or daily_close.iloc[-1] <= daily_sma_val:
            continue
        s3 += 1

        # Stage 4 — Volume surge
        vol = d.get("volume", pd.Series(dtype=float))
        if len(vol) < 50:
            continue
        avg5 = vol.iloc[-5:].mean()
        avg50 = vol.iloc[-50:].mean()
        vr = round(avg5 / avg50, 2) if avg50 > 0 else 0.0
        if vr < vol_threshold:
            continue
        s4 += 1

        name = d.get("name", "") or ticker_names.get(tkr, "")
        yield {
            "ticker": tkr,
            "name": name,
            "close": round(d["close"].iloc[-1], 2),
            "MA20": round(sma[20], 2),
            "MA30": round(sma[30], 2),
            "MA50": round(sma[50], 2),
            "MA120": round(sma[120], 2),
            "MA200": round(sma[200], 2),
            "divergence_pct": round(div, 2),
            "kdj_signal": kdj_sig,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "daily_trend": round(daily_close.iloc[-1] / daily_sma_val - 1, 4),
            "vol_ratio": vr,
        }

    print(f"  Stage 1a (divergence <= {threshold}%):             {s1} passed")
    print(f"  Stage 1b (tight for >= {min_compression} bars):    {s1_duration} passed")
    print(f"  Stage 2  (daily KDJ golden cross / near):         {s2} passed")
    print(f"  Stage 3  (daily close > {trend_sma}SMA):              {s3} passed")
    print(f"  Stage 4  (vol ratio >= {vol_threshold}x):          {s4} passed")


def run_divergence_screener(data, ticker_names=None,
                            lookback=DIVERGENCE_LOOKBACK):
    """
    KDJ Divergence Screener:
      Detects bullish divergence — price falling while KDJ rising (daily, >= lookback bars).
    """
    ticker_names = ticker_names or {}
    passed = 0

    for tkr, d in data.items():
        sig, k_val, d_val, j_val, price_slope, k_slope = _detect_divergence(
            d.get("daily_high"), d.get("daily_low"), d.get("daily_close"),
            lookback=lookback,
        )
        if sig is None:
            continue
        passed += 1

        name = d.get("name", "") or ticker_names.get(tkr, "")
        daily_close = d.get("daily_close")
        daily_price = round(daily_close.iloc[-1], 2) if daily_close is not None else 0
        hourly_close = round(d["close"].iloc[-1], 2)

        yield {
            "ticker": tkr,
            "name": name,
            "close": hourly_close,
            "daily_close": daily_price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "price_slope": price_slope,
            "kdj_k_slope": k_slope,
        }

    print(f"  Divergence detected: {passed} passed")


def _write_csv(results, prefix, cols, sort_key, output_dir=OUTPUT_DIR):
    """Sort results and write {prefix}_{date}.csv."""
    results.sort(key=sort_key)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{prefix}_{datetime.now():%Y-%m-%d}.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(results)
    print(f"  -> {len(results)} stocks saved to {path}")
    return path


def main():
    print("=" * 56)
    print("  Bursa Malaysia Stock Screener  (2 outputs)")
    print(f"  Timeframe: 1-hour + daily  |  SMA: {SMA_PERIODS}")
    print(f"  KDJ: ({KDJ_PERIOD},{KDJ_SIGNAL}) | oversold < {KDJ_OVERSOLD} | lookback {KDJ_LOOKBACK}")
    print("=" * 56)
    print()

    tickers = load_tickers(TICKERS_FILE)
    data = download_data(tickers)

    # ── Screener 1: SMA Compression ─────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [1/2] SMA Compression + KDJ + Trend + Volume")
    print("=" * 56)
    sma_results = list(run_sma_screener(data, tickers))
    sma_cols = ["ticker", "name", "close", "MA20", "MA30", "MA50", "MA120", "MA200",
                "divergence_pct", "kdj_signal", "kdj_k", "kdj_d", "kdj_j",
                "daily_trend", "vol_ratio"]
    _write_csv(sma_results, "screener_sma", sma_cols,
               sort_key=lambda r: r["divergence_pct"])

    # ── Screener 2: KDJ Divergence ──────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [2/2] KDJ Bullish Divergence  (price down, KDJ up)")
    print("=" * 56)
    div_results = list(run_divergence_screener(data, tickers))
    div_cols = ["ticker", "name", "close", "daily_close",
                "kdj_k", "kdj_d", "kdj_j", "price_slope", "kdj_k_slope"]
    _write_csv(div_results, "screener_divergence", div_cols,
               sort_key=lambda r: r["kdj_k_slope"] - abs(r["price_slope"]))

    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CANCEL] Screener cancelled by user.")
        sys.exit(0)
