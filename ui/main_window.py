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
from workers.download_worker import DownloadWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Screener Pro")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)
        self.data = {}
        self.ticker_names = {}

        settings = QSettings("StockScreenerPro", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self._setup_menu()
        self._setup_statusbar()
        self._setup_central()
        self._setup_shortcuts()

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

    def _setup_shortcuts(self):
        pass

    def _on_run_screeners(self):
        params = self.sidebar.get_params()
        market_code = params["market_code"]
        self._start_download(market_code)

    def _start_download(self, market_code):
        self.status_label.setText("Downloading " + market_code.upper() + " market data...")
        self.worker = DownloadWorker(market_code)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_download_error)
        self.worker.start()

    def _on_data_loaded(self, data, ticker_names):
        self.data = data
        self.ticker_names = ticker_names
        self.status_label.setText("Loaded " + str(len(data)) + " tickers - ready to screen")
        self.update_progress(100, str(len(data)) + " tickers loaded")

    def _on_download_error(self, msg):
        self.status_label.setText("Error: " + msg)
        QMessageBox.warning(self, "Download Failed",
                           "Could not download data:\n" + msg)

    def _on_market_changed(self, market_code):
        self.status_label.setText(
            "Market changed to " + market_code + " - re-downloading...")
        self._start_download(market_code)

    def _on_refresh(self):
        params = self.sidebar.get_params()
        self._start_download(params["market_code"])

    def _on_export(self):
        self.status_label.setText("Export not yet implemented")

    def _on_about(self):
        QMessageBox.about(
            self, "About Stock Screener Pro",
            "<h3>Stock Screener Pro v1.0.0</h3>"
            "<p>Multi-market stock screening terminal.</p>"
            "<p><b>Supported Markets:</b> Bursa Malaysia, NYSE, NASDAQ, AMEX, SSE</p>"
            "<p><b>Screeners:</b> EMA Compression, KDJ Cross, KDJ Divergence, Scoring</p>"
        )

    def closeEvent(self, event):
        settings = QSettings("StockScreenerPro", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def update_progress(self, value, text=""):
        if value >= 100:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setValue(value)
        if text:
            self.status_label.setText(text)
