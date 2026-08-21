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


def _make_empty_widget(title: str = "No results",
                       hint: str = "Run Screeners from the sidebar to start, or adjust parameters and retry") -> QWidget:
    """A friendly empty-state placeholder (styled via styles.py objectNames)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addStretch()
    icon = QLabel("📭")
    icon.setObjectName("emptyStateIcon")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(icon)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("emptyStateTitle")
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title_lbl)
    hint_lbl = QLabel(hint)
    hint_lbl.setObjectName("emptyStateHint")
    hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint_lbl.setWordWrap(True)
    lay.addWidget(hint_lbl)
    lay.addStretch()
    return w


# 各 tab 的空态文案
_EMPTY_STATES = {
    "new_listings": (
        "No new listings yet",
        "New stocks first appear here after a data refresh "
        "(the baseline is set on the first run)",
    ),
}


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
            ("🆕 New Listings", "new_listings"),
        ]

        for tab_label, tab_key in tab_specs:
            table = TableView()
            table.row_activated.connect(self.ticker_activated)
            self.tables[tab_key] = table

            empty_title, empty_hint = _EMPTY_STATES.get(
                tab_key, ("No results",
                          "Run Screeners from the sidebar to start, or adjust parameters and retry"))
            stack = QStackedWidget()
            stack.addWidget(_make_empty_widget(empty_title, empty_hint))  # index 0: empty
            stack.addWidget(table)                                       # index 1: results
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

    def set_new_listings(self, df: pd.DataFrame):
        """Update the 🆕 New Listings tab (not part of the screener pipeline)."""
        if "new_listings" not in self.tables:
            return
        idx = self._tab_index["new_listings"]
        base = self._base_labels["new_listings"]
        if df is not None and not df.empty:
            self.tables["new_listings"].set_dataframe(df)
            self.tabs.widget(idx).setCurrentIndex(1)
            self.tabs.setTabText(idx, f"{base} ({len(df)})")
        else:
            self.tables["new_listings"].set_dataframe(pd.DataFrame())
            self.tabs.widget(idx).setCurrentIndex(0)
            self.tabs.setTabText(idx, base)

    def set_all_empty(self):
        """Clear screener tabs (e.g. after market switch); keep New Listings."""
        for key in self.tables:
            if key == "new_listings":
                continue
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
