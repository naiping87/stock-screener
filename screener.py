"""
Bursa Malaysia Stock Screener — 3 scripts → 1 combined CSV:
  1. sma_daily      — daily SMA 5/10/20/30/50 compressed <3% for 20+ days
  2. kdj_divergence — price falling, KDJ rising over 30 days
  3. sma_hourly     — hourly SMA 5/10/20/30/50 compressed <3% for 20+ hours
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
SMA_PERIODS = [5, 10, 20, 30, 50]
DIVERGENCE_THRESHOLD = 3.0          # percent
VOL_MIN = 500000                    # min daily volume MA
VOL_MIN_HOURLY = 100000             # min hourly volume MA
MAX_WORKERS = 10                    # concurrent download threads
REQUEST_DELAY = 0.1                 # seconds between requests per thread
MAX_RETRIES = 3
MIN_COMPRESSION_BARS = 20           # SMAs must be tight for this many bars
KDJ_PERIOD = 9                      # KDJ lookback (same as Pine Script 'Period')
KDJ_SIGNAL = 3                      # KDJ smooth (same as Pine Script 'Signal Period')
DIVERGENCE_LOOKBACK = 30            # bars for KDJ/price divergence detection
DAILY_DAYS = 400                    # days of daily data (weekly KDJ needs 60+ bars, ~400 days)
HOURLY_DAYS = 30                    # days of hourly data (needs 70+ valid bars for 50h SMA + 20 compression)
WEEKLY_VOL_MIN = 500000             # min weekly volume MA
KDJ_LOOKBACK = 3                    # bars to look back for golden cross
KDJ_OVERSOLD = 50                   # K must be below this for valid signal
SCORE_TREND_PERIODS = [20, 30, 60, 120]  # SMA periods for trend divergence
SCORE_TREND_THRESHOLD = 1.0         # max divergence % for trend score
SCORE_SMA200_SLOPE_BARS = 20        # bars for SMA200 slope check
SCORE_VOL_PERIOD = 60               # days for volatility check
SCORE_VOL_THRESHOLD = 5.0           # min annualized volatility %
SCORE_VOL_MA_BARS = 5               # bars for volume MA
SCORE_VOL_MA_THRESHOLD = 1_000_000  # min volume MA
SCORE_TOP_N = 50                    # top N results to show
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


def _fetch_ticker(sess, tkr, dp1, dp2, hp1, hp2, min_bars_d, min_bars_h):
    """Download daily + hourly data for one ticker (weekly resampled from daily)."""
    d_data, name = _fetch_chart(sess, tkr, dp1, dp2, "1d", min_bars_d)
    if d_data is None:
        return tkr, None

    d_close = d_data["close"].dropna()
    d_high = d_data["high"].dropna()
    d_low = d_data["low"].dropna()
    d_vol = d_data["volume"].fillna(0)
    di = d_close.index.intersection(d_high.index).intersection(d_low.index).intersection(d_vol.index)

    result = {
        "close": d_close.loc[di],
        "high": d_high.loc[di],
        "low": d_low.loc[di],
        "volume": d_vol.loc[di],
        "name": name,
    }

    # Hourly data
    h_data, _ = _fetch_chart(sess, tkr, hp1, hp2, "1h", min_bars_h)
    if h_data is not None:
        h_close = h_data["close"].dropna()
        h_vol = h_data["volume"].fillna(0)
        if len(h_close) >= min_bars_h:
            hi = h_close.index.intersection(h_vol.index)
            result["close_hourly"] = h_close.loc[hi]
            result["volume_hourly"] = h_vol.loc[hi]

    # Weekly data — resample from daily for consistent OHLC
    if len(di) >= 5:
        w_ohlc = {
            "close": d_close.loc[di].resample("W").last(),
            "high": d_high.loc[di].resample("W").max(),
            "low": d_low.loc[di].resample("W").min(),
            "volume": d_vol.loc[di].resample("W").sum(),
        }
        wk_idx = w_ohlc["close"].index.intersection(
            w_ohlc["high"].index
        ).intersection(w_ohlc["low"].index).intersection(w_ohlc["volume"].index)
        result["close_weekly"] = w_ohlc["close"].loc[wk_idx]
        result["high_weekly"] = w_ohlc["high"].loc[wk_idx]
        result["low_weekly"] = w_ohlc["low"].loc[wk_idx]
        result["volume_weekly"] = w_ohlc["volume"].loc[wk_idx]

    return tkr, result


def download_data(tickers, progress_cb=None):
    """Download daily + hourly + weekly data concurrently via Yahoo chart API."""
    end_date = datetime.now()
    d_start = end_date - timedelta(days=DAILY_DAYS)
    h_start = end_date - timedelta(days=HOURLY_DAYS)
    dp1, dp2 = int(d_start.timestamp()), int(end_date.timestamp())
    hp1, hp2 = int(h_start.timestamp()), int(end_date.timestamp())
    min_bars_d = max(SMA_PERIODS) + MIN_COMPRESSION_BARS
    min_bars_h = max(SMA_PERIODS) + MIN_COMPRESSION_BARS

    ticker_list = sorted(tickers.keys())
    all_data = {}
    session = _build_session()

    print(f"[DOWNLOAD] Fetching {DAILY_DAYS}d daily + {HOURLY_DAYS}d hourly "
          f"for {len(ticker_list)} tickers (workers={MAX_WORKERS}) ...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _fetch_ticker, session, tkr,
                dp1, dp2, hp1, hp2, min_bars_d, min_bars_h,
            ): tkr
            for tkr in ticker_list
        }
        done = 0
        for f in as_completed(futures):
            tkr, data = f.result()
            if data is not None:
                all_data[tkr] = data
            done += 1
            if progress_cb:
                progress_cb(done, len(ticker_list))
            elif done % 100 == 0:
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
    k = rsv.ewm(alpha=alpha, min_periods=1, adjust=False).mean()
    d = k.ewm(alpha=alpha, min_periods=1, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j


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

    mask = ~np.isnan(price_slice) & ~np.isnan(k_slice)
    if mask.sum() < lookback // 2:
        return None, None, None, None, None, None

    price_slope = np.polyfit(x[mask], price_slice[mask], 1)[0]
    k_slope = np.polyfit(x[mask], k_slice[mask], 1)[0]

    if price_slope < 0 and k_slope > 0:
        k_now = round(k.iloc[-1], 1)
        d_now = round(d.iloc[-1], 1)
        j_now = round(j.iloc[-1], 1)
        return "bullish_div", k_now, d_now, j_now, round(price_slope, 4), round(k_slope, 4)

    return None, None, None, None, None, None


def _check_volume(vol_series, min_vol=None, roll=20):
    """Return True if volume MA > min_vol (reads VOL_MIN if not given)."""
    if min_vol is None:
        min_vol = VOL_MIN  # read module variable at call time
    if vol_series is None or len(vol_series) < roll:
        return False
    return vol_series.rolling(roll).mean().iloc[-1] > min_vol


def run_sma_screener(data, ticker_names=None, periods=SMA_PERIODS,
                     threshold=DIVERGENCE_THRESHOLD,
                     min_compression=MIN_COMPRESSION_BARS):
    """
    SMA Compression Screener (daily):
      Stage 1 — SMA divergence <= threshold% for >= min_compression bars
      Stage 2 — daily volume MA > min_vol
    """
    ticker_names = ticker_names or {}
    s1 = 0
    s2 = 0

    for tkr, d in data.items():
        close = d["close"]
        div, sma = _calc_divergence(close, periods)
        if div is None or div > threshold:
            continue

        if not _check_compression_duration(close, periods, threshold, min_compression):
            continue
        s1 += 1

        if not _check_volume(d.get("volume")):
            continue
        s2 += 1

        vol = d.get("volume")
        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if vol is not None and len(vol) >= 20 else 0
        trend = "↑" if close.iloc[-1] > sma[20] else "↓"

        name = d.get("name", "") or ticker_names.get(tkr, "")
        yield {
            "ticker": tkr,
            "name": name,
            "close": round(close.iloc[-1], 2),
            "MA5": round(sma[5], 2),
            "MA10": round(sma[10], 2),
            "MA20": round(sma[20], 2),
            "MA30": round(sma[30], 2),
            "MA50": round(sma[50], 2),
            "divergence_pct": round(div, 2),
            "vol_ma": vol_ma_val,
            "trend": trend,
        }

    print(f"  Stage 1 (compression):    {s1} passed")
    print(f"  Stage 2 (vol > {VOL_MIN//1000}k):  {s2} passed")


def run_sma_hourly_screener(data, ticker_names=None, periods=SMA_PERIODS,
                            threshold=DIVERGENCE_THRESHOLD,
                            min_compression=MIN_COMPRESSION_BARS):
    """
    SMA Compression Screener (hourly):
      Stage 1 — SMA divergence <= threshold% for >= min_compression bars
      Stage 2 — hourly volume MA > min_vol
    """
    ticker_names = ticker_names or {}
    s1 = 0
    s2 = 0

    for tkr, d in data.items():
        close = d.get("close_hourly")
        if close is None:
            continue

        div, sma = _calc_divergence(close, periods)
        if div is None or div > threshold:
            continue

        if not _check_compression_duration(close, periods, threshold, min_compression):
            continue
        s1 += 1

        if not _check_volume(d.get("volume_hourly"), min_vol=VOL_MIN_HOURLY):
            continue
        s2 += 1

        vol = d.get("volume_hourly")
        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if vol is not None and len(vol) >= 20 else 0
        trend = "↑" if close.iloc[-1] > sma[20] else "↓"

        name = d.get("name", "") or ticker_names.get(tkr, "")
        yield {
            "ticker": tkr,
            "name": name,
            "close": round(close.iloc[-1], 2),
            "MA5": round(sma[5], 2),
            "MA10": round(sma[10], 2),
            "MA20": round(sma[20], 2),
            "MA30": round(sma[30], 2),
            "MA50": round(sma[50], 2),
            "divergence_pct": round(div, 2),
            "vol_ma": vol_ma_val,
            "trend": trend,
        }

    print(f"  Stage 1 (compression):      {s1} passed")
    print(f"  Stage 2 (vol > {VOL_MIN_HOURLY//1000}k):     {s2} passed")


def run_divergence_screener(data, ticker_names=None,
                            lookback=DIVERGENCE_LOOKBACK):
    """
    KDJ Divergence Screener:
      Stage 1 — Bullish divergence (price falling, KDJ rising, daily lookback bars)
      Stage 2 — daily volume MA > min_vol
    """
    ticker_names = ticker_names or {}
    s1 = 0
    s2 = 0

    for tkr, d in data.items():
        sig, k_val, d_val, j_val, price_slope, k_slope = _detect_divergence(
            d["high"], d["low"], d["close"],
            lookback=lookback,
        )
        if sig is None:
            continue
        s1 += 1

        if not _check_volume(d.get("volume")):
            continue
        s2 += 1

        vol = d.get("volume")
        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if vol is not None and len(vol) >= 20 else 0

        name = d.get("name", "") or ticker_names.get(tkr, "")
        price = round(d["close"].iloc[-1], 2)

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "price_slope": price_slope,
            "kdj_k_slope": k_slope,
            "vol_ma": vol_ma_val,
        }

    print(f"  Stage 1 (divergence):     {s1} passed")
    print(f"  Stage 2 (vol > {VOL_MIN//1000}k): {s2} passed")


def _detect_kdj_signal(k, d, j, lookback=KDJ_LOOKBACK, oversold=KDJ_OVERSOLD):
    """Detect KDJ golden cross via J line (J=3K-2D, crosses K when K crosses D).

    Returns (signal, k_val, d_val, j_val):
      signal: 'crossed' (J just crossed K) | 'above' (J>K and J>D) | None
    """
    if k is None or len(k) < lookback + 2:
        return None, None, None, None

    k_now, d_now = k.iloc[-1], d.iloc[-1]
    j_now = j.iloc[-1] if j is not None else float("nan")

    # Check if J is currently above both K and D (bullish J position)
    j_above = j_now > k_now and j_now > d_now

    # Recent J-cross-K (equivalent to K-cross-D)
    for i in range(-lookback, 0):
        j_i = j.iloc[i]
        k_i = k.iloc[i]
        j_prev = j.iloc[i - 1]
        k_prev = k.iloc[i - 1]
        if j_i > k_i and j_prev <= k_prev:
            if k_i < oversold:
                return "crossed", round(k_now, 1), round(d_now, 1), round(j_now, 1)

    # J above K and D (already bullish, no recent cross)
    if j_above and j_now < 70:  # not overbought yet
        return "above", round(k_now, 1), round(d_now, 1), round(j_now, 1)

    return None, None, None, None


def run_weekly_kdj_screener(data, ticker_names=None,
                            vol_min=WEEKLY_VOL_MIN):
    """
    Weekly KDJ Golden Cross Screener:
      Stage 1 — Weekly KDJ golden cross / near-cross in oversold zone
      Stage 2 — Weekly volume MA > vol_min
    """
    ticker_names = ticker_names or {}
    s1 = 0
    s2 = 0

    for tkr, d in data.items():
        w_close = d.get("close_weekly")
        w_high = d.get("high_weekly")
        w_low = d.get("low_weekly")
        if w_close is None or len(w_close) < KDJ_PERIOD + KDJ_SIGNAL:
            continue

        k, d_kdj, j = _calc_kdj(w_high, w_low, w_close,
                                period=KDJ_PERIOD, signal=KDJ_SIGNAL)
        kdj_sig, k_val, d_val, j_val = _detect_kdj_signal(k, d_kdj, j)
        if kdj_sig is None:
            continue
        s1 += 1

        w_vol = d.get("volume_weekly")
        if not _check_volume(w_vol, min_vol=vol_min):
            continue
        s2 += 1

        name = d.get("name", "") or ticker_names.get(tkr, "")
        price = round(w_close.iloc[-1], 2)
        vol_ma_val = int(w_vol.rolling(20).mean().iloc[-1]) if w_vol is not None and len(w_vol) >= 20 else 0

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "kdj_signal": kdj_sig,
            "vol_ma": vol_ma_val,
        }

    print(f"  Stage 1 (weekly KDJ cross): {s1} passed")
    print(f"  Stage 2 (weekly vol > {vol_min//1000}k):   {s2} passed")


def run_scoring_screener(data, ticker_names=None,
                         trend_periods=SCORE_TREND_PERIODS,
                         trend_threshold=SCORE_TREND_THRESHOLD,
                         sma200_slope_bars=SCORE_SMA200_SLOPE_BARS,
                         vol_period=SCORE_VOL_PERIOD,
                         vol_threshold=SCORE_VOL_THRESHOLD,
                         vol_ma_bars=SCORE_VOL_MA_BARS,
                         vol_ma_threshold=SCORE_VOL_MA_THRESHOLD,
                         top_n=SCORE_TOP_N):
    """
    Weighted Scoring Screener — scores every stock on 6 factors.
    Returns top_n stocks sorted by total score descending.
    """
    ticker_names = ticker_names or {}
    results = []

    for tkr, d in data.items():
        close = d["close"]
        high = d["high"]
        low = d["low"]
        vol = d.get("volume")
        score = 0
        details = {}

        # 1. Close > SMA200 (+1)
        sma200 = close.rolling(200).mean()
        above_200 = len(sma200.dropna()) > 0 and close.iloc[-1] > sma200.iloc[-1]
        if above_200:
            score += 1
        details["above_200"] = above_200

        # 2. SMA200 slope > 0 (+1)
        slope_up = False
        if len(sma200.dropna()) >= sma200_slope_bars:
            y = sma200.iloc[-sma200_slope_bars:].values.astype(float)
            if not np.isnan(y).any():
                slope = np.polyfit(np.arange(sma200_slope_bars, dtype=float), y, 1)[0]
                slope_up = slope > 0
        if slope_up:
            score += 1
        details["sma200_up"] = slope_up

        # 3. SMA divergence < threshold (+1)
        trend_tight = False
        sma_vals = {}
        for p in trend_periods:
            sma_vals[p] = close.rolling(p).mean()
        vals = [sma_vals[p].iloc[-1] for p in trend_periods]
        if not any(pd.isna(v) for v in vals):
            div = (max(vals) - min(vals)) / close.iloc[-1] * 100.0
            trend_tight = div < trend_threshold
        if trend_tight:
            score += 1
        details["trend_tight"] = trend_tight

        # 4. KDJ golden cross / near-cross (+1)
        k, d_kdj, j = _calc_kdj(high, low, close)
        kdj_sig = _detect_kdj_signal(k, d_kdj, j)[0]
        kdj_ok = kdj_sig is not None
        if kdj_ok:
            score += 1
        details["kdj_sig"] = kdj_sig or ""

        # 5. Volatility > threshold (+1)
        vol_ok = False
        if len(close) >= vol_period:
            returns = close.pct_change().dropna()
            if len(returns) >= vol_period:
                ann_vol = returns.iloc[-vol_period:].std() * (252 ** 0.5) * 100
                vol_ok = ann_vol > vol_threshold
        if vol_ok:
            score += 1
        details["vol_ok"] = vol_ok

        # 6. Volume MA > threshold (+1)
        vol_ma_ok = False
        if vol is not None and len(vol) >= vol_ma_bars:
            vol_ma_ok = vol.rolling(vol_ma_bars).mean().iloc[-1] > vol_ma_threshold
        if vol_ma_ok:
            score += 1
        details["vol_ma_ok"] = vol_ma_ok

        name = d.get("name", "") or ticker_names.get(tkr, "")
        results.append({
            "ticker": tkr,
            "name": name,
            "close": round(close.iloc[-1], 2),
            "score": score,
            "above_200": "Y" if above_200 else "",
            "sma200_up": "Y" if slope_up else "",
            "trend_tight": "Y" if trend_tight else "",
            "kdj_sig": kdj_sig or "",
            "vol_ok": "Y" if vol_ok else "",
            "vol_ma_ok": "Y" if vol_ma_ok else "",
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    print(f"  Scored {len(results)} stocks, top score: {results[0]['score'] if results else 0}")
    return results[:top_n]


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
    print("  Bursa Malaysia Stock Screener  (3 scripts, 1 output)")
    print(f"  SMA: {SMA_PERIODS} | divergence < {DIVERGENCE_THRESHOLD}%")
    print(f"  Compression >= {MIN_COMPRESSION_BARS} bars | Vol daily>{VOL_MIN//1000}k hourly>{VOL_MIN_HOURLY//1000}k")
    print(f"  KDJ divergence {DIVERGENCE_LOOKBACK}d")
    print("=" * 56)
    print()

    tickers = load_tickers(TICKERS_FILE)
    data = download_data(tickers)

    all_results = []

    # ── Script 1: Daily SMA Compression ─────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [1/3] Daily SMA Compression")
    print(f"        divergence <= {DIVERGENCE_THRESHOLD}% for >= {MIN_COMPRESSION_BARS} days")
    print("=" * 56)
    for r in run_sma_screener(data, tickers):
        r["script"] = "sma_daily"
        all_results.append(r)

    # ── Script 2: KDJ Divergence ────────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [2/3] KDJ Bullish Divergence  (price down, KDJ up)")
    print(f"        lookback {DIVERGENCE_LOOKBACK} days")
    print("=" * 56)
    for r in run_divergence_screener(data, tickers):
        r["script"] = "kdj_divergence"
        all_results.append(r)

    # ── Script 3: Hourly SMA Compression ────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [3/3] Hourly SMA Compression")
    print(f"        divergence <= {DIVERGENCE_THRESHOLD}% for >= {MIN_COMPRESSION_BARS} hours")
    print("=" * 56)
    for r in run_sma_hourly_screener(data, tickers):
        r["script"] = "sma_hourly"
        all_results.append(r)

    # ── Write combined CSV ──────────────────────────────────────────────────
    print("\n" + "=" * 56)
    combined_cols = ["script", "ticker", "name", "close",
                     "MA5", "MA10", "MA20", "MA30", "MA50",
                     "divergence_pct", "kdj_k", "kdj_d", "kdj_j",
                     "price_slope", "kdj_k_slope"]
    _write_csv(all_results, "screener_combined", combined_cols,
               sort_key=lambda r: (
                   0 if r["script"] == "sma_daily" else
                   1 if r["script"] == "sma_hourly" else 2,
                   r.get("divergence_pct", 999),
               ))

    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CANCEL] Screener cancelled by user.")
        sys.exit(0)
