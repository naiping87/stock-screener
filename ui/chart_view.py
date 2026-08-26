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
from screener_setup import nearest_pivot, closing_strength

# ── TradingView palette ──────────────────────────────────────────────────
BG = "#131722"
PANEL = "#1e222d"
TEXT = "#d1d4dc"
TEXT_SEC = "#787b86"
UP = "#089981"
DOWN = "#f23645"
GRID = (255, 255, 255, 40)
EMA_COLORS = {20: "#2962FF", 50: "#f7c600", 60: "#ff6b00", 100: "#b18cff", 200: "#787b86"}
KDJ_COLORS = {"K": "#2962FF", "D": "#f7c600", "J": "#b18cff"}
BAR_WIDTH = {"Daily": 60_000 * 0.7, "Weekly": 400_000 * 0.7}  # seconds per bar (xs is epoch seconds)

pg.setConfigOptions(background=BG, foreground=TEXT, antialias=True)


class CandlestickItem(pg.GraphicsObject):
    """Fast candlestick renderer (classic pyqtgraph recipe, TV colors).

    QPicture-based painting broke under PyQt6 (the item painted in device
    pixels instead of data coordinates, so the candles rendered as a single
    smeared block and the X axis collapsed to 0-2). Draw directly in
    paint() with the view's transform instead — correct in every Qt.
    """

    def __init__(self, xs, opens, highs, lows, closes):
        super().__init__()
        self.xs = np.asarray(xs, dtype=float)
        self.opens = np.asarray(opens, dtype=float)
        self.highs = np.asarray(highs, dtype=float)
        self.lows = np.asarray(lows, dtype=float)
        self.closes = np.asarray(closes, dtype=float)
        # Cache bounds so boundingRect() doesn't scan the arrays every paint
        self._bounds = pg.QtCore.QRectF(
            float(self.xs.min() - 0.6),
            float(np.nanmin(self.lows)),
            float(self.xs.max() - self.xs.min() + 1.2),
            float(np.nanmax(self.highs) - np.nanmin(self.lows) + 0.1),
        )
        self._w = 0.5

    def paint(self, painter, *args, **kwargs):
        painter.setRenderHint(pg.QtGui.QPainter.RenderHint.Antialiasing, False)
        for x, o, h, lo, c in zip(self.xs, self.opens, self.highs,
                                  self.lows, self.closes, strict=True):
            if not (np.isfinite(o) and np.isfinite(h) and np.isfinite(lo)
                    and np.isfinite(c)):
                continue
            up = c >= o
            color = UP if up else DOWN
            pen = pg.mkPen(color, width=1)
            painter.setPen(pen)
            painter.setBrush(pg.mkBrush(color))
            # wick
            painter.drawLine(pg.QtCore.QPointF(x, lo), pg.QtCore.QPointF(x, h))
            # body (min height so flat bars are visible)
            top = o if up else c
            bottom = c if up else o
            hgt = max(bottom - top, (h - lo) * 0.003, 0.01)
            painter.drawRect(pg.QtCore.QRectF(x - self._w, top,
                                              self._w * 2, hgt))

    def boundingRect(self):
        return self._bounds


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
        # Epoch seconds for the date axis, robust across datetime resolution
        # and timezones. pandas 3.0 may give datetime64[s] or [us]; a tz-aware
        # index cannot astype() directly (tz-convert first), and a [s] index
        # divided by 1e9 collapsed every bar to x=1.0. Using UTC microseconds
        # then /1e6 gives true epoch seconds for every variant.
        _idx_utc = close.index.tz_convert("UTC").tz_localize(None)
        xs = (_idx_utc.astype("datetime64[us]").astype("int64") / 1e6).to_numpy(dtype="float64")
        opens = d["open"].to_numpy(dtype="float64")
        highs = d["high"].to_numpy(dtype="float64")
        lows = d["low"].to_numpy(dtype="float64")
        closes = close.to_numpy(dtype="float64")
        volume = d.get("volume")

        # ── Panes ──────────────────────────────────────────────────────
        # DateAxisItem with the market's UTC offset (Bursa is UTC+8) so the
        # axis labels read local dates, not UTC. Reused for every pane whose
        # bottom may become visible (volume/KDJ panes hide theirs).
        date_axis = pg.DateAxisItem(orientation="bottom", utcOffset=8 * 3600)
        self.price = self.addPlot(row=0, col=0, axisItems={"bottom": date_axis})
        self.price.setMenuEnabled(False)
        self.price.showGrid(x=True, y=True, alpha=0.15)
        self.price.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.getAxis("bottom").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.setMouseEnabled(x=True, y=False)

        n_rows = 1
        if volume is not None and len(volume) > 0:
            self.volume = self.addPlot(row=1, col=0,
                                       axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
            self.volume.setMenuEnabled(False)
            self.volume.setXLink(self.price)
            self.volume.hideAxis("bottom")
            self.volume.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
            self.volume.setMouseEnabled(x=True, y=False)
            n_rows = 2

        self.kdj = self.addPlot(row=n_rows, col=0,
                                axisItems={"bottom": pg.DateAxisItem(orientation="bottom", utcOffset=8 * 3600)})
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

        # ── Phase-1 annotations: nearest confirmed pivot (resistance) ───
        try:
            pv = nearest_pivot(d["high"], d["low"], close)
            if pv is not None:
                line = pg.InfiniteLine(pos=pv["price"], angle=0,
                                        pen=pg.mkPen("#f7c600", width=1.4,
                                                     style=pg.QtCore.Qt.PenStyle.DashLine))
                self.price.addItem(line)
                lbl = pg.TextItem(html=f"<span style='color:#f7c600;font-weight:600'>"
                                       f"Pivot {pv['price']:,.2f} (−{pv['distance_pct']:.1f}%)</span>",
                                  anchor=(1, 1), color="#f7c600", fill=pg.mkBrush("#1e222d"))
                lbl.setZValue(45)
                self.price.addItem(lbl, ignoreBounds=True)
                lbl.setPos(xs[-1], pv["price"])
            sup = nearest_support(d["low"], d["high"], close)
            if sup is not None:
                line2 = pg.InfiniteLine(pos=sup["price"], angle=0,
                                        pen=pg.mkPen("#c8a4ff", width=1.0,
                                                     style=pg.QtCore.Qt.PenStyle.DotLine))
                self.price.addItem(line2)
        except Exception:
            pass  # annotation is a bonus; never break the chart

        # ── Phase-1: closing strength chip (top-right header line) ─────-
        try:
            clv = closing_strength(d["high"], d["low"], close)
            if clv is not None:
                clv_color = UP if clv >= 0.8 else (TEXT_SEC if clv >= 0.6 else DOWN)
                clv_lbl = pg.TextItem(
                    html=f"<span style='color:{clv_color};font-size:12px'>"
                         f"CLV {clv:.2f}</span>", anchor=(1, 0), color=clv_color)
                clv_lbl.setZValue(45)
                self.price.addItem(clv_lbl, ignoreBounds=True)
                clv_lbl.setPos(xs[-1], closes[-1])
        except Exception:
            pass

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
