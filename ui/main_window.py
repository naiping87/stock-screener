"""Main window — menu, status bar, sidebar + results tab layout."""

import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
)

from tools.new_stock_monitor import AnnouncementBoard, normalize_code, run_once
from utils import cache_dir
from workers.alert_worker import AlertWorker
from workers.download_worker import DownloadWorker
from workers.meta_worker import MetaWorker
from workers.screener_worker import ScreenerWorker

from .results_panel import ResultsPanel
from .sidebar import Sidebar
from .system_tray import SystemTray

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Screener Pro")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)
        self.data = {}
        self.ticker_names = {}
        self._result_dfs = {}
        self._meta_cache = {}
        self._busy = False            # a download / screener run is in flight
        self._last_market_code = None
        self._retry_cb = None         # callback for the status-bar Retry button

        settings = QSettings("StockScreenerPro", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self._setup_menu()
        self._setup_statusbar()
        self._setup_central()
        self._setup_tray()
        self._refresh_new_listings()

    def _setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        refresh_action = QAction("&Refresh Data", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

        export_action = QAction("&Export CSV...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.hide()
        self.statusbar.addPermanentWidget(self.progress_bar)

        # Cancel button — visible only while a worker is running
        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #f23645; border: 1px solid #f23645;"
            " border-radius: 6px; padding: 4px 14px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(242,54,69,0.12); }")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.hide()
        self.statusbar.addPermanentWidget(self.cancel_btn)

        # Retry button — visible after a failed download / screener run
        self.retry_btn = QPushButton("↻ Retry")
        self.retry_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #f7c600; border: 1px solid #f7c600;"
            " border-radius: 6px; padding: 4px 14px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(247,198,0,0.12); }")
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.hide()
        self.statusbar.addPermanentWidget(self.retry_btn)

    def _setup_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = Sidebar()
        splitter.addWidget(self.sidebar)

        self.results_panel = ResultsPanel()
        splitter.addWidget(self.results_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 960])
        self.setCentralWidget(splitter)

        self.sidebar.run_clicked.connect(self._on_run_screeners)
        self.sidebar.market_changed.connect(self._on_market_changed)
        self.sidebar.sector_combo.currentIndexChanged.connect(self._on_sector_changed)
        self.results_panel.ticker_activated.connect(self._open_chart)

        # Alert toggle — persisted across launches
        settings = QSettings("StockScreenerPro", "Alerts")
        self.sidebar.alerts_checkbox.setChecked(settings.value("enabled", True, type=bool))
        self.sidebar.alerts_checkbox.stateChanged.connect(self._on_alerts_toggled)

        # Auto-refresh timer
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._on_refresh)
        self.sidebar.auto_refresh.stateChanged.connect(self._on_auto_refresh_toggled)

    def _setup_tray(self):
        self.tray = SystemTray(self)
        self.tray.show_window.connect(self._show_from_tray)
        self.tray.quit_app.connect(self.close)

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Busy state / feedback ─────────────────────────────────────────────

    def _set_busy(self, busy: bool, text: str = ""):
        """Lock the controls while a worker runs and reflect it on the Run button."""
        self._busy = busy
        self.sidebar.run_btn.setEnabled(not busy)
        self.sidebar.reset_btn.setEnabled(not busy)
        self.sidebar.market_combo.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        if busy:
            self.sidebar.run_btn.setText("⏳ Running…")
            if text:
                self.status_label.setText(text)
        else:
            self.sidebar.run_btn.setText("▶  Run Screeners")
            self._hide_error()

    def _show_error(self, msg: str, retry_cb=None):
        """Non-modal error: red status text + optional Retry button."""
        logger.error("Operation failed: %s", msg)
        self.status_label.setText("⚠ " + msg)
        self.status_label.setStyleSheet("color:#f23645;")
        self._retry_cb = retry_cb
        self.retry_btn.setVisible(retry_cb is not None)

    def _hide_error(self):
        self.status_label.setStyleSheet("")
        self._retry_cb = None
        self.retry_btn.hide()

    def _on_cancel(self):
        for w in (getattr(self, "worker", None),
                  getattr(self, "screener_worker", None),
                  getattr(self, "meta_worker", None)):
            if w is not None and w.isRunning():
                w.cancel()
                self.status_label.setText("Cancelling…")
                return
        self._set_busy(False)

    def _on_retry(self):
        cb = self._retry_cb
        self._hide_error()
        if cb:
            cb()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_run_screeners(self):
        if self._busy:
            return
        if not self.data:
            params = self.sidebar.get_params()
            self._start_download(params["market_code"])
        else:
            self._start_screeners()

    def _start_download(self, market_code, force_refresh=False):
        if self._busy:
            return
        self._last_market_code = market_code
        self._set_busy(True, "Downloading " + market_code.upper() + " market data...")
        self.results_panel.set_all_empty()
        self.worker = DownloadWorker(market_code, force_refresh=force_refresh)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_download_error)
        self.worker.cancelled.connect(self._on_worker_cancelled)
        self.worker.start()

    def _on_data_loaded(self, data, ticker_names):
        self.data = data
        self.ticker_names = ticker_names
        self.status_label.setText("Loaded " + str(len(data)) + " tickers - running screeners...")
        # Internal chain: busy flag stays set, so bypass the guard.
        self._start_screeners()

    def _start_screeners(self):
        """Start the screener pipeline (busy is already set by the caller)."""
        params = self.sidebar.get_params()
        self._result_dfs = {}
        self._set_busy(True, "Running screeners...")
        self.screener_worker = ScreenerWorker(self.data, self.ticker_names, params)
        self.screener_worker.progress.connect(self.update_progress)
        self.screener_worker.result.connect(self._store_result)
        self.screener_worker.finished.connect(self._on_screeners_done)
        self.screener_worker.error.connect(self._on_screener_error)
        self.screener_worker.cancelled.connect(self._on_worker_cancelled)
        self.screener_worker.start()

    def _store_result(self, tab_key, df):
        self._result_dfs[tab_key] = df

    def _on_screeners_done(self):
        # Collect all unique tickers from results
        all_tickers = set()
        for df in self._result_dfs.values():
            if df is None or df.empty:
                continue
            # Need original ticker with suffix for Yahoo lookup
            col = "ticker" if "ticker" in df.columns else "Code"
            if col not in df.columns:
                continue
            for tkr in df[col]:
                all_tickers.add(tkr)

        # Filter to tickers not already cached
        new_tickers = all_tickers - set(self._meta_cache.keys())
        if new_tickers:
            self.meta_worker = MetaWorker(new_tickers)
            self.meta_worker.progress.connect(self.update_progress)
            self.meta_worker.finished.connect(self._on_meta_loaded)
            self.meta_worker.error.connect(
                lambda e: self._show_error("Meta data failed: " + e, self._start_screeners))
            self.meta_worker.cancelled.connect(self._on_worker_cancelled)
            self.meta_worker.start()
        else:
            self._finalize_results()

    def _on_meta_loaded(self, meta):
        self._meta_cache.update(meta)
        self._finalize_results()

    def _finalize_results(self):
        # Attach ROE + sector to each result DataFrame (in-place, fast)
        all_sectors = set()
        for _tab_key, df in self._result_dfs.items():
            if df is None or df.empty:
                continue
            if "ticker" in df.columns:
                tkrs = df["ticker"].values
                df["ROE"] = [self._meta_cache.get(t, {}).get("roe") for t in tkrs]
                df["ROE%"] = [f"{v:.1f}%" if v is not None else "" for v in df["ROE"]]
                df["Sector"] = [self._meta_cache.get(t, {}).get("sector", "") for t in tkrs]
                for s in df["Sector"]:
                    if s:
                        all_sectors.add(s)
        self.sidebar.set_sectors(list(all_sectors))
        # Show all tabs
        self._apply_sector_filter()
        self.status_label.setText("Ready")
        self.update_progress(100, "Ready")
        self._set_busy(False)
        self._maybe_run_alerts()
        self._check_new_listings()

    def _apply_sector_filter(self):
        """Re-render the result tables under the current sector filter.

        Pure filtering — must NOT touch busy/status state, because it is also
        invoked live from the sector combo while a run is in flight.
        """
        sector = self.sidebar.sector_combo.currentData()
        for tab_key, df in self._result_dfs.items():
            if df is None or df.empty:
                self.results_panel.set_results(tab_key, df)
                continue
            if sector and "Sector" in df.columns:
                filtered = df[df["Sector"] == sector]
                self.results_panel.set_results(tab_key, filtered)
            else:
                self.results_panel.set_results(tab_key, df)

    def _on_sector_changed(self):
        self._apply_sector_filter()

    # ── Weekly KDJ alerts ─────────────────────────────────────────────────

    def _on_alerts_toggled(self, state):
        QSettings("StockScreenerPro", "Alerts").setValue("enabled", bool(state))

    def _maybe_run_alerts(self):
        """After a completed run, check for fresh weekly KDJ crosses in the
        background and notify via the system tray (never blocks the UI)."""
        if not self.sidebar.alerts_checkbox.isChecked():
            return
        if not self.data:
            return
        if getattr(self, "alert_worker", None) is not None and self.alert_worker.isRunning():
            return
        vol_min = self.sidebar.vol_weekly.row_widget.value()
        self.alert_worker = AlertWorker(self.data, self.ticker_names, vol_min=vol_min)
        self.alert_worker.finished.connect(self._on_alerts_ready)
        self.alert_worker.error.connect(self._on_alerts_error)
        self.alert_worker.start()

    def _on_alerts_ready(self, alerts):
        n = len(alerts)
        if n == 0:
            return
        logger.info("New weekly KDJ alerts: %d", n)
        if n <= 3:
            for r in alerts:
                name = r.get("name", "")
                tkr = r.get("ticker", "")
                price = r.get("close", "?")
                k, d, j = r.get("kdj_k", "?"), r.get("kdj_d", "?"), r.get("kdj_j", "?")
                self.tray.notify(f"KDJ Cross: {name}",
                                 f"{tkr} | Price: {price} | J={j} K={k} D={d} | Weekly KDJ crossed")
        else:
            self.tray.notify("🔔 Stock Screener Alerts",
                             f"{n} stocks with new weekly KDJ golden cross detected")
        self.tray.set_alert_count(n)
        self.status_label.setText(f"🔔 {n} new weekly KDJ alert{'s' if n > 1 else ''}")

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)

    def _on_alerts_error(self, msg):
        logger.warning("Alerts check failed: %s", msg)
        self.status_label.setText("⚠ Alerts check failed")

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)

    # ── New listings (🆕 公告栏) ──────────────────────────────────────────

    def _new_listings_paths(self):
        """State + board files live next to the day-cache (APPDATA when bundled)."""
        base = cache_dir()
        return (os.path.join(base, "seen_state.json"),
                os.path.join(base, "announcements.json"))

    def _refresh_new_listings(self):
        """Re-render the 🆕 New Listings tab from the announcements file."""
        try:
            _state_file, board_file = self._new_listings_paths()
            entries = AnnouncementBoard(board_file).as_list()
        except Exception as e:
            logger.warning("New listings board read failed: %s", e)
            entries = []
        if not entries:
            self.results_panel.set_new_listings(pd.DataFrame())
            return
        rows = [{
            "ticker": e.get("ticker", ""),
            "Code": e.get("code", ""),
            "Market": e.get("market", ""),
            "First Seen": e.get("first_seen", ""),
        } for e in entries]
        self.results_panel.set_new_listings(pd.DataFrame(rows))

    def _check_new_listings(self):
        """Compare the current ticker list against history; publish new ones.

        Runs after each completed data pipeline. First run sets the baseline
        (no alerts); afterwards every stock that appears for the first time is
        appended to the announcements board + tray notification.
        """
        if not self.ticker_names:
            return
        market = self._last_market_code or self.sidebar.get_params()["market_code"]
        ticker_map = {normalize_code(t): t for t in self.ticker_names
                      if normalize_code(t) is not None}
        if not ticker_map:
            return
        state_file, board_file = self._new_listings_paths()
        try:
            new, ok = run_once(lambda: set(ticker_map.keys()),
                               state_file, market=market)
        except Exception as e:
            logger.warning("New listings check failed: %s", e)
            return
        if not ok or not new:
            return
        run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entries = [{
            "code": c,
            "ticker": ticker_map.get(c, ""),
            "market": market,
            "first_seen": run_at,
        } for c in new]
        AnnouncementBoard(board_file).publish(entries)
        preview = ", ".join(new[:6]) + ("…" if len(new) > 6 else "")
        self.tray.notify("🆕 New listings",
                         f"{len(new)} new stock(s): {preview}")
        self.status_label.setText(f"🆕 {len(new)} new listing(s)")
        logger.info("New listings for %s: %s", market, preview)

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)
        self._refresh_new_listings()

    # ── Chart drill-down ──────────────────────────────────────────────────

    def _open_chart(self, ticker):
        d = self.data.get(ticker)
        name = self.ticker_names.get(ticker, "")
        if d is None:
            self.status_label.setText(f"⚠ No chart data for {ticker}")
            return
        try:
            from ui.chart_view import ChartDialog
            dlg = ChartDialog(ticker, name, d, self)
            dlg.exec()
        except Exception as e:
            logger.exception("Chart dialog failed for %s", ticker)
            self._show_error("Chart failed: " + str(e))

    def _on_worker_cancelled(self):
        self.status_label.setText("Cancelled")
        self.update_progress(100, "Cancelled")
        self._set_busy(False)

    def _on_screener_error(self, msg):
        self._show_error("Screener failed: " + msg, self._start_screeners)

    def _on_download_error(self, msg):
        def _retry_download():
            code = self._last_market_code or self.sidebar.get_params()["market_code"]
            self._start_download(code, force_refresh=False)
        self._show_error("Download failed: " + msg, _retry_download)

    def _on_market_changed(self, market_code):
        if self._busy:
            return
        self.status_label.setText(
            "Market changed to " + market_code + " - re-downloading...")
        self.results_panel.set_all_empty()
        self._start_download(market_code)

    def _on_refresh(self):
        if self._busy:
            return
        params = self.sidebar.get_params()
        # Refresh Data / F5 / auto-refresh must always fetch fresh data,
        # never serve the day-cache.
        self._start_download(params["market_code"], force_refresh=True)

    def _on_export(self):
        key = self.results_panel.current_tab_key()
        if key and key in self.results_panel.tables:
            table = self.results_panel.tables[key]
            table._export_csv()

    def _on_auto_refresh_toggled(self, state):
        if state:
            self._refresh_timer.start(300000)  # 5 min
        else:
            self._refresh_timer.stop()

    def _on_about(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, "About Stock Screener Pro",
            "<h3>Stock Screener Pro v1.0.0</h3>"
            "<p>Multi-market stock screening terminal.</p>"
            "<p><b>Markets:</b> Bursa MY, NYSE, NASDAQ, AMEX, SSE</p>"
            "<p><b>Screeners:</b> EMA Compression (Daily/Hourly/Weekly), KDJ Cross, "
            "KDJ Divergence, Scoring</p>"
        )

    def closeEvent(self, event):
        settings = QSettings("StockScreenerPro", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()

    def update_progress(self, value, text=""):
        if value >= 100:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setValue(value)
        if text:
            self.status_label.setText(text)
