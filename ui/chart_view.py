"""Chart dialog — TradingView-style drill-down: candlesticks + EMA + KDJ + volume.

Rendered with pyqtgraph for native zoom/pan performance. Data comes straight
from the already-downloaded in-memory market data (no extra network calls).
"""

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout

from screener import KDJ_PERIOD, KDJ_SIGNAL, _calc_kdj
from screener_setup import nearest_pivot, closing_strength

# ── TradingView palette ──────────────────────────────────────────────────
BG = "#131722"
PANEL = "#1e222d"
TEXT = "#d1d4dc"
TEXT_SEC = "#787b86"
# High-contrast up/down: bright professional green / clear red. The previous
# #26A69A (teal) read as "cyan" against the dark background and the teal EMA,
# and #EF5350 was too close to the greens — the up/down split was hard to see
# at a glance. Solid, opaque bodies so the color never depends on the wick.
UP = "#22C55E"
DOWN = "#EF4444"
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

    def __init__(self, xs, opens, highs, lows, closes, width=42000.0):
        super().__init__()
        self.xs = np.asarray(xs, dtype=float)
        self.opens = np.asarray(opens, dtype=float)
        self.highs = np.asarray(highs, dtype=float)
        self.lows = np.asarray(lows, dtype=float)
        self.closes = np.asarray(closes, dtype=float)
        # Cache bounds so boundingRect() doesn't scan the arrays every paint
        self._bounds = pg.QtCore.QRectF(
            float(self.xs.min() - width),
            float(np.nanmin(self.lows)),
            float((self.xs.max() - self.xs.min()) + width * 2),
            float(np.nanmax(self.highs) - np.nanmin(self.lows) + 0.1),
        )
        # ── Dynamic body width ──────────────────────────────────────────
        # Width is derived from the MEDIAN gap between consecutive bars, so
        # the body always spans a readable fraction (~62%) of a bar slot on
        # ANY timeframe and at ANY zoom. Fixed widths made daily candles look
        # razor-thin when zoomed out and weekly bodies too narrow; using the
        # actual bar spacing keeps up/down instantly readable at every level.
        gaps = np.diff(self.xs)
        gaps = gaps[np.isfinite(gaps) & (gaps > 0)]
        slot = float(np.median(gaps)) if gaps.size > 0 else float(width)
        self._w = max(slot * 0.62, 0.5)   # body = 62% of the bar slot (min 0.5 s)
        self._wick_w = 1.0                 # 1 px wick, color-first readability

    def paint(self, painter, *args, **kwargs):
        painter.setRenderHint(pg.QtGui.QPainter.RenderHint.Antialiasing, False)
        for x, o, h, lo, c in zip(self.xs, self.opens, self.highs,
                                  self.lows, self.closes, strict=True):
            if not (np.isfinite(o) and np.isfinite(h) and np.isfinite(lo)
                    and np.isfinite(c)):
                continue
            # ── Yahoo data is sometimes inconsistent (close > recorded high
            # or open outside the [low, high] range — 40+ bars on 5211.KL).
            # Visual repair: expand the wicks to always CONTAIN the body, so
            # the candle looks like a real OHLC bar instead of a body that
            # pokes out of its shadows (looked like a "weird candle").
            h_eff = max(h, o, c)
            l_eff = min(lo, o, c)
            up = c >= o
            color = UP if up else DOWN
            # OPAQUE brush — a translucent/faded body lets the background or
            # the EMA show through and kills the green-vs-red signal.
            painter.setPen(pg.mkPen(color, width=1))
            painter.setBrush(pg.mkBrush(color))
            # wick (same color, solid)
            painter.drawLine(pg.QtCore.QPointF(x, l_eff), pg.QtCore.QPointF(x, h_eff))
            # body — full-opacity rect, min visible height for flat bars
            top = o if up else c
            bottom = c if up else o
            hgt = max(bottom - top, (h_eff - l_eff) * 0.004, 0.01)
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
        wk_open = data.get("open_weekly", data["close_weekly"]).reindex(idx)
        # Same placeholder fix as the daily path: Yahoo weekly opens are often
        # NaN or open==close for illiquid names, making every bar read 'green'.
        # Fill from the previous close so the candle has a real body and the
        # true up/down verdict.
        if wk_open is not None:
            prev = data["close_weekly"].reindex(idx).shift(1)
            wk_open = wk_open.fillna(prev)
            same = (wk_open == data["close_weekly"].reindex(idx)) & (prev != data["close_weekly"].reindex(idx)) & prev.notna()
            if same.any():
                wk_open = wk_open.mask(same, prev)
            wk_open = wk_open.fillna(data["close_weekly"].reindex(idx))
        out = {
            "close": data["close_weekly"].reindex(idx),
            "high": data.get("high_weekly", data["close_weekly"]).reindex(idx),
            "low": data.get("low_weekly", data["close_weekly"]).reindex(idx),
            "open": wk_open,
            "volume": data.get("volume_weekly"),
        }
        return {k: v for k, v in out.items() if v is not None}

    close = data.get("close")
    if close is None or len(close) == 0:
        return {}

    if interval == "Weekly":
        close = close.resample("W-FRI").last().dropna()
        wk_open = data.get("open", close).resample("W-FRI").first().reindex(close.index)
        if wk_open is not None:
            prev = close.shift(1)
            wk_open = wk_open.fillna(prev)
            same_as_close = (wk_open == close) & (prev != close) & prev.notna()
            if same_as_close.any():
                wk_open = wk_open.mask(same_as_close, prev)
            wk_open = wk_open.fillna(close)
        return {
            "close": close,
            "open": wk_open,
            "high": data.get("high", close).resample("W-FRI").max().reindex(close.index),
            "low": data.get("low", close).resample("W-FRI").min().reindex(close.index),
            "volume": (data.get("volume", pd.Series(dtype=float))
                       .resample("W-FRI").sum().reindex(close.index)
                       if data.get("volume") is not None else None),
        }

    idx = close.index
    opens = _series(data, "open", idx, close)
    # Yahoo daily data frequently carries NaN opens or open==close
    # placeholders for illiquid names. With open==close we can't tell up from
    # down — every such bar reads as a green doji. Two-stage fill:
    #   1. NaN open → previous CLOSE (standard missing-open fallback)
    #   2. open == close AND previous close differs → the "open" was a
    #      placeheld close; use the previous close instead, restoring a real
    #      body and the true up/down verdict.
    if opens is not None:
        prev = close.shift(1)
        opens = opens.fillna(prev)
        same_as_close = (opens == close) & (prev != close) & prev.notna()
        if same_as_close.any():
            opens = opens.mask(same_as_close, prev)
        opens = opens.fillna(close)
    return {
        "close": close,
        "open": opens,
        "high": _series(data, "high", idx, close),
        "low": _series(data, "low", idx, close),
        "volume": _series(data, "volume", idx),
    }


class _NoWheelViewBox(pg.ViewBox):
    """ViewBox that ignores wheel events entirely.

    Our datasets are already fully visible (a few hundred bars), so wheel zoom
    buys nothing and stutters on every tick while repainting all panes. Drag-to-
    pan and the crosshair stay fully functional — only the wheel is swallowed.
    """

    def wheelEvent(self, ev, axis=None):
        ev.ignore()
        return


class ChartWidget(pg.GraphicsLayoutWidget):
    """Price (candles + EMA) / volume / KDJ panes with linked zoom & crosshair."""

    # Emitted on a double-click so the dialog can close without hunting the ✕.
    double_clicked = pyqtSignal()

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
        self.price = self.addPlot(row=0, col=0, axisItems={"bottom": date_axis},
                                  viewBox=_NoWheelViewBox())
        self.price.setMenuEnabled(False)
        self.price.showGrid(x=True, y=True, alpha=0.15)
        self.price.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.getAxis("bottom").setTextPen(pg.mkPen(TEXT_SEC))
        self.price.setMouseEnabled(x=True, y=False)

        n_rows = 1
        if volume is not None and len(volume) > 0:
            self.volume = self.addPlot(row=1, col=0,
                                       axisItems={"bottom": pg.DateAxisItem(orientation="bottom")},
                                       viewBox=_NoWheelViewBox())
            self.volume.setMenuEnabled(False)
            self.volume.setXLink(self.price)
            self.volume.hideAxis("bottom")
            self.volume.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
            self.volume.setMouseEnabled(x=True, y=False)
            n_rows = 2

        self.kdj = self.addPlot(row=n_rows, col=0,
                                axisItems={"bottom": pg.DateAxisItem(orientation="bottom", utcOffset=8 * 3600)},
                                viewBox=_NoWheelViewBox())
        self.kdj.setMenuEnabled(False)
        self.kdj.setXLink(self.price)
        self.kdj.showGrid(x=True, y=True, alpha=0.15)
        self.kdj.getAxis("left").setTextPen(pg.mkPen(TEXT_SEC))
        self.kdj.setMouseEnabled(x=True, y=False)

        self.price.hideAxis("bottom")
        if volume is not None and len(volume) > 0:
            self.volume.hideAxis("bottom")

        # ── Candles + EMA ──────────────────────────────────────────────
        # Draw EMA FIRST, candles LAST: the candlesticks must be the top
        # visual layer (K > EMA), not buried under the moving averages.
        # A 20-day EMA through the middle of a body used to hide the
        # open/close — the core up/down signal.
        width = BAR_WIDTH.get(interval, 60_000)
        for period, color in EMA_COLORS.items():
            if len(close) >= period:
                ema = close.ewm(span=period, adjust=False).mean().to_numpy(dtype="float64")
                self.price.plot(xs, ema, pen=pg.mkPen(color, width=1.2))
        self.price.addItem(CandlestickItem(
            xs, opens, highs, lows, closes, width=width))

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
        # Keep the up/down split but SOFTEN the intensity (55% alpha) so
        # volume reads as supporting context, never competing with the
        # candlesticks above it (visual hierarchy: K > EMA > volume).
        if volume is not None and len(volume) > 0:
            vols = volume.to_numpy(dtype="float64")
            up_mask = closes >= opens
            down_mask = ~up_mask
            up_brush = pg.mkBrush(pg.mkColor(UP))
            up_brush.setColor(pg.mkColor(UP + "8C"))  # 55% alpha
            down_brush = pg.mkBrush(pg.mkColor(DOWN))
            down_brush.setColor(pg.mkColor(DOWN + "8C"))
            self.volume.addItem(pg.BarGraphItem(
                x=xs[up_mask], height=vols[up_mask], width=width * 0.8,
                brush=up_brush, pen=pg.mkPen(None)))
            self.volume.addItem(pg.BarGraphItem(
                x=xs[down_mask], height=vols[down_mask], width=width * 0.8,
                brush=down_brush, pen=pg.mkPen(None)))

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
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#4a5060"))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#4a5060"))
        self.price.addItem(self._vline, ignoreBounds=True)
        self.price.addItem(self._hline, ignoreBounds=True)
        self._crosshair_label = pg.TextItem(anchor=(0, 0), color=TEXT, fill=pg.mkBrush("#1e222d"))
        self._crosshair_label.setZValue(50)
        # ignoreBounds: the label must never influence autoRange (it would drag
        # the x-range down to 0 and the 5% padding blows it to ±10^9).
        self.price.addItem(self._crosshair_label, ignoreBounds=True)
        self._crosshair_label.setVisible(False)
        # Live price readout at the cursor (so you don't read the left axis).
        self._price_label = pg.TextItem(anchor=(0, 0.5), color=TEXT, fill=pg.mkBrush("#1e222d"))
        self._price_label.setZValue(51)
        self.price.addItem(self._price_label, ignoreBounds=True)
        self._price_label.setVisible(False)
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

    def mouseDoubleClickEvent(self, evt):
        """Double-click anywhere on the chart closes the dialog."""
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(evt)

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
            # price at the cursor's Y, in real time (3 decimals below RM1)
            pv = mouse.y()
            price_txt = f"{pv:,.3f}" if abs(pv) < 1.0 else f"{pv:,.2f}"
            self._price_label.setText(price_txt)
            self._price_label.setPos(nearest + 6, mouse.y())
            self._price_label.setVisible(True)

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

        # Double-click the chart (either tab) to close the dialog.
        for i in range(tabs.count()):
            w = tabs.widget(i)
            if hasattr(w, "double_clicked"):
                w.double_clicked.connect(self.close)

        # Hotkeys: D = Daily, W = Weekly.
        QShortcut(QKeySequence("D"), self, activated=lambda: tabs.setCurrentIndex(0))
        QShortcut(QKeySequence("W"), self, activated=lambda: tabs.setCurrentIndex(1))

        hint = QLabel("Drag to pan · Hover for OHLCV · D = Daily · W = Weekly · Double-click to close")
        hint.setStyleSheet(f"color:{TEXT_SEC}; font-size:11px; padding:2px 4px;")
        layout.addWidget(hint)
