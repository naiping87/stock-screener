"""PandasModel — bridges pd.DataFrame to QTableView via QAbstractTableModel."""

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QColor
import pandas as pd


class PandasModel(QAbstractTableModel):
    """High-performance table model wrapping a pandas DataFrame."""

    # Columns that should be right-aligned (numeric)
    RIGHT_ALIGN_COLS = {"Price", "kdj_k", "kdj_d", "kdj_j", "Vol Ratio",
                        "Vol MA", "Score", "Div%", ">200", "Align",
                        "Tight", "BB", "Vol%", "Spike", "Vol↑", "VolMA"}
    # Columns with color-coded values
    GREEN_RED_COLS = {"ROE%", "Price"}

    def __init__(self, df: pd.DataFrame = None):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def setDataFrame(self, df: pd.DataFrame):
        """Replace the underlying DataFrame."""
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return self._df.shape[0]

    def columnCount(self, parent=QModelIndex()):
        return self._df.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        col = self._df.columns[index.column()]
        raw = self._df.iloc[index.row(), index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(raw, float):
                return f"{raw:.2f}"
            return str(raw) if raw is not None else "—"

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in self.RIGHT_ALIGN_COLS:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.ForegroundRole:
            if col in self.GREEN_RED_COLS:
                try:
                    v = float(raw)
                    if v > 0:
                        return QColor("#3fb950")
                    elif v < 0:
                        return QColor("#f85149")
                except (ValueError, TypeError):
                    pass

        if role == Qt.ItemDataRole.FontRole:
            # Bold for positive ROE
            if col == "ROE%":
                try:
                    if float(raw) > 0:
                        font = self._df.attrs.get("_bold_font")
                        return font
                except (ValueError, TypeError):
                    pass

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return str(self._df.columns[section])
        return None

    def sort(self, column: int, order: Qt.SortOrder):
        """Sort DataFrame by clicked column."""
        col_name = self._df.columns[column]
        ascending = order == Qt.SortOrder.AscendingOrder
        self.beginResetModel()
        self._df = self._df.sort_values(by=col_name, ascending=ascending, na_position='last')
        self.endResetModel()
