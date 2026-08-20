"""Results panel — tab widget with TableView for each screener.

Each tab is a QStackedWidget: index 0 = friendly empty state, index 1 = table.
Tab titles carry live result counts; a search box filters the current tab.
"""

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .table_view import TableView


def _make_empty_widget() -> QWidget:
    """A friendly empty-state placeholder (styled via styles.py objectNames)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addStretch()
    icon = QLabel("📭")
    icon.setObjectName("emptyStateIcon")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(icon)
    title = QLabel("No results")
    title.setObjectName("emptyStateTitle")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)
    hint = QLabel("Run Screeners from the sidebar to start, or adjust parameters and retry")
    hint.setObjectName("emptyStateHint")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(hint)
    lay.addStretch()
    return w


class ResultsPanel(QWidget):
    ticker_activated = pyqtSignal(str)  # double-click on a result row

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tables = {}          # tab_key -> TableView
        self._tab_index = {}      # tab_key -> index in the tab widget
        self._base_labels = {}    # tab_key -> label without count
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Search box (applies to the current tab) ─────────────────────
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search code / name / signal…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_search)
        layout.addWidget(self.search_box)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        tab_specs = [
            ("📅 Daily EMA", "daily_ema"),
            ("⏱ Hourly EMA", "hourly_ema"),
            ("🗓 Weekly EMA", "weekly_ema"),
            ("📉 KDJ Divergence", "kdj_div"),
            ("📆 Weekly KDJ", "weekly_kdj"),
            ("📊 Daily KDJ", "daily_kdj"),
            ("⭐ Scoring", "scoring"),
        ]

        for tab_label, tab_key in tab_specs:
            table = TableView()
            table.row_activated.connect(self.ticker_activated)
            self.tables[tab_key] = table

            stack = QStackedWidget()
            stack.addWidget(_make_empty_widget())   # index 0: empty state
            stack.addWidget(table)                  # index 1: results
            self.tabs.addTab(stack, tab_label)

            self._tab_index[tab_key] = self.tabs.count() - 1
            self._base_labels[tab_key] = tab_label

        layout.addWidget(self.tabs, 1)

    # ── Public API ────────────────────────────────────────────────────────

    def set_results(self, tab_key: str, df: pd.DataFrame):
        """Update a tab with DataFrame results (empty → friendly placeholder)."""
        if tab_key not in self.tables:
            return
        idx = self._tab_index[tab_key]
        if df is not None and not df.empty:
            self.tables[tab_key].set_dataframe(df)
            self.tabs.widget(idx).setCurrentIndex(1)
            self.tabs.setTabText(idx, f"{self._base_labels[tab_key]} ({len(df)})")
        else:
            self.tables[tab_key].set_dataframe(pd.DataFrame())
            self.tabs.widget(idx).setCurrentIndex(0)
            self.tabs.setTabText(idx, self._base_labels[tab_key])

    def set_all_empty(self):
        """Clear all tabs (e.g. after market switch)."""
        for key in self.tables:
            self.set_results(key, pd.DataFrame())

    def current_tab_key(self) -> str | None:
        index = self.tabs.currentIndex()
        for key, i in self._tab_index.items():
            if i == index:
                return key
        return None

    def _current_table(self) -> TableView | None:
        key = self.current_tab_key()
        return self.tables.get(key) if key else None

    # ── Search ────────────────────────────────────────────────────────────

    def _on_search(self, text: str):
        table = self._current_table()
        if table:
            table.set_filter(text)

    def _on_tab_changed(self, index):
        # Re-apply the search text to the newly visible tab.
        table = self._current_table()
        if table:
            table.set_filter(self.search_box.text())
