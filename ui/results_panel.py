"""Results panel — tab widget with table views for each screener."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel
from PyQt6.QtCore import Qt


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Placeholder tabs — will be replaced with real TableView widgets
        tab_names = [
            ("📅 Daily EMA", "daily_ema"),
            ("⏱ Hourly EMA", "hourly_ema"),
            ("📉 KDJ Divergence", "kdj_div"),
            ("📆 Weekly KDJ", "weekly_kdj"),
            ("📊 Daily KDJ", "daily_kdj"),
            ("⭐ Scoring", "scoring"),
        ]

        for tab_label, tab_key in tab_names:
            placeholder = QLabel(f"{tab_label}\n\nRun screeners to see results")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #8b949e; font-size: 16px;")
            self.tabs.addTab(placeholder, tab_label)

        layout.addWidget(self.tabs)

    def set_tab_results(self, tab_key: str, df):
        """Update a tab with DataFrame results. (Not yet implemented.)"""
        pass
