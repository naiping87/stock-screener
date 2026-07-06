"""PandasModel — wraps a DataFrame for QTableView with high performance."""

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex
from PyQt6.QtGui import QColor, QBrush
import pandas as pd


class PandasModel(QAbstractTableModel):
    """A table model that wraps a pandas DataFrame for QTableView.

    Supports:
      - Read-only display with row count / column headers
      - Numeric sorting by clicking column headers
      - Conditional colour per column via a colour_map callback
    """

    def __init__(self, df: pd.DataFrame = None, colour_map: dict = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._colour_map = colour_map or {}
        self._sort_col = None
        self._sort_order = Qt.SortOrder.AscendingOrder

    # ── Core QAbstractTableModel overrides ─────────────────────────────────

    def rowCount(self, parent=QModelIndex()):
        return len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return len(self._df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        val = self._df.iat[index.row(), index.column()]
        col_name = self._df.columns[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(val, float):
                if val == 0 or pd.isna(val):
                    return "—"
                return f"{val:.2f}"
            return str(val) if val is not None else "—"

        elif role == Qt.ItemDataRole.ForegroundRole:
            cb = self._colour_map.get(col_name)
            if cb:
                colour = cb(val)
                if colour:
                    return QBrush(QColor(colour))
            return None

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(val, (int, float)):
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
