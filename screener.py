"""
Bursa Malaysia Stock Screener — 5 screeners:
  1. ema_daily      — daily EMA 10/20/50/100/200 compressed <3% for 20+ days
  2. ema_hourly     — hourly EMA 10/20/50/100/200 compressed <3% for 20+ hours
  3. kdj_divergence — price falling, KDJ rising over 30 days
  4. weekly_kdj     — weekly KDJ golden cross / near-cross
  5. scoring        — weighted 11-factor scoring system
"""
import csv
import os
import sys
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests
import akshare as ak

# ── Configuration ────────────────────────────────────────────────────────────
EMA_PERIODS = [10, 20, 50, 100, 200]
DIVERGENCE_THRESHOLD = 3.0          # percent
VOL_MIN = 500000                    # min daily volume MA
VOL_MIN_HOURLY = 100000             # min hourly volume MA
MAX_WORKERS = 15                    # concurrent download threads
REQUEST_DELAY = 0.0                 # seconds between requests per thread
MAX_RETRIES = 3
MIN_COMPRESSION_BARS = 20           # SMAs must be tight for this many bars
KDJ_PERIOD = 20                     # KDJ lookback (same as Pine Script 'Period')
KDJ_SIGNAL = 5                      # KDJ smooth (same as Pine Script 'Signal Period')
DIVERGENCE_LOOKBACK = 30            # bars for KDJ/price divergence detection
DAILY_DAYS = 400                    # days of daily data (max EMA period 200 + 20 compression bars)
HOURLY_DAYS = 50                    # days of hourly data
WEEKLY_VOL_MIN = 500000             # min weekly volume MA
DAILY_VOL_MIN = 500000              # min daily volume MA for KDJ screener
DAILY_VOL_RATIO = 1.2               # cross bar vol must be > 1.2x 20-day MA vol
KDJ_LOOKBACK = 3                    # bars to look back for golden cross
KDJ_OVERSOLD = 50                   # K must be below this for valid signal (legacy, not enforced)
SCORE_TREND_PERIODS = [10, 20, 50, 100, 200]  # EMA periods for trend divergence
SCORE_TREND_THRESHOLD = 1.0         # max divergence % for trend score
SCORE_EMA200_SLOPE_BARS = 20         # bars for EMA200 slope check
SCORE_VOL_PERIOD = 60               # days for volatility check
SCORE_VOL_THRESHOLD = 5.0           # min annualized volatility %
SCORE_VOL_MA_BARS = 5               # bars for volume MA
SCORE_VOL_MA_THRESHOLD = 1_000_000  # min volume MA
SCORE_TOP_N = 50                    # top N results to show
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TICKERS_FILE = os.path.join(SCRIPT_DIR, "tickers.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
# ──────────────────────────────────────────────────────────────────────────────


def load_tickers(path: str, suffix: str = ".KL") -> dict[str, str]:
    """Read tickers.csv -> dict {full_ticker: company_name}.
    
    Args:
        path: path to tickers CSV
        suffix: Yahoo Finance suffix to append (".KL" for Bursa, "" for US, etc.)
    """
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
            if suffix == ".KL":
                # Bursa: only numeric codes (and known special cases)
                if code.isdigit() or code == "5235SS":
                    tickers[f"{code}{suffix}"] = name
            elif suffix:
                # Other markets with suffix: accept all codes
                tickers[f"{code}{suffix}"] = name
            else:
                # US: no suffix, accept all non-numeric-looking codes
                tickers[code] = name
    print(f"[INFO] Loaded {len(tickers)} tickers")
    return tickers


def _build_session() -> requests.Session:
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


def _fetch_chart(sess, tkr, period1, period2, interval, min_bars, timezone="Asia/Kuala_Lumpur"):
    # type: (requests.Session, str, int, int, str, int, str) -> tuple[dict[str, pd.Series] | None, str]
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
            resp = sess.get(url, params=params, timeout=10)
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

            idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert(timezone)

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


def _fetch_ticker(sess, tkr, dp1, dp2, hp1, hp2, min_bars_d, min_bars_h, timezone="Asia/Kuala_Lumpur"):
    """Download daily + hourly data for one ticker (weekly resampled from daily)."""
    d_data, name = _fetch_chart(sess, tkr, dp1, dp2, "1d", min_bars_d, timezone)
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

    # Hourly data — non-blocking, no retries (fast fail)
    try:
        h_data, _ = _fetch_chart(sess, tkr, hp1, hp2, "1h", min_bars_h, timezone)
        if h_data is not None:
            h_close = h_data["close"].dropna()
            h_vol = h_data["volume"].fillna(0)
            if len(h_close) >= min_bars_h:
                hi = h_close.index.intersection(h_vol.index)
                result["close_hourly"] = h_close.loc[hi]
                result["volume_hourly"] = h_vol.loc[hi]
    except Exception:
        pass


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


def download_data(tickers: dict[str, str], progress_cb: Callable[[int, int], None] | None = None, timezone: str = "Asia/Kuala_Lumpur", market_code: str = "my", data_provider: str = "yahoo") -> dict[str, dict[str, Any]]:
    """Download daily + hourly + weekly data concurrently via Yahoo chart API."""
    if data_provider == "akshare":
        return _download_akshare(tickers, timezone, progress_cb)
    end_date = datetime.now()
    d_start = end_date - timedelta(days=DAILY_DAYS)
    h_start = end_date - timedelta(days=HOURLY_DAYS)
    dp1, dp2 = int(d_start.timestamp()), int(end_date.timestamp())
    hp1, hp2 = int(h_start.timestamp()), int(end_date.timestamp())
    min_bars_d = max(EMA_PERIODS) + MIN_COMPRESSION_BARS
    # Hourly: Yahoo may return fewer bars; cap requirement at EMA50+compression
    min_bars_h = 50 + MIN_COMPRESSION_BARS

    ticker_list = sorted(tickers.keys())
    all_data = {}
    session = _build_session()

    print(f"[DOWNLOAD] Fetching {DAILY_DAYS}d daily + {HOURLY_DAYS}d hourly "
          f"for {len(ticker_list)} tickers (workers={MAX_WORKERS}) ...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _fetch_ticker, session, tkr,
                dp1, dp2, hp1, hp2, min_bars_d, min_bars_h, timezone,
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
def _fetch_akshare_ticker(tkr, name, days, timezone):
    """Download daily data for one A-share ticker via AkShare. Returns dict or None."""
    end_str = datetime.now().strftime("%Y%m%d")
    start_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_hist(symbol=tkr, period="daily", start_date=start_str,
                                    end_date=end_str, adjust="qfq")
            if df is None or len(df) < 20:
                return None
            df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                    "最高": "high", "最低": "low", "成交量": "volume"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            tz_idx = df.index.tz_localize(timezone) if df.index.tz is None else df.index.tz_convert(timezone)
            def _s(col):
                return pd.Series(df[col].values, index=tz_idx, dtype=float)
            result = {"close": _s("close"), "high": _s("high"), "low": _s("low"),
                      "volume": _s("volume"), "name": name}
            if len(tz_idx) >= 5:
                w_close = result["close"].resample("W").last()
                w_high = result["high"].resample("W").max()
                w_low = result["low"].resample("W").min()
                w_vol = result["volume"].resample("W").sum()
                wk_idx = w_close.index.intersection(w_high.index).intersection(w_low.index).intersection(w_vol.index)
                result["close_weekly"] = w_close.loc[wk_idx]
                result["high_weekly"] = w_high.loc[wk_idx]
                result["low_weekly"] = w_low.loc[wk_idx]
                result["volume_weekly"] = w_vol.loc[wk_idx]
            return result
        except Exception:
            if attempt < 1:
                time.sleep(0.5)
    return None


def _download_akshare(tickers, timezone, progress_cb=None):
    all_data = {}
    ticker_list = sorted(tickers.keys())
    ak_workers = min(MAX_WORKERS, 15)
    print(f'[AKSHARE] Fetching {DAILY_DAYS}d daily for {len(ticker_list)} tickers (workers={ak_workers}) ...')
    with ThreadPoolExecutor(max_workers=ak_workers) as pool:
        futures = {pool.submit(_fetch_akshare_ticker, tkr, tickers[tkr], DAILY_DAYS, timezone): tkr for tkr in ticker_list}
        done = 0
        for f in as_completed(futures):
            tkr = futures[f]
            data = f.result()
            if data is not None:
                all_data[tkr] = data
            done += 1
            if progress_cb:
                progress_cb(done, len(ticker_list))
            elif done % 200 == 0:
                print(f'  {done}/{len(ticker_list)} ...')
    print(f'[AKSHARE] Got data for {len(all_data)} / {len(tickers)} tickers')
    return all_data


def _calc_divergence(close_series: pd.Series, periods: list[int]) -> tuple[float | None, dict[int, float] | None]:
    """Return (divergence_pct, ema_dict) or (None, None).
    Automatically skips periods that are too large for the available data.
    ema_dict maps period -> last EMA value (scalar)."""
    # Filter to periods that fit within available data
    valid_periods = [p for p in periods if len(close_series) >= p]
    if len(valid_periods) < 2:
        return None, None
    ema = {}
    for p in valid_periods:
        val = close_series.ewm(span=p, adjust=False).mean().iloc[-1]
        if pd.isna(val):
            return None, None
        ema[p] = val
    close = close_series.iloc[-1]
    vals = list(ema.values())
    return (max(vals) - min(vals)) / close * 100.0, ema


def _compute_ema_series(close_series: pd.Series, periods: list[int]) -> dict[int, pd.Series]:
    """Compute full EMA series for a list of periods (used for compression check)."""
    valid_periods = [p for p in periods if p <= len(close_series)]
    return {p: close_series.ewm(span=p, adjust=False).mean() for p in valid_periods}


def _check_compression_duration(close_series: pd.Series, periods: list[int], threshold: float, min_bars: int, emas: dict[int, pd.Series] | None = None) -> bool:
    """Return True if EMA divergence stayed <= threshold for the last min_bars bars.
    Automatically skips periods that are too large for the available data.
    Optionally accepts pre-computed emas dict to avoid redundant computation."""
    valid_periods = [p for p in periods if p + min_bars <= len(close_series)]
    if len(valid_periods) < 2:
        return False

    if emas is None:
        emas = {p: close_series.ewm(span=p, adjust=False).mean() for p in valid_periods}
    else:
        emas = {p: emas[p] for p in valid_periods if p in emas}
        if len(emas) < 2:
            return False

    for i in range(-min_bars, 0):
        vals = [emas[p].iloc[i] for p in emas]
        if any(pd.isna(v) for v in vals):
            return False
        div = (max(vals) - min(vals)) / close_series.iloc[i] * 100.0
        if div > threshold:
            return False
    return True


def _calc_kdj(daily_high: pd.Series, daily_low: pd.Series, daily_close: pd.Series, period: int = KDJ_PERIOD, signal: int = KDJ_SIGNAL) -> tuple[pd.Series | None, pd.Series | None, pd.Series | None]:
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


def _detect_divergence(daily_high: pd.Series, daily_low: pd.Series, daily_close: pd.Series,
                       lookback: int = DIVERGENCE_LOOKBACK, kdj_period: int = KDJ_PERIOD,
                       kdj_signal: int = KDJ_SIGNAL):
    # type: (...) -> tuple[str | None, float | None, float | None, float | None, float | None, float | None]
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


def _check_volume(vol_series: pd.Series | None, min_vol: int | None = None, roll: int = 20) -> bool:
    """Return True if volume MA > min_vol (reads VOL_MIN if not given)."""
    if min_vol is None:
        min_vol = VOL_MIN  # read module variable at call time
    if vol_series is None or len(vol_series) < roll:
        return False
    return vol_series.rolling(roll).mean().iloc[-1] > min_vol


def _run_ema_screener_impl(data, ticker_names, periods, threshold, min_compression,
                          close_key, vol_key, vol_min, label):
    """Shared EMA compression screener logic (daily or hourly)."""
    if periods is None:
        periods = EMA_PERIODS
    ticker_names = ticker_names or {}
    s1 = 0
    s2 = 0

    for tkr, d in data.items():
        close = d.get(close_key) if close_key != "close" else d["close"]
        if close is None:
            continue

        # Compute EMA series once, derive both divergence + compression check
        ema_series = _compute_ema_series(close, periods)
        if len(ema_series) < 2:
            continue

        # Divergence from last values
        vals = [ema_series[p].iloc[-1] for p in ema_series if not pd.isna(ema_series[p].iloc[-1])]
        if len(vals) < 2:
            continue
        div = (max(vals) - min(vals)) / close.iloc[-1] * 100.0
        if div > threshold:
            continue

        # Build scalar ema dict for output
        ema = {p: round(ema_series[p].iloc[-1], 2) for p in ema_series}

        if not _check_compression_duration(close, list(ema_series.keys()), threshold,
                                           min_compression, emas=ema_series):
            continue
        s1 += 1

        vol = d.get(vol_key)
        if vol is None or not _check_volume(vol, min_vol=vol_min):
            continue
        s2 += 1

        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else 0
        trend_ema = 50 if 50 in ema else min(ema.keys(), key=lambda x: abs(x - 50))
        trend = "↑" if close.iloc[-1] > ema[trend_ema] else "↓"

        name = d.get("name", "") or ticker_names.get(tkr, "")
        result = {
            "ticker": tkr,
            "name": name,
            "close": round(close.iloc[-1], 2),
            "divergence_pct": round(div, 2),
            "vol_ma": vol_ma_val,
            "trend": trend,
        }
        for p in periods:
            if p in ema:
                result[f"EMA{p}"] = ema[p]
        yield result

    print(f"  Stage 1 ({label} compression):     {s1} passed")
    print(f"  Stage 2 ({label} vol > {vol_min//1000}k): {s2} passed")


def run_ema_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                     periods: list[int] | None = None,
                     threshold: float = DIVERGENCE_THRESHOLD,
                     min_compression: int = MIN_COMPRESSION_BARS) -> Generator[dict[str, Any], None, None]:
    """
    EMA Compression Screener (daily):
      Stage 1 — EMA divergence <= threshold% for >= min_compression bars
      Stage 2 — daily volume MA > VOL_MIN
    """
    yield from _run_ema_screener_impl(
        data, ticker_names, periods, threshold, min_compression,
        close_key="close", vol_key="volume", vol_min=VOL_MIN, label="daily",
    )


def run_ema_hourly_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            periods: list[int] | None = None,
                            threshold: float = DIVERGENCE_THRESHOLD,
                            min_compression: int = MIN_COMPRESSION_BARS) -> Generator[dict[str, Any], None, None]:
    """
    EMA Compression Screener (hourly):
      Stage 1 — EMA divergence <= threshold% for >= min_compression bars
      Stage 2 — hourly volume MA > VOL_MIN_HOURLY
    """
    yield from _run_ema_screener_impl(
        data, ticker_names, periods, threshold, min_compression,
        close_key="close_hourly", vol_key="volume_hourly",
        vol_min=VOL_MIN_HOURLY, label="hourly",
    )


def run_divergence_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            lookback: int = DIVERGENCE_LOOKBACK) -> Generator[dict[str, Any], None, None]:
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


def detectKDJSignal(k, d, j, lookback = KDJ_LOOKBACK, oversold = KDJ_OVERSOLD):
    """Detect KDJ golden cross via J line (J=3K-2D, crosses K when K crosses D).
    
    Returns (signal, k_val, d_val, j_val):
      signal: 'crossed' (fresh cross, was below for >=2 bars) | 'above' (bullish, established) | None
    """
    if k is None or len(k) < 5:
        return None, None, None, None
    
    k_now, d_now = k.iloc[-1], d.iloc[-1]
    j_now = j.iloc[-1] if j is not None else float("nan")
    
    # Current position: J above both K and D
    j_above = j_now > k_now and j_now > d_now
    
    # ---- Fresh golden cross? ----
    # Must: J[-1] > K[-1] and J[-2] <= K[-2]
    j1, k1 = j.iloc[-1], k.iloc[-1]
    j2, k2 = j.iloc[-2], k.iloc[-2]
    j3, k3 = j.iloc[-3], k.iloc[-3]
    
    cross_trigger = j1 > k1 and j2 <= k2
    
    if cross_trigger:
        # Was J below K for at least 2 consecutive bars before the cross?
        # Check bars -2 and -3 (both should be below or equal)
        bars_below = 0
        for i in range(-2, -6, -1):  # check bars -2 through -5
            if abs(i) >= len(k):
                break
            if j.iloc[i] <= k.iloc[i]:
                bars_below += 1
            else:
                break
        if bars_below >= 2:
            return "crossed", round(k_now, 1), round(d_now, 1), round(j_now, 1)
    
    # ---- Bullish but established (above) ----
    if j_above:
        return "above", round(k_now, 1), round(d_now, 1), round(j_now, 1)
    
    return None, None, None, None


def run_weekly_kdj_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            vol_min: int = WEEKLY_VOL_MIN) -> Generator[dict[str, Any], None, None]:
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
        kdj_sig, k_val, d_val, j_val = detectKDJSignal(k, d_kdj, j)
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


def run_daily_kdj_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                           vol_min: int = DAILY_VOL_MIN, vol_ratio: float = DAILY_VOL_RATIO) -> Generator[dict[str, Any], None, None]:
    """
    Daily KDJ Golden Cross Screener:
      Stage 1 — Daily KDJ golden cross (fresh, >=2 bars below before cross)
      Stage 2 — Daily volume MA > vol_min
      (Vol Ratio shown for reference, not used as filter)
    """
    ticker_names = ticker_names or {}
    s1 = s2 = 0

    for tkr, d in data.items():
        close = d.get("close")
        high = d.get("high")
        low = d.get("low")
        vol = d.get("volume")
        if close is None or len(close) < KDJ_PERIOD + KDJ_SIGNAL + 5:
            continue

        k, d_kdj, j = _calc_kdj(high, low, close, period=KDJ_PERIOD, signal=KDJ_SIGNAL)
        kdj_sig, k_val, d_val, j_val = detectKDJSignal(k, d_kdj, j)
        if kdj_sig is None:
            continue
        s1 += 1

        # Volume check: daily vol MA
        if not _check_volume(vol, min_vol=vol_min):
            continue
        s2 += 1

        # Volume ratio (informational, not a filter)
        vol_ratio_val = 0
        if vol is not None and len(vol) >= 21:
            vol_ma20 = vol.rolling(20).mean().iloc[-1]
            cross_vol = vol.iloc[-1]
            vol_ratio_val = round(cross_vol / vol_ma20 if vol_ma20 > 0 else 0, 1)

        name = d.get("name", "") or ticker_names.get(tkr, "")
        price = round(close.iloc[-1], 2)
        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if vol is not None and len(vol) >= 20 else 0

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "kdj_signal": kdj_sig,
            "vol_ratio": vol_ratio_val,
            "vol_ma": vol_ma_val,
        }

    print(f"  Stage 1 (daily KDJ cross):  {s1} passed")
    print(f"  Stage 2 (vol MA > {vol_min//1000}k): {s2} passed")


def run_scoring_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                         trend_periods: list[int] = SCORE_TREND_PERIODS,
                         trend_threshold: float = SCORE_TREND_THRESHOLD,
                         ema200_slope_bars: int = SCORE_EMA200_SLOPE_BARS,
                         vol_period: int = SCORE_VOL_PERIOD,
                         vol_threshold: float = SCORE_VOL_THRESHOLD,
                         vol_ma_bars: int = SCORE_VOL_MA_BARS,
                         vol_ma_threshold: int = SCORE_VOL_MA_THRESHOLD,
                         top_n: int = SCORE_TOP_N) -> list[dict[str, Any]]:
    """
    Weighted Scoring Screener — scores every stock on 11 factors.
    Returns top_n stocks sorted by total score descending.
    """
    ticker_names = ticker_names or {}
    results = []

    for tkr, d in data.items():
        close = d["close"]
        if len(close) < 20:  # minimum bars needed for any factor
            continue

        high = d["high"]
        low = d["low"]
        vol = d.get("volume")
        score = 0
        details = {}

        # ── Pre-compute all EMAs once ──────────────────────────────────────
        needed_spans = set(trend_periods) | {200, 50, 100, 20}
        ema = {}
        for span in needed_spans:
            if len(close) >= span:
                ema[span] = close.ewm(span=span, adjust=False).mean()

        # 1. Close > EMA200 (+1)
        above_200 = 200 in ema and close.iloc[-1] > ema[200].iloc[-1]
        if above_200:
            score += 1
        details["above_200"] = above_200

        # 2. EMA200 slope > 0 (+1)
        slope_up = False
        if 200 in ema and len(ema[200].dropna()) >= ema200_slope_bars:
            y = ema[200].iloc[-ema200_slope_bars:].values.astype(float)
            if not np.isnan(y).any():
                slope = np.polyfit(np.arange(ema200_slope_bars, dtype=float), y, 1)[0]
                slope_up = slope > 0
        if slope_up:
            score += 1
        details["ema200_up"] = slope_up

        # 3. EMA divergence < threshold (+1)
        trend_tight = False
        if all(p in ema for p in trend_periods):
            vals = [ema[p].iloc[-1] for p in trend_periods]
            if not any(pd.isna(v) for v in vals):
                div = (max(vals) - min(vals)) / close.iloc[-1] * 100.0
                trend_tight = div < trend_threshold
        if trend_tight:
            score += 1
        details["trend_tight"] = trend_tight

        # 4. KDJ golden cross / near-cross (+1)
        k, d_kdj, j = _calc_kdj(high, low, close)
        kdj_sig = detectKDJSignal(k, d_kdj, j)[0]
        kdj_ok = kdj_sig is not None
        if kdj_ok:
            score += 1
        details["kdj_sig"] = kdj_sig or ""

        # 5. Weekly KDJ golden cross / near-cross + volume confirmation (+1)
        wkdj_sig = None
        w_close = d.get("close_weekly")
        w_high = d.get("high_weekly")
        w_low = d.get("low_weekly")
        w_vol = d.get("volume_weekly")
        if w_close is not None and w_high is not None and w_low is not None:
            wk, wd, wj = _calc_kdj(w_high, w_low, w_close)
            wkdj_sig = detectKDJSignal(wk, wd, wj)[0]
        # Weekly volume > 60-week MA for confirmation
        wkdj_vol_ok = False
        if w_vol is not None and len(w_vol) >= 60:
            wkdj_vol_ok = w_vol.iloc[-1] > w_vol.rolling(60).mean().iloc[-1]
        wkdj_ok = wkdj_sig is not None and wkdj_vol_ok
        if wkdj_ok:
            score += 1
        details["wkdj_sig"] = wkdj_sig or ""

        # 6. Volatility > threshold (+1)
        vol_ok = False
        if len(close) >= vol_period:
            returns = close.pct_change().dropna()
            if len(returns) >= vol_period:
                ann_vol = returns.iloc[-vol_period:].std() * (252 ** 0.5) * 100
                vol_ok = ann_vol > vol_threshold
        if vol_ok:
            score += 1
        details["vol_ok"] = vol_ok

        # 7. Volume MA > threshold (+1)
        vol_ma_ok = False
        if vol is not None and len(vol) >= vol_ma_bars:
            vol_ma_ok = vol.rolling(vol_ma_bars).mean().iloc[-1] > vol_ma_threshold
        if vol_ma_ok:
            score += 1
        details["vol_ma_ok"] = vol_ma_ok

        # 8. Vol MA20 > Vol MA60 (+1) — volume expansion
        vol_expand = False
        if vol is not None and len(vol) >= 60:
            ma20 = vol.rolling(20).mean().iloc[-1]
            ma60 = vol.rolling(60).mean().iloc[-1]
            vol_expand = ma20 > ma60
        if vol_expand:
            score += 1
        details["vol_expand"] = vol_expand

        # 9. EMA Alignment: 50 > 100 > 200 (+1) — perfect bullish alignment
        aligned = False
        if all(sp in ema for sp in (50, 100, 200)):
            e50, e100, e200 = ema[50].iloc[-1], ema[100].iloc[-1], ema[200].iloc[-1]
            if not any(pd.isna(v) for v in (e50, e100, e200)):
                aligned = e50 > e100 > e200
        if aligned:
            score += 1
        details["aligned"] = aligned

        # 10. Bollinger Band squeeze: BB width at 20-bar low (+1)
        bb_squeeze = False
        if 20 in ema:
            bb_mid = ema[20]
            bb_std = close.rolling(20).std()
            bb_width = (4 * bb_std) / bb_mid
            if len(bb_width.dropna()) >= 20:
                bb_now = bb_width.iloc[-1]
                bb_min_20 = bb_width.iloc[-20:].min()
                bb_squeeze = bb_now <= bb_min_20 * 1.01  # within 1% of 20-bar low
        if bb_squeeze:
            score += 1
        details["bb_squeeze"] = bb_squeeze

        # 11. Volume spike: today vol > 2x 20-day avg vol (+1)
        vol_spike = False
        if vol is not None and len(vol) >= 20:
            avg20 = vol.rolling(20).mean().iloc[-1]
            today_vol = vol.iloc[-1]
            vol_spike = avg20 > 0 and today_vol > 2 * avg20
        if vol_spike:
            score += 1
        details["vol_spike"] = vol_spike

        name = d.get("name", "") or ticker_names.get(tkr, "")
        results.append({
            "ticker": tkr,
            "name": name,
            "close": round(close.iloc[-1], 2),
            "score": score,
            "above_200": "Y" if above_200 else "",
            "ema200_up": "Y" if slope_up else "",
            "trend_tight": "Y" if trend_tight else "",
            "kdj_sig": kdj_sig or "",
            "wkdj_sig": wkdj_sig or "",
            "vol_ok": "Y" if vol_ok else "",
            "vol_ma_ok": "Y" if vol_ma_ok else "",
            "vol_expand": "Y" if vol_expand else "",
            "aligned": "Y" if aligned else "",
            "bb_squeeze": "Y" if bb_squeeze else "",
            "vol_spike": "Y" if vol_spike else "",
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    print(f"  Scored {len(results)} stocks, top score: {results[0]['score'] if results else 0}")
    return results[:top_n]


def backtest_scoring(data: dict[str, dict[str, Any]], ticker_names=None,
                     trend_periods=SCORE_TREND_PERIODS,
                     trend_threshold=SCORE_TREND_THRESHOLD,
                     ema200_slope_bars=SCORE_EMA200_SLOPE_BARS,
                     vol_period=SCORE_VOL_PERIOD,
                     vol_threshold=SCORE_VOL_THRESHOLD,
                     vol_ma_bars=SCORE_VOL_MA_BARS,
                     vol_ma_threshold=SCORE_VOL_MA_THRESHOLD,
                     top_n=20, interval_weeks=2, min_bars_needed=250):
    """
    Backtest the scoring system over historical data.
    Every `interval_weeks`, scores stocks using only data available at that date,
    then tracks forward returns at 1w, 2w, 4w.
    Returns list of {date, avg_1w, avg_2w, avg_4w, win_1w, win_2w, win_4w, top_tickers}.
    """
    ticker_names = ticker_names or {}

    # Find stocks with enough data
    valid_tkrs = [tkr for tkr, d in data.items() if len(d.get("close", [])) >= min_bars_needed]
    if len(valid_tkrs) < top_n:
        print(f"  Only {len(valid_tkrs)} stocks with >= {min_bars_needed} bars, need {top_n}")
        return []

    # Build time index from a reference stock
    ref_close = data[valid_tkrs[0]]["close"]
    all_dates = ref_close.index

    # Generate test dates (every interval_weeks, excluding last 4 weeks for forward returns)
    test_dates = []
    for i in range(min_bars_needed, len(all_dates) - 20, interval_weeks * 5):
        test_dates.append(all_dates[i])
    if not test_dates:
        return []

    print(f"  Backtesting {len(test_dates)} dates, {len(valid_tkrs)} stocks ...")
    results = []

    for test_date in test_dates:
        # Build truncated data for this date
        snap_data = {}
        for tkr in valid_tkrs:
            d = data[tkr]
            loc = d["close"].index.get_loc(test_date)
            if isinstance(loc, slice) or isinstance(loc, np.ndarray):
                continue
            snap_data[tkr] = {
                "close": d["close"].iloc[:loc + 1],
                "high": d["high"].iloc[:loc + 1],
                "low": d["low"].iloc[:loc + 1],
                "volume": d["volume"].iloc[:loc + 1] if d.get("volume") is not None else None,
                "name": d.get("name", ""),
            }
        if len(snap_data) < top_n:
            continue

        # Score
        scored = run_scoring_screener(
            snap_data, ticker_names,
            trend_periods=trend_periods, trend_threshold=trend_threshold,
            ema200_slope_bars=ema200_slope_bars,
            vol_period=vol_period, vol_threshold=vol_threshold,
            vol_ma_bars=vol_ma_bars, vol_ma_threshold=vol_ma_threshold,
            top_n=top_n,
        )

        # Track forward returns
        fwd_1w = []
        fwd_2w = []
        fwd_4w = []
        for r in scored:
            tkr = r["ticker"]
            full_close = data[tkr]["close"]
            entry_price = r["close"]
            try:
                loc = full_close.index.get_loc(test_date)
                if isinstance(loc, slice) or isinstance(loc, np.ndarray):
                    continue
                for horizon_days, fwd_list in [(5, fwd_1w), (10, fwd_2w), (20, fwd_4w)]:
                    fwd_idx = loc + horizon_days
                    if fwd_idx < len(full_close):
                        exit_price = full_close.iloc[fwd_idx]
                        ret_pct = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0
                        fwd_list.append(ret_pct)
            except (KeyError, IndexError):
                pass

        results.append({
            "date": test_date.strftime("%Y-%m-%d"),
            "top_tickers": ", ".join(r["ticker"].replace(".KL", "") for r in scored[:5]),
            "avg_1w": round(np.mean(fwd_1w), 2) if fwd_1w else 0,
            "avg_2w": round(np.mean(fwd_2w), 2) if fwd_2w else 0,
            "avg_4w": round(np.mean(fwd_4w), 2) if fwd_4w else 0,
            "win_1w": round(sum(1 for r in fwd_1w if r > 0) / len(fwd_1w) * 100, 1) if fwd_1w else 0,
            "win_2w": round(sum(1 for r in fwd_2w if r > 0) / len(fwd_2w) * 100, 1) if fwd_2w else 0,
            "win_4w": round(sum(1 for r in fwd_4w if r > 0) / len(fwd_4w) * 100, 1) if fwd_4w else 0,
        })

    return results


def _write_csv(results, prefix, cols, sort_key, output_dir=OUTPUT_DIR):
    # type: (list[dict[str, Any]], str, list[str], Callable[[dict[str, Any]], Any], str) -> str
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
    print(f"  EMA: {EMA_PERIODS} | divergence < {DIVERGENCE_THRESHOLD}%")
    print(f"  Compression >= {MIN_COMPRESSION_BARS} bars | Vol daily>{VOL_MIN//1000}k hourly>{VOL_MIN_HOURLY//1000}k")
    print(f"  KDJ divergence {DIVERGENCE_LOOKBACK}d")
    print("=" * 56)
    print()

    tickers = load_tickers(TICKERS_FILE)
    data = download_data(tickers)

    all_results = []

    # ── Script 1: Daily EMA Compression ─────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [1/3] Daily EMA Compression")
    print(f"        divergence <= {DIVERGENCE_THRESHOLD}% for >= {MIN_COMPRESSION_BARS} days")
    print("=" * 56)
    for r in run_ema_screener(data, tickers):
        r["script"] = "ema_daily"
        all_results.append(r)

    # ── Script 2: KDJ Divergence ────────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [2/3] KDJ Bullish Divergence  (price down, KDJ up)")
    print(f"        lookback {DIVERGENCE_LOOKBACK} days")
    print("=" * 56)
    for r in run_divergence_screener(data, tickers):
        r["script"] = "kdj_divergence"
        all_results.append(r)

    # ── Script 3: Hourly EMA Compression ────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [3/3] Hourly EMA Compression")
    print(f"        divergence <= {DIVERGENCE_THRESHOLD}% for >= {MIN_COMPRESSION_BARS} hours")
    print("=" * 56)
    for r in run_ema_hourly_screener(data, tickers):
        r["script"] = "ema_hourly"
        all_results.append(r)

    # ── Write combined CSV ──────────────────────────────────────────────────
    print("\n" + "=" * 56)
    ema_cols = [f"EMA{p}" for p in EMA_PERIODS]
    combined_cols = ["script", "ticker", "name", "close"] + ema_cols + [
        "divergence_pct", "kdj_k", "kdj_d", "kdj_j",
        "price_slope", "kdj_k_slope", "vol_ma", "trend"]
    _write_csv(all_results, "screener_combined", combined_cols,
               sort_key=lambda r: (
                   0 if r["script"] == "ema_daily" else
                   1 if r["script"] == "ema_hourly" else 2,
                   r.get("divergence_pct", 999),
               ))

    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CANCEL] Screener cancelled by user.")
        sys.exit(0)
