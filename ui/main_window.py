"""Main window — menu, status bar, sidebar + results tab layout."""

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Screener Pro")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        # Restore window geometry
        settings = QSettings("StockScreenerPro", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self._setup_menu()
        self._setup_statusbar()
        self._setup_central()
        self._setup_shortcuts()

    # ── Menu bar ─────────────────────────────────────────────────────────

    def _setup_menu(self):
        menubar = self.menuBar()

        # File menu
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

        # View menu
        view_menu = menubar.addMenu("&View")
        self.dark_action = QAction("&Dark Theme", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(True)
        file_menu.addAction(self.dark_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ── Status bar ────────────────────────────────────────────────────────

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

    # ── Central widget ────────────────────────────────────────────────────

    def _setup_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar (left)
        self.sidebar = Sidebar()
        splitter.addWidget(self.sidebar)

        # Results tabs (right)
        self.results_panel = ResultsPanel()
        splitter.addWidget(self.results_panel)

        # Ratio 1:3
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 960])

        self.setCentralWidget(splitter)

        # Connect sidebar signals
        self.sidebar.run_clicked.connect(self._on_run_screeners)
        self.sidebar.market_changed.connect(self._on_market_changed)

    # ── Shortcuts ─────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        pass  # already set up via QAction shortcuts

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_run_screeners(self):
        self.status_label.setText("Running screeners...")

    def _on_market_changed(self, market_code: str):
        self.status_label.setText(f"Market changed to {market_code} — re-downloading...")

    def _on_refresh(self):
        self.status_label.setText("Refreshing data...")

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

    # ── Window events ─────────────────────────────────────────────────────

    def closeEvent(self, event):
        settings = QSettings("StockScreenerPro", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def update_progress(self, value: int, text: str = ""):
        if value >= 100:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setValue(value)
        if text:
            self.status_label.setText(text)
