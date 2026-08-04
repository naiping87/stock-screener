"""Background worker for downloading market data via Yahoo Finance.

Results are cached locally per market + day, so re-opening the app (or
hitting Run again the same day) loads from cache instantly instead of
re-downloading thousands of tickers.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from screener import download_data, load_tickers
from markets import get as get_market
import os, sys, pickle
from datetime import datetime
from utils import resource_path, cache_dir


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
    except Exception:
        return None


def _save_cache(path: str, data, ticker_names) -> None:
    """Best-effort write; a failed cache write must never break the app."""
    try:
        with open(path, "wb") as f:
            pickle.dump((data, ticker_names), f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


class DownloadWorker(QThread):
    """Downloads market data in a background thread, emitting progress.

    Tries the local day-cache first; only downloads when the cache is missing.
    """

    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(dict, dict)  # (data, ticker_names)
    error = pyqtSignal(str)

    def __init__(self, market_code: str, parent=None, force_refresh: bool = False):
        super().__init__(parent)
        self.market_code = market_code
        # True = bypass the day-cache and re-download fresh data
        # (used by the Refresh Data / auto-refresh actions)
        self.force_refresh = force_refresh

    def run(self):
        try:
            m = get_market(self.market_code)
            cache_p = _cache_path(self.market_code)

            # ── Fast path: reuse today's cache (unless force_refresh) ───
            cached = _load_cache(cache_p)
            if cached is not None and not self.force_refresh:
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
                pct = 10 + int((current / max(total, 1)) * 80)
                if pct > last_pct[0]:
                    last_pct[0] = pct
                    self.progress.emit(pct, f"Downloading... {current}/{total}")

            data = download_data(
                tickers,
                progress_cb=progress_cb,
                timezone=m.timezone,
                market_code=self.market_code,
                data_provider="yahoo",
            )

            _save_cache(cache_p, data, ticker_names)
            self.progress.emit(95, f"Download complete — {len(data)} tickers (cached)")
            self.progress.emit(100, "Ready")
            self.finished.emit(data, ticker_names)

        except Exception as e:
            self.error.emit(str(e))
