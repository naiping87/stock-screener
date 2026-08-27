"""PandasModel — wraps a DataFrame for QTableView with high performance."""

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor


# Plain-language explanations shown when hovering a column header.
COLUMN_HELP = {
    # Identifiers / price
    "Code": "Ticker code",
    "Name": "Company name",
    "Price": "Latest close price",
    "Close": "Latest close price",
    # Ignition / phase-1 (friendly names)
    "Setup Type": "The classification: SETUP / TRIGGER WATCH / BREAKOUT / LEADER / EMA RECLAIM / WEAKENING…",
    "Value": "Risk/reward-adjusted master score — the main ranking. Higher = better.",
    "Master": "Weighted Strength/Setup/Trigger/Breakout score (0-100).",
    "Strength": "Leading factor (30%): RS rank + momentum + sector strength.",
    "Setup": "Structure (25%): tight base, higher low, volume dry-up.",
    "Trigger": "Trigger (25%): strong close, near pivot, shakeout, EMA reclaim.",
    "Breakout": "Breakout quality (20%): how it broke above a pivot.",
    "RS Rank": "Relative-strength percentile vs the whole market (0-100).",
    "CLV": "Closing strength: 1.0 = closes at the day high (0-1).",
    "R:R": "Risk/reward to the next resistance (higher = better).",
    "Score": "11-factor technical score (0-11).",
    "Sector": "Stock's sector (Bursa taxonomy).",
    "Wtd%": "Weighted technical component score.",
    # RS / sector
    "RS5": "Relative strength vs market, 5 days",
    "RS20": "Relative strength vs market, 20 days",
    "RS60": "Relative strength vs market, 60 days",
    "RS Mom": "RS acceleration / momentum",
    "RS↑20d": "20-day change in RS rank (+ = gaining)",
    "RS Rank Chg": "Change in RS rank",
    "SecStr": "Sector strength (0-100)",
    "SecRS": "Stock vs its own sector (%)",
    # structure
    "Pivot": "Nearest resistance (confirmed pivot) above price",
    "Dist%": "% from the nearest pivot",
    "Target": "Measured-move target price",
    "Sup": "Nearest support below price",
    "Base%": "Base width (% range)",
    "DryUp": "Volume dry-up inside the base",
    "Shake": "Shakeout detected (a washout that recovered)",
    "FBO": "Failed breakout — broke a pivot but closed back below",
    "FBD": "Failed breakdown — broke support but recovered",
    "Regime": "Whole-market RISK_ON / NEUTRAL / RISK_OFF",
    "Why": "Why the stock is on the list (buy-side reasons)",
    # KDJ
    "Signal": "'crossed' = fresh golden cross · 'above' = already bullish",
    "kdj_k": "KDJ K value",
    "kdj_d": "KDJ D value",
    "kdj_j": "KDJ J value (K/D momentum)",
    "kdj_state": "BULLISH (K>D) / BEARISH (K<D)",
    "kdj_k_d_golden": "K crossed above D today (golden cross)",
    # scoring / fundamentals
    "ROE%": "Return on equity (%)",
    "ROE": "Return on equity",
    # volume
    "Vol MA": "Average volume",
    "Vol Ratio": "Today's volume vs the 20-day average",
    "Volume": "Trading volume",
    # movers
    "Chg%": "% change for the day",
}


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
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            return COLUMN_HELP.get(str(self._df.columns[section]))
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
