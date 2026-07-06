"""Results panel — tab widget with TableView for each screener."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel
from PyQt6.QtCore import Qt
import pandas as pd

from .table_view import TableView
from .styles import TEXT_SECONDARY


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tables = {}  # tab_key -> TableView
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        tab_specs = [
            ("📅 Daily EMA", "daily_ema"),
            ("⏱ Hourly EMA", "hourly_ema"),
            ("📉 KDJ Divergence", "kdj_div"),
            ("📆 Weekly KDJ", "weekly_kdj"),
            ("📊 Daily KDJ", "daily_kdj"),
            ("⭐ Scoring", "scoring"),
        ]

        for tab_label, tab_key in tab_specs:
            table = TableView()
            self.tables[tab_key] = table
            self.tabs.addTab(table, tab_label)

        layout.addWidget(self.tabs)

    # ── Public API ────────────────────────────────────────────────────────

    def set_results(self, tab_key: str, df: pd.DataFrame):
        """Update a tab with DataFrame results."""
        if tab_key in self.tables and df is not None and not df.empty:
            self.tables[tab_key].set_dataframe(df)
        else:
            self.tables[tab_key].set_dataframe(pd.DataFrame())

    def set_all_empty(self):
        """Clear all tabs (e.g. after market switch)."""
        for table in self.tables.values():
            table.set_dataframe(pd.DataFrame())

    def current_tab_key(self) -> str | None:
        index = self.tabs.currentIndex()
        keys = list(self.tables.keys())
        return keys[index] if 0 <= index < len(keys) else None
