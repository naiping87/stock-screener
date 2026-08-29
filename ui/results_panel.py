"""Results panel — tab widget with TableView for each screener.

Each tab is a QStackedWidget: index 0 = friendly empty state, index 1 = table.
Tab titles carry live result counts; a search box filters the current tab.
"""

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .table_view import TableView
import i18n


def _make_empty_widget(title: str = "No results",
                       hint: str = "Run Screeners from the sidebar to start, or adjust parameters and retry") -> QWidget:
    """A friendly empty-state placeholder (styled via styles.py objectNames)."""
    title = i18n.t(title)
    hint = i18n.t(hint)
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
    "top_movers": (
        "No movers yet",
        "Run Screeners to load market data — today's top gainers, losers and actives appear here",
    ),
    "new_picks": (
        "No new picks yet",
        "Stocks that pass the screeners for the first time appear here — "
        "the baseline is set on the first run after a data refresh",
    ),
    "edge": (
        "No edge stats yet",
        "This tab shows real win rates per signal type (built from the "
        "signal journal). It accumulates as you run the screeners over the "
        "coming days — check back after a week or two.",
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
        self.search_box.setPlaceholderText("🔍 " + i18n.t("Search code / name / signal…"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self._on_search)
        self.guide_btn = QPushButton("❓ Guide")
        self.guide_btn.setObjectName("guideButton")
        self.guide_btn.clicked.connect(self._show_guide)
        head = QHBoxLayout()
        head.addWidget(self.search_box, 1)
        head.addWidget(self.guide_btn)
        layout.addLayout(head)

        # Ignition-only hint: explains when the Min Closing Strength filter
        # caps the result below the requested Top N (hidden by default).
        self.filter_note = QLabel("")
        self.filter_note.setObjectName("filterNote")
        self.filter_note.setStyleSheet(
            "color:#f4b83a; font-size:12.5px; padding:2px 2px 4px 2px;")
        self.filter_note.hide()
        layout.addWidget(self.filter_note)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        tab_specs = [
            ("🚀 " + i18n.t("Ignition"), "phase1"),
            ("⭐ " + i18n.t("Scoring"), "scoring"),
            ("🔺 " + i18n.t("Top Movers"), "top_movers"),
            ("📅 " + i18n.t("Daily EMA"), "daily_ema"),
            ("⏱ " + i18n.t("Hourly EMA"), "hourly_ema"),
            ("🗓 " + i18n.t("Weekly EMA"), "weekly_ema"),
            ("📉 " + i18n.t("KDJ Divergence"), "kdj_div"),
            ("📆 " + i18n.t("Weekly KDJ"), "weekly_kdj"),
            ("📊 " + i18n.t("Daily KDJ"), "daily_kdj"),
            ("🆕 " + i18n.t("New Picks"), "new_picks"),
            ("📈 " + i18n.t("Edge Report"), "edge"),
        ]

        for tab_label, tab_key in tab_specs:
            table = TableView()
            if tab_key == "top_movers":
                # Don't stretch the last column (Volume) to fill the window —
                # keep it compact so the movers table reads cleanly.
                table.horizontalHeader().setStretchLastSection(False)
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
        # Surface the CLV-filter hint on the Ignition tab (hidden elsewhere).
        note = df.attrs.get("filter_note") if isinstance(df, pd.DataFrame) else None
        self._filter_note_text = str(note) if note else ""
        if self._filter_note_text:
            self.filter_note.setText(self._filter_note_text)
            self.filter_note.show()
        else:
            self.filter_note.hide()
        if df is not None and not df.empty:
            self.tables[tab_key].set_dataframe(df)
            self.tabs.widget(idx).setCurrentIndex(1)
            self.tabs.setTabText(idx, f"{self._base_labels[tab_key]} ({len(df)})")
        else:
            self.tables[tab_key].set_dataframe(pd.DataFrame())
            self.tabs.widget(idx).setCurrentIndex(0)
            self.tabs.setTabText(idx, self._base_labels[tab_key])

    def set_new_picks(self, df: pd.DataFrame):
        """Update the 🆕 New Picks tab (not part of the screener pipeline)."""
        if "new_picks" not in self.tables:
            return
        idx = self._tab_index["new_picks"]
        base = self._base_labels["new_picks"]
        if df is not None and not df.empty:
            self.tables["new_picks"].set_dataframe(df)
            self.tabs.widget(idx).setCurrentIndex(1)
            self.tabs.setTabText(idx, f"{base} ({len(df)})")
        else:
            self.tables["new_picks"].set_dataframe(pd.DataFrame())
            self.tabs.widget(idx).setCurrentIndex(0)
            self.tabs.setTabText(idx, base)

    def set_all_empty(self):
        """Clear screener tabs (e.g. after market switch); keep New Picks."""
        for key in self.tables:
            if key == "new_picks":
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
        # Keep the CLV hint only on the Ignition tab; restore it on return.
        if self.current_tab_key() == "phase1" and getattr(self, "_filter_note_text", ""):
            self.filter_note.setText(self._filter_note_text)
            self.filter_note.show()
        else:
            self.filter_note.hide()
        # Re-apply the search text to the newly visible tab.
        table = self._current_table()
        if table:
            table.set_filter(self.search_box.text())

    def _show_guide(self):
        """Quick how-to so users aren't dropped into a wall of columns."""
        QMessageBox.information(
            self,
            "How to use Stock Screener Pro",
            "Start on the Ignition tab (first tab) — it ranks the whole market "
            "by setup quality.\n\n"
            "1) Click a column header to SORT (start with 'Value').\n"
            "2) Read the 'Why' column — it explains each signal in plain words.\n"
            "3) Hover any column header to see what it means.\n"
            "4) Double-click a stock to open its chart (candles + EMA + KDJ).\n"
            "5) Too many/too few? Adjust Min Score, Top N, Min Closing Strength "
            "on the left.\n"
            "6) Too many columns? Right-click -> 'Columns…' to hide the ones you "
            "don't use.\n\n"
            "Other tabs: Top Movers (today's leaders), EMA / KDJ screeners, "
            "Scoring, New Picks. Start simple: Ignition -> chart -> decide.",
        )
