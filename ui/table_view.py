"""Custom QTableView with sorting, conditional formatting, and export."""

import pandas as pd
from PyQt6.QtCore import QEvent, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFileDialog, QHeaderView, QMenu, QTableView, QToolTip

from .styles import BLUE, GREEN, ORANGE, RED, TEXT_DIM
from .table_model import PandasModel, _column_help

# ── Default colour maps for common columns ───────────────────────────────

def roe_colour(val) -> str | None:
    """Green if ROE > 0, red if ROE < 0."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return TEXT_DIM
    try:
        v = float(val)
        if v > 0:
            return GREEN
        elif v < 0:
            return RED
    except (ValueError, TypeError):
        pass
    return None


def signal_colour(val) -> str | None:
    """Green for 'crossed', blue for 'above'."""
    if not isinstance(val, str):
        return None
    v = val.strip().lower()
    if v == "crossed":
        return GREEN
    elif v == "above":
        return BLUE
    return None


def score_colour(val) -> str | None:
    """Gradient: high score = green, mid = orange, low = red."""
    try:
        v = float(val)
        if v >= 70:
            return GREEN
        elif v >= 40:
            return ORANGE
        else:
            return RED
    except (ValueError, TypeError):
        return None


def score11_colour(val) -> str | None:
    """11-factor technical score (0-11): 7+ green, 4+ orange, else red."""
    try:
        v = float(val)
        if v >= 7:
            return GREEN
        elif v >= 4:
            return ORANGE
        else:
            return RED
    except (ValueError, TypeError):
        return None


def clv_colour(val) -> str | None:
    """Closing strength (0-1): 0.8+ green, 0.6+ orange, else red."""
    try:
        v = float(val)
        if v >= 0.8:
            return GREEN
        elif v >= 0.6:
            return ORANGE
        else:
            return RED
    except (ValueError, TypeError):
        return None


def rr_colour(val) -> str | None:
    """Risk/reward: 2+ green, 1.2+ orange, else red."""
    try:
        v = float(val)
        if v >= 2.0:
            return GREEN
        elif v >= 1.2:
            return ORANGE
        else:
            return RED
    except (ValueError, TypeError):
        return None


def chg_colour(val) -> str | None:
    """Green if change is positive, red if negative."""
    try:
        v = float(val)
        if v > 0:
            return GREEN
        elif v < 0:
            return RED
    except (ValueError, TypeError):
        pass
    return None


DEFAULT_COLOUR_MAP = {
    "ROE%": roe_colour,
    "ROE": roe_colour,
    "Signal": signal_colour,
    "KDJ": signal_colour,
    "WKDJ": signal_colour,
    "Score": score11_colour,
    "Chg%": chg_colour,
    # Phase-1 (Ignition) friendly columns: 0-100 gradient for sub-scores
    "Value": score_colour,
    "Master": score_colour,
    "Strength": score_colour,
    "Setup": score_colour,
    "Trigger": score_colour,
    "Breakout": score_colour,
    "RS Rank": score_colour,
    "CLV": clv_colour,
    "R:R": rr_colour,
}


class SortFilterProxy(QSortFilterProxyModel):
    """Minimal proxy to enable sorting + filtering on the PandasModel.

    Sorting compares the raw values (Qt.UserRole) so formatted display
    strings ("1.2M", "12.30%") never break numeric ordering.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ""

    def setFilterFixedString(self, text: str):
        """Store the lowercase needle and let Qt re-run the row filter.

        The actual match happens in filterAcceptsRow() against each row's
        precomputed search key — a single Python substring test per row,
        NOT a per-cell scan of every column (which was the search-input lag:
        ~280ms per keystroke on a 1000-row table).
        """
        self._needle = (text or "").strip().lower()
        super().setFilterFixedString(text)

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._needle:
            return True
        m = self.sourceModel()
        if hasattr(m, "search_key"):
            return self._needle in m.search_key(source_row)
        # Fallback: no search-key support → behave like an unfiltered row.
        return True

    def lessThan(self, left, right):
        lv = left.data(Qt.ItemDataRole.UserRole)
        rv = right.data(Qt.ItemDataRole.UserRole)
        if lv is None:
            return True
        if rv is None:
            return False
        try:
            return float(lv) < float(rv)
        except (TypeError, ValueError):
            return str(lv) < str(rv)


class TableView(QTableView):
    """Scrollable, sortable table with conditional colours + export."""

    export_requested = pyqtSignal(str)  # tab_name
    row_activated = pyqtSignal(str)     # ticker (double-click -> drill-down)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = PandasModel()
        self._proxy = SortFilterProxy()
        self._proxy.setSourceModel(self._model)
        # Search across every column (set via set_filter below).
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModel(self._proxy)

        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        # cell hover tooltips (the model returns ToolTipRole = column explanation)
        self.setMouseTracking(True)
        if hasattr(self, "setToolTipsVisible"):
            self.setToolTipsVisible(True)
        # reliable per-column header tooltips via an event filter on the header.
        self.horizontalHeader().viewport().installEventFilter(self)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsClickable(True)

        # Let user resize columns
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.doubleClicked.connect(self._on_double_clicked)

    def _on_double_clicked(self, index):
        """Emit the raw ticker (with market suffix) for chart drill-down."""
        src = self._proxy.mapToSource(index)
        df = self._model.dataframe()
        if src.isValid() and "ticker" in df.columns and 0 <= src.row() < len(df):
            tkr = df.iloc[src.row()]["ticker"]
            if tkr is not None:
                self.row_activated.emit(str(tkr))

    def set_dataframe(self, df: pd.DataFrame):
        """Set the data and apply default colour maps."""
        model = PandasModel(df, colour_map=DEFAULT_COLOUR_MAP)
        self._proxy.setSourceModel(model)
        self._model = model
        self._auto_size_cols()

    def set_filter(self, text: str):
        """Filter rows by text across all columns (empty string = clear)."""
        self._proxy.setFilterFixedString(text.strip())

    def eventFilter(self, obj, event):
        """Show column explanations when hovering the header on any tab."""
        if obj is self.horizontalHeader().viewport() and event.type() == QEvent.Type.ToolTip:
            pos = self.horizontalHeader().viewport().mapFromGlobal(event.globalPos())
            sec = self.horizontalHeader().logicalIndexAt(pos)
            if sec >= 0:
                name = str(self._proxy.headerData(
                    sec, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole))
                QToolTip.showText(event.globalPos(), f"{name}: {_column_help(name) or name}")
                return True
        return super().eventFilter(obj, event)

    def _auto_size_cols(self):
        header = self.horizontalHeader()
        for i in range(self._model.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            w = header.sectionSize(i)
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(i, max(w + 20, 60))

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        copy_action = QAction("Copy selection", self)
        copy_action.triggered.connect(self._copy_selection)
        menu.addAction(copy_action)

        # Column visibility — hide the noise, keep what you actually use.
        cols = menu.addMenu("Columns…")
        df = self._model.dataframe()
        for i, name in enumerate(df.columns):
            act = cols.addAction(str(name))
            act.setCheckable(True)
            act.setChecked(not self.isColumnHidden(i))
            act.triggered.connect(lambda checked, c=i: self.setColumnHidden(c, not checked))
        menu.addSeparator()

        export_action = QAction("Export CSV...", self)
        export_action.triggered.connect(self._export_csv)
        menu.addAction(export_action)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_selection(self):
        rows = set()
        for idx in self.selectionModel().selectedRows():
            rows.add(idx.row())
        if not rows:
            return
        lines = []
        cols = self._model.columnCount()
        for row in sorted(rows):
            cells = []
            for col in range(cols):
                val = self._model.index(row, col).data(Qt.ItemDataRole.DisplayRole)
                cells.append(val or "")
            lines.append("\t".join(cells))
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            # utf-8-sig: Excel 打开中文不乱码
            self._model.dataframe().to_csv(path, index=False, encoding="utf-8-sig")
