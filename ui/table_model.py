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
    "Liq": "Liquidity status from ADTV60 (dollar volume). 🔴 Illiquid · 🟠 Low · 🟡 Tradable · 🟢 Good · 🔥 High. Illiquid/Low are down-weighted so they never rank as high-confidence.",
    "ADTV60": "Average Daily Traded Value over 60 days (RM) — the structural-liquidity gauge. Below RM20k = not a tradeable Ignition.",
    "Part.": "Participation label for today's volume ratio (Very Low … Very Strong). Confirmation context only, never a buy signal.",
    "adtv20": "Average Daily Traded Value over 20 days (RM) — recent activity, for reference.",
    "liquidity_tier": "ILLIQUID / LOW / TRADABLE / GOOD / HIGH (ADTV60).",
    "liquidity_label": "Human-readable liquidity label.",
    "liquidity_gate": "True when ADTV60 is below the minimum — down-weighted and flagged, not a tradeable Ignition.",
    "liquidity_mult": "Score multiplier applied to the ranking (0.35 illiquid … 1.10 high).",
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
    # scoring / EMA tab raw keys (displayed uppercase by the table)
    "SCORE": "11-factor technical score (0-11).",
    "TECH_WEIGHTED": "Weighted technical score (0-100).",
    "TECH_COMPONENTS": "Trend / Compression / Momentum / Volume / Activity breakdown.",
    "RS_5D": "Relative strength vs the market, 5 days",
    "RS_20D": "Relative strength vs the market, 20 days",
    "RS_60D": "Relative strength vs the market, 60 days",
    "TICKER": "Ticker code",
    "SECTOR": "Stock's sector (Bursa taxonomy)",
    "PRICE": "Latest close price",
    "WTD%": "Weighted technical score",
    # scoring raw keys (displayed uppercase-ish)
    "wkdj_sig": "Weekly KDJ golden-cross / above signal",
    "kdj_sig": "Daily KDJ golden-cross / above signal",
    "above_200": "Close above the 200-day EMA",
    "ema200_up": "200-day EMA rising",
    "trend_tight": "Short EMAs compressed / tight trend",
    "vol_ok": "Volume above the minimum threshold",
    "vol_ma_ok": "Volume above its moving average",
    "vol_expand": "Volume expanding",
    "aligned": "EMA 50 > 100 > 200 aligned (bullish)",
    "bb_squeeze": "Bollinger squeeze (compression)",
    "vol_spike": "Today's volume > 2x the 20-day average",
    "score_components": "Trend / Compression / Momentum / Volume / Activity breakdown",
    "score_weighted": "Weighted technical score (0-100)",
    # phase-1 raw keys (in case shown unrenamed)
    "rs_5d": "Relative strength vs market, 5 days",
    "rs_20d": "Relative strength vs market, 20 days",
    "rs_60d": "Relative strength vs market, 60 days",
    "rs_120d": "Relative strength vs market, 120 days",
    "rs_momentum": "RS acceleration / momentum",
    "sector_strength": "Sector strength (0-100)",
    "sector_rs_20d": "Stock vs its own sector, 20 days",
    "range_atr": "Today's range / ATR20. < 0.8 = low significance (a high close here is weak).",
    "meaningful_range": "True when today's range is >= 0.8x ATR20 — a real move, not a dead bar.",
    "market_regime": "Whole-market RISK_ON / NEUTRAL / RISK_OFF",
    "pivot_distance_pct": "% from the nearest pivot",
    "base_range_pct": "Base width (% range)",
    "extension_pct": "% above the 20-day EMA",
    "master_rr": "Risk/reward-adjusted master score (main ranking)",
    "master_score": "Weighted Strength/Setup/Trigger/Breakout score",
    "tech_weighted": "Weighted technical score (0-100)",
}

# case-insensitive lookup so "Score"/"SCORE"/"score" all match.
_COLUMN_HELP_LOWER = {str(k).strip().lower(): v for k, v in COLUMN_HELP.items()}


def _column_help(name) -> str | None:
    if not name:
        return None
    return _COLUMN_HELP_LOWER.get(str(name).strip().lower())


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
            av = abs(val)
            if av < 1.00:
                # Bursa tick is 0.005 below RM1 -> show up to 3 decimals,
                # trimming trailing zeros so 0.500 -> 0.5 but 0.335 -> 0.335.
                s = f"{val:,.3f}".rstrip("0").rstrip(".")
                return s or "0"
            return f"{val:,.2f}"
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
        # Per-row lowercase search key (code + name + text columns) so the
        # proxy can filter with ONE fast string test per row instead of
        # scanning every cell with Qt's per-column substring match.
        self._search_keys: list[str] | None = None
        self._build_search_keys()

    def _build_search_keys(self) -> None:
        """Precompute a lowercase search key per row (text columns only)."""
        df = self._df
        if df is None or df.empty:
            self._search_keys = None
            return
        # Text-like columns (code / name / sector / why / setup type): these
        # are what a trader actually searches. Numeric columns are excluded so
        # typing "0" can't match a random "0.50" price, and so the filter is a
        # cheap per-row string test instead of an all-cells scan.
        # pandas 3.0 stores string columns as `str`/`string` (not `object`),
        # so detect text columns robustly rather than by ``== object``.
        text_col_positions = [
            i for i, c in enumerate(df.columns)
            if pd.api.types.is_string_dtype(df[c])
            or pd.api.types.is_object_dtype(df[c])
        ]
        if not text_col_positions:
            self._search_keys = [""] * len(df)
            return
        self._search_keys = [
            " ".join(str(df.iat[r, ci]) for ci in text_col_positions).lower()
            for r in range(len(df))
        ]

    def search_key(self, row: int) -> str:
        """Lowercase searchable text for a row (code/name/text columns)."""
        if self._search_keys is None:
            return ""
        try:
            return self._search_keys[row]
        except IndexError:
            return ""

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
            name = str(self._df.columns[section])
            help_text = _column_help(name) or name
            return f"{name}: {help_text}"
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
        self._build_search_keys()
        self.layoutChanged.emit()

    # ── Public API ────────────────────────────────────────────────────────

    def setDataFrame(self, df: pd.DataFrame):
        """Replace underlying DataFrame and reset the view."""
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self._build_search_keys()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df.copy()
