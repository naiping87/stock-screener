"""Background worker for downloading market data via Yahoo Finance."""

from PyQt6.QtCore import QThread, pyqtSignal
from screener import download_data, load_tickers
from markets import get as get_market
import os


class DownloadWorker(QThread):
    """Downloads market data in a background thread, emitting progress."""

    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(dict, dict)  # (data, ticker_names)
    error = pyqtSignal(str)

    def __init__(self, market_code: str, parent=None):
        super().__init__(parent)
        self.market_code = market_code

    def run(self):
        try:
            m = get_market(self.market_code)
            tickers_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), m.tickers_csv)

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

            self.progress.emit(95, f"Download complete — {len(data)} tickers")
            self.progress.emit(100, "Ready")
            self.finished.emit(data, ticker_names)

        except Exception as e:
            self.error.emit(str(e))
