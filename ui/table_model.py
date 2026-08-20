"""PandasModel — wraps a DataFrame for QTableView with high performance."""

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor


def _format_cell(val, col_name: str) -> str:
    """TradingView-style cell formatting.

    - Volumes: compact K/M/B; other big numbers: thousands separators.
    - Prices/EMAs: adaptive decimals (4 below 1.0, else 2).
    - Percent-ish columns: append '%'.
    - Flags (bools): ✓ / —.
    Display strings are only for humans; sorting/filtering use the raw
    value via Qt.ItemDataRole.UserRole.
    """
    if val is None:
        return "—"
    if isinstance(val, bool):
        return "✓" if val else "—"
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        try:
            if pd.isna(val):
                return "—"
        except (TypeError, ValueError):
            return str(val)
        if val == 0:
            return "—"
        col = str(col_name)
        low = col.lower()
        if "vol" in low and "ratio" not in low:
            av = abs(val)
            if av >= 1e9:
                return f"{val / 1e9:.1f}B"
            if av >= 1e6:
                return f"{val / 1e6:.1f}M"
            if av >= 1e3:
                return f"{val / 1e3:.0f}K"
            return f"{val:,.0f}"
        if col == "Price" or col.startswith("EMA"):
            return f"{val:,.4f}" if abs(val) < 1 else f"{val:,.2f}"
        if "div" in low or col.endswith("%") or col == "ROE":
            # ROE 原始值是小数 (0.123 = 12.3%)，其余百分比列直接是百分数值
            return f"{val * 100:.2f}%" if col == "ROE" else f"{val:.2f}%"
        if isinstance(val, int) or float(val).is_integer():
            return f"{val:,.0f}"
        return f"{val:,.2f}"
    return str(val)


class PandasModel(QAbstractTableModel):
    """A table model that wraps a pandas DataFrame for QTableView.

    Supports:
      - Read-only display with row count / column headers
      - Numeric sorting by clicking column headers (raw values via UserRole)
      - Conditional colour per column via a colour_map callback
    """

    def __init__(self, df: pd.DataFrame = None, colour_map: dict = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._colour_map = colour_map or {}
        self._sort_col = None
        self._sort_order = Qt.SortOrder.AscendingOrder

    # ── Core QAbstractTableModel overrides ─────────────────────────────────

    def rowCount(self, parent=QModelIndex()):  # noqa: B008 — canonical Qt signature
        return len(self._df)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008 — canonical Qt signature
        return len(self._df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        val = self._df.iat[index.row(), index.column()]
        col_name = self._df.columns[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            return _format_cell(val, col_name)

        elif role == Qt.ItemDataRole.UserRole:
            # Raw value for sorting / filtering (proxy uses this).
            return val

        elif role == Qt.ItemDataRole.ForegroundRole:
            cb = self._colour_map.get(col_name)
            if cb:
                colour = cb(val)
                if colour:
                    return QBrush(QColor(colour))
            return None

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._df.columns[section])
            else:
                return str(section + 1)
        return None

    # ── Sorting ───────────────────────────────────────────────────────────

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        col_name = self._df.columns[column]
        self.layoutAboutToBeChanged.emit()
        try:
            ascending = order == Qt.SortOrder.AscendingOrder
            self._df = self._df.sort_values(col_name, ascending=ascending,
                                            na_position="last")
        except (TypeError, KeyError):
            pass
        self._sort_col = column
        self._sort_order = order
        self.layoutChanged.emit()

    # ── Public API ────────────────────────────────────────────────────────

    def setDataFrame(self, df: pd.DataFrame):
        """Replace underlying DataFrame and reset the view."""
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df.copy()
