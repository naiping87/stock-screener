"""
Bursa Malaysia Stock Screener — 5 screeners:
  1. ema_daily      — daily EMA 10/20/50/100/200 compressed <3% for 20+ days
  2. ema_hourly     — hourly EMA 10/20/50/100/200 compressed <3% for 20+ hours
  3. kdj_divergence — price falling, KDJ rising over 30 days
  4. weekly_kdj     — weekly KDJ golden cross / near-cross
  5. scoring        — weighted 11-factor scoring system
"""
import csv
import io
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests

from indicators.gm_kdj import gm_kdj, kdj_state, kdj_cross, kdj_divergence

try:
    import akshare as ak
except Exception:  # akshare 是可选的;导入失败(ImportError/FileNotFoundError 等)时降级为 None
    ak = None

logger = logging.getLogger(__name__)


class DownloadCancelled(Exception):
    """Raised inside download_data when the caller requests cancellation.

    The worker threads catch this and emit a `cancelled` signal instead of
    treating it as a download failure.
    """

# ── Configuration ────────────────────────────────────────────────────────────
EMA_PERIODS = [10, 20, 50, 100, 200]
DIVERGENCE_THRESHOLD = 3.0          # percent
VOL_MIN = 500000                    # min daily volume MA
VOL_MIN_HOURLY = 100000             # min hourly volume MA
VOL_MIN_WEEKLY_EMA = 500000         # min weekly volume MA (EMA screener)
MAX_WORKERS = 15                    # concurrent download threads
REQUEST_DELAY = 0.0                 # seconds between requests per thread
MAX_RETRIES = 3
MIN_COMPRESSION_BARS = 20           # SMAs must be tight for this many bars
KDJ_PERIOD = 26                     # KDJ lookback (same as Pine Script 'Period')
KDJ_SIGNAL = 5                      # KDJ smooth (same as Pine Script 'Signal Period')
DIVERGENCE_LOOKBACK = 30            # bars for KDJ/price divergence detection
DAILY_DAYS = 400                    # days of daily data (max EMA period 200 + 20 compression bars)
HOURLY_DAYS = 50                    # days of hourly data
WEEKLY_DAYS = 1600                  # days of weekly (1wk) history — enough for weekly EMA200 + 20 compression bars
MIN_WEEKLY_BARS = max(EMA_PERIODS) + MIN_COMPRESSION_BARS  # weekly bars needed for EMA200 compression
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
SCORE_TOP_N = 100                   # top N results to show (max 300)
SCORE_MIN = 0                       # min total score to show (0 = show top N)
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
        # Never sys.exit() here: in the GUI this kills the whole process.
        # Raise instead so the caller (QThread) can surface a friendly error.
        raise FileNotFoundError(f"tickers file not found: {path}")

    tickers = {}
    # 本地 tickers CSV 有 utf-8（Bursa/US）与 gb18030（A 股）两种编码。
    # open() 的解码是惰性的，须先读字节再显式解码回退。
    def _read_text() -> str:
        with open(path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8", "gb18030"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    with io.StringIO(_read_text()) as f:
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
    logger.info("Loaded %d tickers", len(tickers))
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


def _fetch_ticker(sess, tkr, dp1, dp2, hp1, hp2, wp1, wp2, min_bars_d, min_bars_h, min_bars_w, timezone="Asia/Kuala_Lumpur", daily_only=False):
    """Download daily + hourly + weekly(1wk) data for one ticker."""
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

    # A-shares load fast: daily only, weekly derived from daily (no hourly).
    if daily_only:
        try:
            w_close = result["close"].resample("W").last()
            w_high = result["high"].resample("W").max()
            w_low = result["low"].resample("W").min()
            w_vol = result["volume"].resample("W").sum()
            wk_idx = w_close.index.intersection(w_high.index).intersection(w_low.index).intersection(w_vol.index)
            result["close_weekly"] = w_close.loc[wk_idx]
            result["high_weekly"] = w_high.loc[wk_idx]
            result["low_weekly"] = w_low.loc[wk_idx]
            result["volume_weekly"] = w_vol.loc[wk_idx]
        except Exception:
            pass
        return tkr, result

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


    # Weekly data — fetch 1wk interval directly (long history needed for weekly EMA200)
    try:
        w_data, _ = _fetch_chart(sess, tkr, wp1, wp2, "1wk", min_bars_w, timezone)
        if w_data is not None:
            w_close = w_data["close"].dropna()
            w_high = w_data["high"].dropna()
            w_low = w_data["low"].dropna()
            w_vol = w_data["volume"].fillna(0)
            wi = w_close.index.intersection(w_high.index).intersection(w_low.index).intersection(w_vol.index)
            if len(wi) >= min_bars_w:
                result["close_weekly"] = w_close.loc[wi]
                result["high_weekly"] = w_high.loc[wi]
                result["low_weekly"] = w_low.loc[wi]
                result["volume_weekly"] = w_vol.loc[wi]
    except Exception:
        pass

    return tkr, result


def download_data(tickers: dict[str, str], progress_cb: Callable[[int, int], None] | None = None, timezone: str = "Asia/Kuala_Lumpur", market_code: str = "my", data_provider: str = "yahoo", cancel_event: threading.Event | None = None) -> dict[str, dict[str, Any]]:
    """Download daily + hourly + weekly data concurrently via Yahoo chart API.

    `cancel_event` (optional): when set, the loop raises DownloadCancelled at
    the next check so the caller can abort without treating it as an error.
    """
    if data_provider == "akshare":
        # AkShare (East Money) is frequently blocked / rate-limited (each call
        # wastes ~1s failing on 1700 tickers, which is very slow).  So prefer a
        # fast daily-only Yahoo pull; only fall back to AkShare if Yahoo itself
        # is unavailable (e.g. a buyer's network where Yahoo is blocked).
        data = _download_yahoo(tickers, timezone, progress_cb, cancel_event, daily_only=True)
        min_ok = max(1, int(len(tickers) * 0.2))
        if len(data) < min_ok:
            logger.warning("[YAHOO] only %d/%d tickers returned; trying AkShare",
                           len(data), len(tickers))
            data = _download_akshare(tickers, timezone, progress_cb, cancel_event)
        return data
    return _download_yahoo(tickers, timezone, progress_cb, cancel_event)


def _download_yahoo(tickers: dict[str, str], timezone: str, progress_cb=None, cancel_event=None, daily_only: bool = False) -> dict[str, dict[str, Any]]:
    """Download daily + hourly + weekly data concurrently via Yahoo chart API.

    `cancel_event` (optional): when set, the loop raises DownloadCancelled at
    the next check so the caller can abort without treating it as an error.
    `daily_only` (option): skip hourly/weekly network calls and derive weekly
    from daily — much faster, used for large A-share universes.
    """
    end_date = datetime.now()
    d_start = end_date - timedelta(days=DAILY_DAYS)
    h_start = end_date - timedelta(days=HOURLY_DAYS)
    w_start = end_date - timedelta(days=WEEKLY_DAYS)
    dp1, dp2 = int(d_start.timestamp()), int(end_date.timestamp())
    hp1, hp2 = int(h_start.timestamp()), int(end_date.timestamp())
    wp1, wp2 = int(w_start.timestamp()), int(end_date.timestamp())
    min_bars_d = max(EMA_PERIODS) + MIN_COMPRESSION_BARS
    # Hourly: Yahoo may return fewer bars; cap requirement at EMA50+compression
    min_bars_h = 50 + MIN_COMPRESSION_BARS
    min_bars_w = MIN_WEEKLY_BARS

    ticker_list = sorted(tickers.keys())
    all_data = {}
    session = _build_session()

    n_fetch = "1d" if daily_only else "1d + 1h + 1w"
    logger.info("[DOWNLOAD] Fetching %s for %d tickers (workers=%d)",
                n_fetch, len(ticker_list), MAX_WORKERS)

    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        futures = {
            pool.submit(
                _fetch_ticker, session, tkr,
                dp1, dp2, hp1, hp2, wp1, wp2,
                min_bars_d, min_bars_h, min_bars_w, timezone,
                daily_only,
            ): tkr
            for tkr in ticker_list
        }
        done = 0
        for f in as_completed(futures):
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled()
            tkr, data = f.result()
            if data is not None:
                all_data[tkr] = data
            done += 1
            if progress_cb:
                progress_cb(done, len(ticker_list))
            elif done % 100 == 0:
                logger.info("  %d/%d tickers processed ...", done, len(ticker_list))
            time.sleep(REQUEST_DELAY)
    finally:
        # wait=False + cancel_futures: don't block the UI thread on abort;
        # in-flight requests finish in daemon threads (Python >= 3.9).
        pool.shutdown(wait=False, cancel_futures=True)

    logger.info("[DATA] Got price history for %d / %d tickers", len(all_data), len(tickers))
    return all_data
def _fetch_akshare_ticker(tkr, name, days, timezone):
    """Download daily data for one A-share ticker via AkShare. Returns dict or None."""
    if ak is None:
        return None
    # Internal keys carry the market suffix (e.g. "600000.SS"); akshare wants the bare code.
    symbol = tkr.split(".")[0]
    end_str = datetime.now().strftime("%Y%m%d")
    start_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_str,
                                    end_date=end_str, adjust="qfq")
            if df is None or len(df) < 20:
                return None
            df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                    "最高": "high", "最低": "low", "成交量": "volume"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            tz_idx = df.index.tz_localize(timezone) if df.index.tz is None else df.index.tz_convert(timezone)
            def _s(col, df=df, tz_idx=tz_idx):
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


def _download_akshare(tickers, timezone, progress_cb=None, cancel_event=None):
    all_data = {}
    ticker_list = sorted(tickers.keys())
    ak_workers = min(MAX_WORKERS, 15)
    logger.info('[AKSHARE] Fetching %dd daily for %d tickers (workers=%d) ...',
                DAILY_DAYS, len(ticker_list), ak_workers)
    pool = ThreadPoolExecutor(max_workers=ak_workers)
    try:
        futures = {pool.submit(_fetch_akshare_ticker, tkr, tickers[tkr], DAILY_DAYS, timezone): tkr for tkr in ticker_list}
        done = 0
        for f in as_completed(futures):
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled()
            tkr = futures[f]
            data = f.result()
            if data is not None:
                all_data[tkr] = data
            done += 1
            if progress_cb:
                progress_cb(done, len(ticker_list))
            elif done % 200 == 0:
                logger.info('  %d/%d ...', done, len(ticker_list))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    logger.info('[AKSHARE] Got data for %d / %d tickers', len(all_data), len(tickers))
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
    """Calculate KDJ (K, D, J) — delegates to indicators.gm_kdj (Pine-parity)."""
    needed = period + signal
    if daily_high is None or daily_low is None or daily_close is None or len(daily_close) < needed:
        return None, None, None
    out = gm_kdj(daily_high, daily_low, daily_close, period=period, signal=signal)
    return out["k"], out["d"], out["j"]


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

    logger.info("  Stage 1 (%s compression): %d passed", label, s1)
    logger.info("  Stage 2 (%s vol > %dk): %d passed", label, vol_min // 1000, s2)


def run_ema_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                     periods: list[int] | None = None,
                     threshold: float = DIVERGENCE_THRESHOLD,
                     min_compression: int = MIN_COMPRESSION_BARS,
                     min_vol: int = VOL_MIN) -> Generator[dict[str, Any], None, None]:
    """
    EMA Compression Screener (daily):
      Stage 1 — EMA divergence <= threshold% for >= min_compression bars
      Stage 2 — daily volume MA > min_vol
    """
    yield from _run_ema_screener_impl(
        data, ticker_names, periods, threshold, min_compression,
        close_key="close", vol_key="volume", vol_min=min_vol, label="daily",
    )


def run_ema_hourly_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            periods: list[int] | None = None,
                            threshold: float = DIVERGENCE_THRESHOLD,
                            min_compression: int = MIN_COMPRESSION_BARS,
                            min_vol: int = VOL_MIN_HOURLY) -> Generator[dict[str, Any], None, None]:
    """
    EMA Compression Screener (hourly):
      Stage 1 — EMA divergence <= threshold% for >= min_compression bars
      Stage 2 — hourly volume MA > min_vol
    """
    yield from _run_ema_screener_impl(
        data, ticker_names, periods, threshold, min_compression,
        close_key="close_hourly", vol_key="volume_hourly",
        vol_min=min_vol, label="hourly",
    )


def run_ema_weekly_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            periods: list[int] | None = None,
                            threshold: float = DIVERGENCE_THRESHOLD,
                            min_compression: int = MIN_COMPRESSION_BARS,
                            min_vol: int = VOL_MIN_WEEKLY_EMA) -> Generator[dict[str, Any], None, None]:
    """
    EMA Compression Screener (weekly):
      Stage 1 — EMA divergence <= threshold% for >= min_compression bars
      Stage 2 — weekly volume MA > min_vol
    """
    yield from _run_ema_screener_impl(
        data, ticker_names, periods, threshold, min_compression,
        close_key="close_weekly", vol_key="volume_weekly",
        vol_min=min_vol, label="weekly",
    )





def run_divergence_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                            lookback: int = DIVERGENCE_LOOKBACK,
                            min_vol: int = VOL_MIN) -> Generator[dict[str, Any], None, None]:
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

        if not _check_volume(d.get("volume"), min_vol=min_vol):
            continue
        s2 += 1

        vol = d.get("volume")
        vol_ma_val = int(vol.rolling(20).mean().iloc[-1]) if vol is not None and len(vol) >= 20 else 0

        name = d.get("name", "") or ticker_names.get(tkr, "")
        price = round(d["close"].iloc[-1], 2)

        # Standardised KDJ taxonomy (P1): add canonical state + pivot divergence
        # alongside the existing slope divergence.
        k_series, d_series, _ = _calc_kdj(d["high"], d["low"], d["close"],
                                          period=KDJ_PERIOD, signal=KDJ_SIGNAL)
        kdj_st = kdj_state(k_series, d_series)["state"] if k_series is not None else ""
        pivot_div = (kdj_divergence(d["close"], k_series, lookback=lookback)["pivot_bullish"]
                     if k_series is not None else False)

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "price_slope": price_slope,
            "kdj_k_slope": k_slope,
            "kdj_state": kdj_st,
            "kdj_pivot_div": pivot_div,
            "vol_ma": vol_ma_val,
        }

    logger.info("  Stage 1 (divergence): %d passed", s1)
    logger.info("  Stage 2 (vol > %dk): %d passed", VOL_MIN // 1000, s2)


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
        kdj_st = kdj_state(k, d_kdj)["state"]
        kd_golden = kdj_cross(k, d_kdj, j)["k_d_golden"]

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "kdj_signal": kdj_sig,
            "kdj_state": kdj_st,
            "kdj_k_d_golden": kd_golden,
            "vol_ma": vol_ma_val,
        }

    logger.info("  Stage 1 (weekly KDJ cross): %d passed", s1)
    logger.info("  Stage 2 (weekly vol > %dk): %d passed", vol_min // 1000, s2)


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
        kdj_st = kdj_state(k, d_kdj)["state"]
        kd_golden = kdj_cross(k, d_kdj, j)["k_d_golden"]

        yield {
            "ticker": tkr,
            "name": name,
            "close": price,
            "kdj_k": k_val,
            "kdj_d": d_val,
            "kdj_j": j_val,
            "kdj_signal": kdj_sig,
            "kdj_state": kdj_st,
            "kdj_k_d_golden": kd_golden,
            "vol_ratio": vol_ratio_val,
            "vol_ma": vol_ma_val,
        }

    logger.info("  Stage 1 (daily KDJ cross): %d passed", s1)
    logger.info("  Stage 2 (vol MA > %dk): %d passed", vol_min // 1000, s2)


def run_scoring_screener(data: dict[str, dict[str, Any]], ticker_names: dict[str, str] | None = None,
                         trend_periods: list[int] = SCORE_TREND_PERIODS,
                         trend_threshold: float = SCORE_TREND_THRESHOLD,
                         ema200_slope_bars: int = SCORE_EMA200_SLOPE_BARS,
                         vol_period: int = SCORE_VOL_PERIOD,
                         vol_threshold: float = SCORE_VOL_THRESHOLD,
                         vol_ma_bars: int = SCORE_VOL_MA_BARS,
                         vol_ma_threshold: int = SCORE_VOL_MA_THRESHOLD,
                         top_n: int = SCORE_TOP_N,
                         min_score: int = SCORE_MIN,
                         components: bool = False) -> list[dict[str, Any]]:
    """
    Weighted Scoring Screener — scores every stock on 11 factors.
    Returns top_n stocks sorted by total score descending. When min_score > 0,
    every stock with score >= min_score is kept (top_n is then just a cap),
    so early-stage candidates below the old cutoff are not missed.
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
        row = {
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
        }
        if components:
            # De-redundant breakdown: cluster the 11 booleans into 5 themes so
            # the score is explainable and not double-counting one idea.
            row["score_components"] = {
                "trend": int(above_200) + int(slope_up) + int(aligned),
                "compression": int(trend_tight) + int(bb_squeeze),
                "momentum": int(kdj_ok) + int(wkdj_ok),
                "volume": int(vol_expand) + int(vol_spike),
                "activity": int(vol_ok) + int(vol_ma_ok),
            }
            # Fixed, explainable weights (NOT tuned vs the backtest). Sums to 100.
            row["score_weighted"] = sum(
                _w for _flag, _w in (
                    (above_200, 10), (slope_up, 8), (trend_tight, 12),
                    (kdj_ok, 9), (wkdj_ok, 9), (vol_ok, 4),
                    (vol_ma_ok, 5), (vol_expand, 8), (aligned, 8),
                    (bb_squeeze, 12), (vol_spike, 15),
                ) if _flag)
        results.append(row)

    results.sort(key=lambda r: r["score"], reverse=True)
    logger.info("  Scored %d stocks, top score: %s", len(results), results[0]["score"] if results else 0)
    if min_score > 0:
        results = [r for r in results if r["score"] >= min_score]
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
        logger.warning("  Only %d stocks with >= %d bars, need %d", len(valid_tkrs), min_bars_needed, top_n)
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

    logger.info("  Backtesting %d dates, %d stocks ...", len(test_dates), len(valid_tkrs))
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
    logger.info("  -> %d stocks saved to %s", len(results), path)
    return path


def main():
    print("=" * 56)
    print("  Bursa Malaysia Stock Screener  (3 scripts, 1 output)")
    print(f"  EMA: {EMA_PERIODS} | divergence < {DIVERGENCE_THRESHOLD}%")
    print(f"  Compression >= {MIN_COMPRESSION_BARS} bars | Vol daily>{VOL_MIN//1000}k hourly>{VOL_MIN_HOURLY//1000}k weekly>{VOL_MIN_WEEKLY_EMA//1000}k")
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

