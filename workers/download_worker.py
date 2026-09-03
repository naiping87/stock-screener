"""Background worker for downloading market data via Yahoo Finance.

Results are cached locally per market + day, so re-opening the app (or
hitting Run again the same day) loads from cache instantly instead of
re-downloading thousands of tickers.
"""

import logging
import os
import pickle
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt6.QtCore import QThread, pyqtSignal

from markets import get as get_market
from market_session import session_mode
from screener import DownloadCancelled, download_data, load_tickers
from utils import cache_dir, resource_path

logger = logging.getLogger(__name__)


def _cache_path(market_code: str) -> str:
    """Per-market, per-day cache file, e.g. <cache>/my_2026-08-04.pkl."""
    return os.path.join(cache_dir(), f"{market_code}_{datetime.now():%Y-%m-%d}.pkl")


def _load_cache(path: str):
    """Return (data, ticker_names) from cache, or None on any failure."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning("Cache read failed (%s): %s", path, e)
        return None


def _save_cache(path: str, data, ticker_names) -> None:
    """Best-effort write; a failed cache write must never break the app.

    Never persist an empty/zero-ticker result — otherwise a failed download
    (e.g. a rate-limited provider) poisons the day-cache and the app keeps
    loading an empty result on every subsequent Run.
    """
    if not data:
        logger.warning("Skipping cache write: no data for %s", path)
        return
    try:
        with open(path, "wb") as f:
            pickle.dump((data, ticker_names), f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.warning("Cache write failed (%s): %s", path, e)


class DownloadWorker(QThread):
    """Downloads market data in a background thread, emitting progress.

    Tries the local day-cache first; only downloads when the cache is missing.
    Supports cooperative cancellation via cancel().
    """

    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(dict, dict)  # (data, ticker_names)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, market_code: str, parent=None, force_refresh: bool = False):
        super().__init__(parent)
        self.market_code = market_code
        # True = bypass the day-cache and re-download fresh data
        # (used by the Refresh Data / auto-refresh actions)
        self.force_refresh = force_refresh
        self.cancel_requested = False
        self._cancel_event = threading.Event()

    def cancel(self):
        """Request cancellation; the worker stops at the next check point."""
        self.cancel_requested = True
        self._cancel_event.set()

    def run(self):
        try:
            m = get_market(self.market_code)
            cache_p = _cache_path(self.market_code)

            # ── Fast path: reuse today's cache (unless force_refresh) ───
            # Only reuse a cache that actually holds data; an empty cache from
            # a blocked/failed download is ignored so it re-downloads fresh.
            cached = _load_cache(cache_p)
            if cached is not None and cached[0] and not self.force_refresh:
                data, ticker_names = cached
                self.progress.emit(95, f"Loaded {len(data)} tickers from cache")
                self.progress.emit(100, "Ready")
                self.finished.emit(data, ticker_names)
                return

            # ── Slow path: download, then persist to cache ──────────────
            tickers_path = resource_path(m.tickers_csv)

            self.progress.emit(5, f"Loading {self.market_code.upper()} tickers...")
            tickers = load_tickers(tickers_path, suffix=m.yahoo_suffix)
            ticker_names = dict(tickers)

            n = len(tickers)
            self.progress.emit(10, f"Downloading {n} tickers ({m.label})...")

            last_pct = [10]

            def progress_cb(current, total):
                if self.cancel_requested:
                    raise DownloadCancelled()
                pct = 10 + int((current / max(total, 1)) * 80)
                if pct > last_pct[0]:
                    last_pct[0] = pct
                    self.progress.emit(pct, f"Downloading... {current}/{total}")

            # EOD-only: complete a trailing null close from Yahoo's quote price
            # so a post-market review isn't stuck on a prior valid day. Never
            # backfill intraday (the daily bar isn't closed yet).
            backfill_quote_close = False
            try:
                _tz = ZoneInfo(m.timezone)
                _sess = session_mode(self.market_code, datetime.now(tz=_tz), m.timezone)
                backfill_quote_close = (_sess == "eod")
            except Exception:
                backfill_quote_close = False  # conservative: no backfill if unsure

            data = download_data(
                tickers,
                progress_cb=progress_cb,
                timezone=m.timezone,
                market_code=self.market_code,
                data_provider=getattr(m, "data_provider", "yahoo"),
                cancel_event=self._cancel_event,
                backfill_quote_close=backfill_quote_close,
            )

            if self.cancel_requested:
                self.cancelled.emit()
                return

            _save_cache(cache_p, data, ticker_names)
            self.progress.emit(95, f"Download complete — {len(data)} tickers (cached)")
            self.progress.emit(100, "Ready")
            self.finished.emit(data, ticker_names)

        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as e:
            logger.exception("Download failed for %s", self.market_code)
            self.error.emit(str(e))
