"""Main window — menu, status bar, sidebar + results tab layout."""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMenuBar, QMenu, QStatusBar, QLabel, QPushButton,
    QMessageBox, QProgressBar, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from .styles import (
    BG_DARK, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY,
    GREEN, RED, ACCENT, STYLESHEET,
)
from .sidebar import Sidebar
from .results_panel import ResultsPanel
from .system_tray import SystemTray
from workers.download_worker import DownloadWorker
from workers.screener_worker import ScreenerWorker
from workers.meta_worker import MetaWorker


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

        settings = QSettings("StockScreenerPro", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self._setup_menu()
        self._setup_statusbar()
        self._setup_central()
        self._setup_tray()

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

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_run_screeners(self):
        if not self.data:
            params = self.sidebar.get_params()
            self._start_download(params["market_code"])
        else:
            self._run_screeners()

    def _start_download(self, market_code):
        self.status_label.setText("Downloading " + market_code.upper() + " market data...")
        self.results_panel.set_all_empty()
        self.worker = DownloadWorker(market_code)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_download_error)
        self.worker.start()

    def _on_data_loaded(self, data, ticker_names):
        self.data = data
        self.ticker_names = ticker_names
        self.status_label.setText("Loaded " + str(len(data)) + " tickers - running screeners...")
        self._run_screeners()

    def _run_screeners(self):
        params = self.sidebar.get_params()
        self._result_dfs = {}
        self.screener_worker = ScreenerWorker(self.data, self.ticker_names, params)
        self.screener_worker.progress.connect(self.update_progress)
        self.screener_worker.result.connect(self._store_result)
        self.screener_worker.finished.connect(self._on_screeners_done)
        self.screener_worker.error.connect(self._on_screener_error)
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
            self.meta_worker.error.connect(lambda e: self.status_label.setText("Meta error: " + e))
            self.meta_worker.start()
        else:
            self._finalize_results()

    def _on_meta_loaded(self, meta):
        self._meta_cache.update(meta)
        self._finalize_results()

    def _finalize_results(self):
        # Attach ROE + sector to each result DataFrame (in-place, fast)
        all_sectors = set()
        for tab_key, df in self._result_dfs.items():
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

    def _apply_sector_filter(self):
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

        self.status_label.setText("Ready")
        self.update_progress(100, "Ready")

    def _on_sector_changed(self):
        self._apply_sector_filter()

    def _on_screener_error(self, msg):
        self.status_label.setText("Error: " + msg)
        QMessageBox.warning(self, "Screener Error",
                           "Screener failed:\n" + msg)

    def _on_download_error(self, msg):
        self.status_label.setText("Error: " + msg)
        QMessageBox.warning(self, "Download Failed",
                           "Could not download data:\n" + msg)

    def _on_market_changed(self, market_code):
        self.status_label.setText(
            "Market changed to " + market_code + " - re-downloading...")
        self.results_panel.set_all_empty()
        self._start_download(market_code)

    def _on_refresh(self):
        params = self.sidebar.get_params()
        self._start_download(params["market_code"])

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

