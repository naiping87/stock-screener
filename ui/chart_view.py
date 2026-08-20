"""Chart dialog — TradingView-style drill-down: candlesticks + EMA + KDJ + volume.

Rendered with pyqtgraph for native zoom/pan performance. Data comes straight
from the already-downloaded in-memory market data (no extra network calls).
"""

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout

from screener import KDJ_PERIOD, KDJ_SIGNAL, _calc_kdj

# ── TradingView palette ──────────────────────────────────────────────────
BG = "#131722"
PANEL = "#1e222d"
TEXT = "#d1d4dc"
TEXT_SEC = "#787b86"
UP = "#089981"
DOWN = "#f23645"
GRID = (255, 255, 255, 40)
EMA_COLORS = {20: "#2962FF", 50: "#f7c600", 100: "#b18cff", 200: "#787b86"}
KDJ_COLORS = {"K": "#2962FF", "D": "#f7c600", "J": "#b18cff"}
BAR_WIDTH = {"Daily": 60_000, "Weekly": 400_000}  # px-less: seconds per bar

pg.setConfigOptions(background=BG, foreground=TEXT, antialias=True)


class CandlestickItem(pg.GraphicsObject):
    """Fast candlestick renderer (classic pyqtgraph recipe, TV colors)."""

    def __init__(self, xs, opens, highs, lows, closes):
        super().__init__()
        self._picture = None
        self._make_picture(xs, opens, highs, lows, closes)

    def _make_picture(self, xs, opens, highs, lows, closes):
        self._picture = pg.QtGui.QPicture()
        p = pg.QtGui.QPainter(self._picture)
        w = 0.5
        for x, o, h, lo, c in zip(xs, opens, highs, lows, closes, strict=True):
            if np.isnan(o) or np.isnan(h) or np.isnan(lo) or np.isnan(c):
                continue
            up = c >= o
            color = UP if up else DOWN
            p.setPen(pg.mkPen(color))
            p.drawLine(pg.QtCore.QPointF(x, lo), pg.QtCore.QPointF(x, h))
            p.setBrush(pg.mkBrush(color))
            body_top, body_bottom = (o, c) if up else (c, o)
            p.drawRect(pg.QtCore.QRectF(x - w, body_top, w * 2, max(body_bottom - body_top, 0.01)))
        p.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self):
        return pg.QtCore.QRectF(self._picture.boundingRect())


def _series(data: dict, key: str, index: pd.Index, default=None) -> pd.Series | None:
    s = data.get(key)
    if s is None:
        s = default
    if s is None:
        return None
    try:
        return s.reindex(index)
    except Exception:
        return None


def _prepare(data: dict, interval: str) -> dict:
    """Normalise one interval's OHLCV series onto a single aligned index."""
    if interval == "Weekly" and "close_weekly" in data:
        idx = data["close_weekly"].index
        out = {
            "close": data["close_weekly"].reindex(idx),
            "high": data.get("high_weekly", data["close_weekly"]).reindex(idx),
            "low": data.get("low_weekly", data["close_weekly"]).reindex(idx),
            "open": data.get("open_weekly", data["close_weekly"]).reindex(idx),
            "volume": data.get("volume_weekly"),
        }
        return {k: v for k, v in out.items() if v is not None}

    close = data.get("close")
    if close is None or len(close) == 0:
        return {}

    if interval == "Weekly":
        close = close.resample("W-FRI").last().dropna()
        return {
            "close": close,
            "open": data.get("open", close).resample("W-FRI").first().reindex(close.index),
            "high": data.get("high", close).resample("W-FRI").max().reindex(close.index),
            "low": data.get("low", close).resample("W-FRI").min().reindex(close.index),
            "volume": (data.get("volume", pd.Series(dtype=float))
                       .resample("W-FRI").sum().reindex(close.index)
                       if data.get("volume") is not None else None),
        }

    idx = close.index
    return {
        "close": close,
        "open": _series(data, "open", idx, close),
        "high": _series(data, "high", idx, close),
        "low": _series(data, "low", idx, close),
        "volume": _series(data, "volume", idx),
    }


class ChartWidget(pg.GraphicsLayoutWidget):
    """Price (candles + EMA) / volume / KDJ panes with linked zoom & crosshair."""

    def __init__(self, data: dict, interval: str = "Daily", parent=None):
        super().__init__(parent)
        self.setBackground(BG)
        self.ci.layout.setSpacing(0)

        d = _prepare(data, interval)
        self._empty = not d or d.get("close") is None or len(d["close"]) == 0
        if self._empty:
            self._show_empty()
            return

        close = d["close"]
        xs = (close.index.astype("int64") // 10**9).to_numpy(dtype="float64")
        opens = d["open"].to_numpy(dtype="float64")
        highs = d["high"].to_numpy(dtype="float64")
        lows = d["low"].to_numpy(dtype="float64")
        closes = close.to_numpy(dtype="float64")
        volume = d.get("volume")

        # ── Panes ──────────────────────────────────────────────────────
        date_axis = pg.DateAxisItem(orientation="bottom")
        self.price = self.addPlot(row=0, col=0, axisItems={"bottom": date_axis})
        self.price.setMenuEnabled(False)
        self.price.showGrid(x=True, y=True, alpha=0.15)
        self.price.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.getAxis("bottom").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.setMouseEnabled(x=True, y=False)

        n_rows = 1
        if volume is not None and len(volume) > 0:
            self.volume = self.addPlot(row=1, col=0)
            self.volume.setMenuEnabled(False)
            self.volume.setXLink(self.price)
            self.volume.hideAxis("bottom")
            self.volume.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
            self.volume.setMouseEnabled(x=True, y=False)
            n_rows = 2

        self.kdj = self.addPlot(row=n_rows, col=0)
        self.kdj.setMenuEnabled(False)
        self.kdj.setXLink(self.price)
        self.kdj.showGrid(x=True, y=True, alpha=0.15)
        self.kdj.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
        self.kdj.setMouseEnabled(x=True, y=False)

        self.price.hideAxis("bottom")
        if volume is not None and len(volume) > 0:
            self.volume.hideAxis("bottom")

        # ── Candles + EMA ──────────────────────────────────────────────
        self.price.addItem(CandlestickItem(xs, opens, highs, lows, closes))
        width = BAR_WIDTH.get(interval, 60_000)
        for period, color in EMA_COLORS.items():
            if len(close) >= period:
                ema = close.ewm(span=period, adjust=False).mean().to_numpy(dtype="float64")
                self.price.plot(xs, ema, pen=pg.mkPen(color, width=1.2))

        # ── Volume ─────────────────────────────────────────────────────
        if volume is not None and len(volume) > 0:
            vols = volume.to_numpy(dtype="float64")
            up_mask = closes >= opens
            down_mask = ~up_mask
            self.volume.addItem(pg.BarGraphItem(
                x=xs[up_mask], height=vols[up_mask], width=width,
                brush=pg.mkBrush(UP), pen=pg.mkPen(None)))
            self.volume.addItem(pg.BarGraphItem(
                x=xs[down_mask], height=vols[down_mask], width=width,
                brush=pg.mkBrush(DOWN), pen=pg.mkPen(None)))

        # ── KDJ ────────────────────────────────────────────────────────
        kdj = _calc_kdj(d["high"], d["low"], close, KDJ_PERIOD, KDJ_SIGNAL)
        if kdj and kdj[0] is not None:
            k, dd, j = kdj
            for _name, series, color in (("K", k, KDJ_COLORS["K"]),
                                         ("D", dd, KDJ_COLORS["D"]),
                                         ("J", j, KDJ_COLORS["J"])):
                if series is None:
                    continue
                self.kdj.plot(xs, series.to_numpy(dtype="float64"),
                              pen=pg.mkPen(color, width=1.2))

        # ── Crosshair ──────────────────────────────────────────────────
        self._xs = xs
        self._ohlcv = list(zip(xs, opens, highs, lows, closes,
                               volume.to_numpy(dtype="float64") if volume is not None else [None] * len(xs),
                               strict=True))
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#2a2e39"))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#2a2e39"))
        self.price.addItem(self._vline, ignoreBounds=True)
        self.price.addItem(self._hline, ignoreBounds=True)
        self._crosshair_label = pg.TextItem(anchor=(0, 0), color=TEXT, fill=pg.mkBrush("#1e222d"))
        self._crosshair_label.setZValue(50)
        # ignoreBounds: the label must never influence autoRange (it would drag
        # the x-range down to 0 and the 5% padding blows it to ±10^9).
        self.price.addItem(self._crosshair_label, ignoreBounds=True)
        self._crosshair_label.setVisible(False)
        self._mouse_proxy = pg.SignalProxy(self.price.scene().sigMouseMoved,
                                           rateLimit=60, slot=self._on_mouse_moved)

        # ── Header (anchored inside the price pane) ────────────────────
        last = closes[-1]
        prev = closes[-2] if len(closes) > 1 else last
        chg = (last - prev) / prev * 100 if prev else 0.0
        chg_color = UP if chg >= 0 else DOWN
        title = (f"<span style='color:{TEXT};font-weight:700;font-size:15px'>{interval}</span>"
                 f"&nbsp;&nbsp;<span style='color:{TEXT};font-size:14px'>"
                 f"Close <b>{last:,.2f}</b></span>"
                 f"&nbsp;&nbsp;<span style='color:{chg_color};font-weight:600'>"
                 f"{chg:+.2f}%</span>"
                 f"&nbsp;&nbsp;<span style='color:{TEXT_SEC};font-size:12px'>"
                 f"{len(close)} bars</span>")
        header = pg.TextItem(html=title, anchor=(0, 0))
        header.setZValue(40)
        self.price.addItem(header, ignoreBounds=True)
        self._header = header

        self.ci.layout.setRowStretchFactor(0, 5)
        if volume is not None and len(volume) > 0:
            self.ci.layout.setRowStretchFactor(1, 1)
        self.ci.layout.setRowStretchFactor(n_rows, 2)

        # Auto-fit price range to the data
        self.price.autoRange()

    def _on_mouse_moved(self, evt):
        if self._empty:
            return
        pos = evt[0]
        if self.price.sceneBoundingRect().contains(pos):
            mouse = self.price.vb.mapSceneToView(pos)
            x = mouse.x()
            nearest = min(self._xs, key=lambda v: abs(v - x))
            for (bx, o, h, _lo, c, vol) in self._ohlcv:
                if bx == nearest:
                    color = UP if c >= o else DOWN
                    txt = (f"<span style='color:{TEXT}'><b>{pd.Timestamp(bx, unit='s'):%Y-%m-%d}</b></span>"
                           f"&nbsp; O <span style='color:{color}'>{o:,.2f}</span>"
                           f"&nbsp; H <span style='color:{color}'>{h:,.2f}</span>"
                           f"&nbsp; L <span style='color:{color}'>{_lo:,.2f}</span>"
                           f"&nbsp; C <span style='color:{color}'>{c:,.2f}</span>")
                    if vol is not None:
                        txt += f"&nbsp; V <span style='color:{TEXT_SEC}'>{vol:,.0f}</span>"
                    self._crosshair_label.setHtml(txt)
                    self._crosshair_label.setPos(nearest + 12, mouse.y() - 26)
                    self._crosshair_label.setVisible(True)
                    break
            self._vline.setPos(nearest)
            self._hline.setPos(mouse.y())

    def _show_empty(self):
        lbl = pg.LabelItem("<span style='color:#5d606b;font-size:14px'>Not enough data to render chart</span>")
        self.addItem(lbl, row=0, col=0)


class ChartDialog(QDialog):
    """Drill-down dialog: Daily + Weekly candlestick charts for one ticker."""

    def __init__(self, ticker: str, name: str, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{name} ({ticker})")
        self.resize(1040, 720)
        self.setStyleSheet(f"QDialog{{background:{BG};}}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)

        head = QLabel(f"<span style='color:{TEXT};font-size:17px;font-weight:700'>{name}</span>"
                      f"&nbsp;&nbsp;<span style='color:{TEXT_SEC};font-size:13px'>{ticker}</span>")
        head.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(head)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(ChartWidget(data, "Daily"), "📅 Daily")
        tabs.addTab(ChartWidget(data, "Weekly"), "🗓 Weekly")
        layout.addWidget(tabs, 1)

        hint = QLabel("Scroll to zoom · Drag to pan · Hover for OHLCV")
        hint.setStyleSheet(f"color:{TEXT_SEC}; font-size:11px; padding:2px 4px;")
        layout.addWidget(hint)
