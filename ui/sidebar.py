"""Sidebar — Apple-style parameter panel with card sections."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QGroupBox, QPushButton,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QSlider,
    QHBoxLayout, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from markets import list_all, get as get_market
from screener import (
    EMA_PERIODS, DIVERGENCE_THRESHOLD, MIN_COMPRESSION_BARS,
    KDJ_PERIOD, KDJ_SIGNAL, DIVERGENCE_LOOKBACK,
    VOL_MIN, VOL_MIN_HOURLY, WEEKLY_VOL_MIN,
    DAILY_VOL_MIN, DAILY_VOL_RATIO,
    SCORE_TREND_PERIODS, SCORE_TREND_THRESHOLD, SCORE_EMA200_SLOPE_BARS,
    SCORE_VOL_PERIOD, SCORE_VOL_THRESHOLD, SCORE_VOL_MA_BARS,
    SCORE_VOL_MA_THRESHOLD, SCORE_TOP_N,
)


LABEL_STYLE = "color:#6e6e73; font-size:12px; font-weight:500;"
VALUE_STYLE = "color:#1d1d1f; font-weight:600; font-size:12px; min-width:28px;"


def _row(label_text, widget, hint=None):
    """One row: label | widget."""
    w = QWidget()
    l = QHBoxLayout(w)
    l.setContentsMargins(0, 3, 0, 3)
    lbl = QLabel(label_text)
    lbl.setMinimumWidth(130)
    lbl.setStyleSheet(LABEL_STYLE)
    l.addWidget(lbl)
    l.addWidget(widget)
    l.addStretch()
    w.row_widget = widget
    if hint:
        w.setToolTip(hint)
    return w


def _sp(label_text, min_v, max_v, default, step=1, hint=None):
    """Label + QSpinBox."""
    sp = QSpinBox()
    sp.setRange(min_v, max_v)
    sp.setValue(default)
    sp.setSingleStep(step)
    sp.setFixedWidth(110)
    sp.setToolTip(hint or "")
    return _row(label_text, sp, hint)


def _dbl(label_text, min_v, max_v, default, step=0.1, hint=None):
    """Label + QDoubleSpinBox."""
    sp = QDoubleSpinBox()
    sp.setRange(min_v, max_v)
    sp.setValue(default)
    sp.setSingleStep(step)
    sp.setFixedWidth(110)
    sp.setToolTip(hint or "")
    return _row(label_text, sp, hint)


def _sld(label_text, min_v, max_v, default, step=1, hint=None):
    """Label + slider + value display."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 2, 0, 6)
    top = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setStyleSheet(LABEL_STYLE)
    top.addWidget(lbl)
    val_lbl = QLabel(str(default))
    val_lbl.setStyleSheet(VALUE_STYLE)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
    top.addWidget(val_lbl)
    layout.addLayout(top)
    s = QSlider(Qt.Orientation.Horizontal)
    if step < 1:
        s.setRange(int(min_v / step), int(max_v / step))
        s.setValue(int(default / step))
    else:
        s.setRange(min_v, max_v)
        s.setValue(default)
    s.setFixedHeight(24)
    layout.addWidget(s)
    w.slider = s
    w.val_label = val_lbl
    w.step = step
    def on_change(v):
        val = v * step if step < 1 else v
        val_lbl.setText(f"{val:.1f}" if step < 1 else str(int(val)))
    s.valueChanged.connect(on_change)
    if hint:
        w.setToolTip(hint)
    return w


def _multi(label_text, options, defaults, hint=None):
    """Label + horizontal checkboxes."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 2, 0, 6)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(LABEL_STYLE)
    layout.addWidget(lbl)
    row = QHBoxLayout()
    boxes = []
    for opt in options:
        cb = QCheckBox(str(opt))
        cb.setChecked(opt in defaults)
        cb.setStyleSheet(
            "QCheckBox{color:#1d1d1f;font-size:14px;font-weight:600;spacing:6px;padding:4px 8px;}"
            "QCheckBox::indicator{width:20px;height:20px;border:2px solid #d2d2d7;border-radius:5px;background:#fff;}"
            "QCheckBox::indicator:checked{background:#0071e3;border-color:#0071e3;}")
        if hint:
            cb.setToolTip(hint)
        row.addWidget(cb)
        boxes.append(cb)
    row.addStretch()
    layout.addLayout(row)
    w.boxes = boxes
    w.options = options
    return w


class Sidebar(QWidget):
    run_clicked = pyqtSignal()
    market_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumWidth(440)
        self.setStyleSheet("background:#f0f0f2;")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────
        title = QLabel("Parameters")
        title.setFont(QFont("SF Pro Display, Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color:#1d1d1f; background:transparent;")
        layout.addWidget(title)

        # ── Market ────────────────────────────────────────────────────
        market = QComboBox()
        for m in list_all():
            market.addItem(m.label, m.code)
        market.currentIndexChanged.connect(self._on_market_changed)
        market.setMinimumHeight(36)
        layout.addWidget(market)
        self.market_combo = market

        # Sector filter
        sector_lbl = QLabel("Sector")
        sector_lbl.setStyleSheet("color:#6e6e73; font-size:12px; font-weight:600; background:transparent; margin-top:8px;")
        layout.addWidget(sector_lbl)
        self.sector_combo = QComboBox()
        self.sector_combo.addItem("All Sectors", "")
        self.sector_combo.setMinimumHeight(32)
        layout.addWidget(self.sector_combo)

        # ── Scroll ────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;}")

        pw = QWidget()
        pw.setStyleSheet("background:transparent;")
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(2)

        # --- EMA Compression ---
        ema = QGroupBox("EMA Compression")
        el = QVBoxLayout(ema)
        self.ema_periods = _multi("Trend Periods", [10, 20, 50, 100, 200],
                                  [20, 50, 100, 200],
                                  "Select EMA periods to check for compression")
        el.addWidget(self.ema_periods)
        self.divergence_pct = _sld("Divergence %", 1.0, 10.0, DIVERGENCE_THRESHOLD, 0.5,
                                   "Max price-EMA deviation")
        el.addWidget(self.divergence_pct)
        self.compress_bars = _sld("Min Bars", 2, 20, MIN_COMPRESSION_BARS,
                                  hint="Min bars of sustained compression")
        el.addWidget(self.compress_bars)
        pl.addWidget(ema)

        # --- Volume ---
        vol = QGroupBox("Volume Filters")
        vl = QVBoxLayout(vol)
        self.vol_daily = _sp("Daily Min Vol", 0, 100_000_000, VOL_MIN, 100_000,
                             "Min daily volume MA for EMA/Divergence screeners")
        vl.addWidget(self.vol_daily)
        self.vol_hourly = _sp("Hourly Min Vol", 0, 100_000_000, VOL_MIN_HOURLY, 10_000,
                              "Min hourly volume MA")
        vl.addWidget(self.vol_hourly)
        self.vol_weekly = _sp("Weekly Min Vol", 0, 100_000_000, WEEKLY_VOL_MIN, 100_000,
                              "Min weekly volume MA for Weekly KDJ screener")
        vl.addWidget(self.vol_weekly)
        self.vol_d_kdj = _sp("KDJ Daily Vol Min", 0, 100_000_000, DAILY_VOL_MIN, 100_000,
                             "Min daily volume MA for Daily KDJ screener")
        vl.addWidget(self.vol_d_kdj)
        self.daily_vol_r = _sld("KDJ Vol Ratio", 1.0, 5.0, DAILY_VOL_RATIO, 0.1,
                                "Volume spike vs MA for Daily KDJ")
        vl.addWidget(self.daily_vol_r)
        pl.addWidget(vol)

        # --- KDJ ---
        kdj = QGroupBox("KDJ Parameters")
        kl = QVBoxLayout(kdj)
        self.kdj_period = _sld("Period (RSV)", 3, 30, KDJ_PERIOD,
                               hint="Highest/lowest lookback bars")
        kl.addWidget(self.kdj_period)
        self.kdj_signal = _sld("Signal Smooth", 1, 10, KDJ_SIGNAL,
                               hint="K/D smoothing period")
        kl.addWidget(self.kdj_signal)
        self.div_lookback = _sld("Div Lookback", 10, 60, DIVERGENCE_LOOKBACK, 5,
                                 "Bars to check for divergence pattern")
        kl.addWidget(self.div_lookback)
        pl.addWidget(kdj)

        # --- Scoring ---
        score = QGroupBox("Scoring System")
        sl = QVBoxLayout(score)
        self.score_trend_p = _multi("Trend Periods", [10, 20, 50, 100, 200],
                                    SCORE_TREND_PERIODS,
                                    "EMAs checked for bullish trend — check if price > EMA")
        sl.addWidget(self.score_trend_p)
        self.score_trend_div = _dbl("Trend Divergence %", 1.0, 20.0, SCORE_TREND_THRESHOLD, 0.5,
                                    "Min price above EMA for trend score")
        sl.addWidget(self.score_trend_div)
        self.score_slope = _sld("Slope Bars", 5, 60, SCORE_EMA200_SLOPE_BARS, 5,
                                "Bars for EMA200 slope calculation")
        sl.addWidget(self.score_slope)
        self.score_vol_p = _sld("Vol Lookback", 5, 120, SCORE_VOL_PERIOD, 5,
                                "Volume SMA period for volume score")
        sl.addWidget(self.score_vol_p)
        self.score_vol_t = _dbl("Vol Threshold %", 1.0, 50.0, SCORE_VOL_THRESHOLD, 1.0,
                                "Volume vs SMA threshold")
        sl.addWidget(self.score_vol_t)
        self.score_vol_ma_b = _sld("Vol MA Bars", 2, 20, SCORE_VOL_MA_BARS,
                                   hint="Volume SMA lookback for comparison")
        sl.addWidget(self.score_vol_ma_b)
        self.score_vol_ma_t = _dbl("Vol MA Threshold", 1.0, 20.0, SCORE_VOL_MA_THRESHOLD, 1.0,
                                   "Min volume SMA value")
        sl.addWidget(self.score_vol_ma_t)
        self.score_top_n = _sp("Top N Results", 5, 100, SCORE_TOP_N, 5,
                               "Number of top-scoring stocks to show")
        sl.addWidget(self.score_top_n)
        pl.addWidget(score)

        pl.addStretch()
        scroll.setWidget(pw)
        layout.addWidget(scroll)

        # ── Reset + Run ──────────────────────────────────────────────
        reset_row = QHBoxLayout()
        self.reset_btn = QPushButton("↺  Reset")
        self.reset_btn.setMinimumHeight(36)
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #0071e3;
                border: 1px solid #d2d2d7;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background: rgba(0,113,227,0.08);
                border-color: #0071e3;
            }
            QPushButton:pressed {
                background: rgba(0,113,227,0.15);
            }
        """)
        self.reset_btn.clicked.connect(self._reset_params)
        reset_row.addWidget(self.reset_btn)
        reset_row.addStretch()
        layout.addLayout(reset_row)

        # Wrap in a container with distinct background for visual pop
        run_container = QWidget()
        run_container.setStyleSheet(
            "background:#e8e8ed; border-radius:14px; padding:6px;")
        run_layout = QVBoxLayout(run_container)
        run_layout.setContentsMargins(6, 6, 6, 6)

        self.run_btn = QPushButton("▶  Run Screeners")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        self.run_btn.setMinimumHeight(56)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setStyleSheet("""
            QPushButton#runBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0088ff, stop:1 #0066dd);
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 17px;
                font-weight: 700;
                padding: 16px 0px;
                letter-spacing: 0.5px;
            }
            QPushButton#runBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a94ff, stop:1 #0077f0);
                border: 2px solid rgba(255,255,255,0.25);
            }
            QPushButton#runBtn:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0055cc, stop:1 #0044aa);
            }
        """)
        run_layout.addWidget(self.run_btn)
        layout.addWidget(run_container)

        # Auto-refresh
        ar = QHBoxLayout()
        self.auto_refresh = QCheckBox("Auto-refresh every 5 min")
        self.auto_refresh.setStyleSheet("color:#6e6e73; font-size:12px;")
        ar.addWidget(self.auto_refresh)
        ar.addStretch()
        layout.addLayout(ar)

    def set_sectors(self, sectors: list):
        current = self.sector_combo.currentData()
        self.sector_combo.blockSignals(True)
        self.sector_combo.clear()
        self.sector_combo.addItem('All Sectors', '')
        for s in sorted(s for s in sectors if s):
            self.sector_combo.addItem(s, s)
        idx = self.sector_combo.findData(current)
        self.sector_combo.setCurrentIndex(max(idx, 0))
        self.sector_combo.blockSignals(False)

    def _reset_params(self):
        code = self.market_combo.currentData()
        if code:
            m = get_market(code)
            d = m.defaults
            self.vol_daily.row_widget.setValue(d.get('vol_d', VOL_MIN))
            self.vol_hourly.row_widget.setValue(d.get('vol_h', VOL_MIN_HOURLY))
            self.vol_weekly.row_widget.setValue(d.get('vol_w', WEEKLY_VOL_MIN))
            self.vol_d_kdj.row_widget.setValue(d.get('vol_d_kdj', DAILY_VOL_MIN))
            self.kdj_period.slider.setValue(d.get('kdj_p', KDJ_PERIOD))
            self.kdj_signal.slider.setValue(d.get('kdj_s', KDJ_SIGNAL))
            self.div_lookback.slider.setValue(d.get('div_lb', DIVERGENCE_LOOKBACK))
            self.divergence_pct.slider.setValue(int(DIVERGENCE_THRESHOLD / 0.5))
            self.compress_bars.slider.setValue(MIN_COMPRESSION_BARS)
            self.daily_vol_r.slider.setValue(int(DAILY_VOL_RATIO / 0.1))
            self.score_slope.slider.setValue(SCORE_EMA200_SLOPE_BARS)
            self.score_vol_p.slider.setValue(SCORE_VOL_PERIOD)
            self.score_vol_ma_b.slider.setValue(SCORE_VOL_MA_BARS)
            self.score_trend_div.row_widget.setValue(SCORE_TREND_THRESHOLD)
            self.score_vol_t.row_widget.setValue(SCORE_VOL_THRESHOLD)
            self.score_vol_ma_t.row_widget.setValue(SCORE_VOL_MA_THRESHOLD)
            self.score_top_n.row_widget.setValue(SCORE_TOP_N)

    def _on_market_changed(self, index):
        code = self.market_combo.currentData()
        if code:
            m = get_market(code)
            d = m.defaults
            self.vol_daily.row_widget.setValue(d.get("vol_d", 200_000))
            self.vol_hourly.row_widget.setValue(d.get("vol_h", 20_000))
            self.vol_weekly.row_widget.setValue(d.get("vol_w", 500_000))
            self.vol_d_kdj.row_widget.setValue(d.get("vol_d_kdj", 500_000))
            self.market_changed.emit(code)

    # ── Param collector ────────────────────────────────────────────────
    def get_params(self) -> dict:
        def _sv(w):
            step = w.step
            v = w.slider.value()
            return v * step if step < 1 else v

        def _mv(w):
            return [w.options[i] for i, cb in enumerate(w.boxes) if cb.isChecked()]

        return {
            "market_code": self.market_combo.currentData(),
            "ema_periods": _mv(self.ema_periods),
            "ema_threshold": _sv(self.divergence_pct),
            "compress_bars": _sv(self.compress_bars),
            "vol_daily": self.vol_daily.row_widget.value(),
            "vol_hourly": self.vol_hourly.row_widget.value(),
            "vol_weekly": self.vol_weekly.row_widget.value(),
            "vol_daily_kdj": self.vol_d_kdj.row_widget.value(),
            "daily_vol_ratio": _sv(self.daily_vol_r),
            "kdj_period": _sv(self.kdj_period),
            "kdj_signal": _sv(self.kdj_signal),
            "div_lookback": _sv(self.div_lookback),
            "score_trend_periods": _mv(self.score_trend_p),
            "score_trend_div": self.score_trend_div.row_widget.value(),
            "score_slope_bars": _sv(self.score_slope),
            "score_vol_p": _sv(self.score_vol_p),
            "score_vol_t": self.score_vol_t.row_widget.value(),
            "score_vol_ma_b": _sv(self.score_vol_ma_b),
            "score_vol_ma_t": self.score_vol_ma_t.row_widget.value(),
            "score_top_n": self.score_top_n.row_widget.value(),
        }
