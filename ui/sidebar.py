"""Sidebar — market selector + all screener parameters matching Cloud version."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QGroupBox, QPushButton,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QSlider,
    QHBoxLayout, QScrollArea, QLineEdit, QFrame,
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


def _sp(label, min_v, max_v, default, step=1, fmt=None):
    """Create a labeled QSpinBox."""
    w = QWidget()
    l = QHBoxLayout(w)
    l.setContentsMargins(0, 2, 0, 2)
    lbl = QLabel(label)
    lbl.setMinimumWidth(120)
    lbl.setStyleSheet('color:#8b949e; font-size:12px;')
    l.addWidget(lbl)
    sp = QSpinBox()
    sp.setRange(min_v, max_v)
    sp.setValue(default)
    sp.setSingleStep(step)
    sp.setFixedWidth(100)
    if fmt:
        sp.setSuffix(fmt)
    l.addWidget(sp)
    l.addStretch()
    w.spin = sp
    return w


def _dbl(label, min_v, max_v, default, step=0.1):
    w = QWidget()
    l = QHBoxLayout(w)
    l.setContentsMargins(0, 2, 0, 2)
    lbl = QLabel(label)
    lbl.setMinimumWidth(120)
    lbl.setStyleSheet('color:#8b949e; font-size:12px;')
    l.addWidget(lbl)
    sp = QDoubleSpinBox()
    sp.setRange(min_v, max_v)
    sp.setValue(default)
    sp.setSingleStep(step)
    sp.setFixedWidth(100)
    l.addWidget(sp)
    l.addStretch()
    w.spin = sp
    return w


def _sld(label, min_v, max_v, default, step=1):
    """Label + slider + value label."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 2, 0, 4)
    top = QHBoxLayout()
    top.addWidget(QLabel(label))
    val_lbl = QLabel(str(default))
    val_lbl.setStyleSheet("color:#58a6ff; font-weight:600; font-size:12px;")
    val_lbl.setFixedWidth(36)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
    top.addWidget(val_lbl)
    layout.addLayout(top)
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(int(min_v * (1/step if step < 1 else 1)), int(max_v * (1/step if step < 1 else 1)))
    s.setValue(int(default * (1/step if step < 1 else 1)))
    s.setFixedHeight(22)
    layout.addWidget(s)
    w.slider = s
    w.val_label = val_lbl
    w.step = step
    def on_change(v):
        val = v * step if step < 1 else v / 1
        if step == 1:
            val = v
            val_lbl.setText(str(val))
        elif step < 1:
            val = v * step
            val_lbl.setText(f"{val:.1f}")
        else:
            val_lbl.setText(str(v))
    s.valueChanged.connect(on_change)
    return w


def _multi(label, options, defaults):
    """Label + checkboxes for multiselect."""
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 2, 0, 4)
    layout.addWidget(QLabel(label))
    boxes = []
    row = QHBoxLayout()
    for i, opt in enumerate(options):
        cb = QCheckBox(str(opt))
        cb.setChecked(opt in defaults)
        row.addWidget(cb)
        boxes.append(cb)
    layout.addLayout(row)
    w.boxes = boxes
    w.options = options
    return w


class Sidebar(QWidget):
    run_clicked = pyqtSignal()
    market_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(310)
        self.setMaximumWidth(420)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Title ──────────────────────────────────────────────────────
        title = QLabel("Parameters")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#e6edf3;")
        layout.addWidget(title)

        # ── Market selector ───────────────────────────────────────────
        mkt_label = QLabel("Market")
        mkt_label.setStyleSheet("color:#58a6ff; font-size:11px; font-weight:600;")
        layout.addWidget(mkt_label)

        self.market_combo = QComboBox()
        markets = list_all()
        for m in markets:
            self.market_combo.addItem(m.label, m.code)
        self.market_combo.currentIndexChanged.connect(self._on_market_changed)
        layout.addWidget(self.market_combo)

        # ── Scrollable params ─────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)

        # --- EMA Compression ---
        ema_g = QGroupBox("EMA Compression")
        ema_l = QVBoxLayout(ema_g)
        self.ema_periods = _multi("Periods", [10, 20, 50, 100, 200], [20, 50, 100, 200])
        ema_l.addWidget(self.ema_periods)
        self.divergence_pct = _sld("Divergence %", 1.0, 10.0, DIVERGENCE_THRESHOLD, 0.5)
        ema_l.addWidget(self.divergence_pct)
        self.compress_bars = _sld("Min Compress Bars", 2, 20, MIN_COMPRESSION_BARS)
        ema_l.addWidget(self.compress_bars)
        pl.addWidget(ema_g)

        # --- Volume ---
        vol_g = QGroupBox("Volume")
        vol_l = QVBoxLayout(vol_g)
        self.vol_daily = _sp("Daily Vol Min", 0, 100_000_000, VOL_MIN, 100_000)
        vol_l.addWidget(self.vol_daily)
        self.vol_hourly = _sp("Hourly Vol Min", 0, 100_000_000, VOL_MIN_HOURLY, 10_000)
        vol_l.addWidget(self.vol_hourly)
        self.vol_weekly = _sp("Weekly Vol Min", 0, 100_000_000, WEEKLY_VOL_MIN, 100_000)
        vol_l.addWidget(self.vol_weekly)
        self.vol_d_kdj = _sp("KDJ Vol Min", 0, 100_000_000, DAILY_VOL_MIN, 100_000)
        vol_l.addWidget(self.vol_d_kdj)
        self.daily_vol_r = _sld("Daily KDJ Vol Ratio", 1.0, 5.0, DAILY_VOL_RATIO, 0.1)
        vol_l.addWidget(self.daily_vol_r)
        pl.addWidget(vol_g)

        # --- KDJ ---
        kdj_g = QGroupBox("KDJ")
        kdj_l = QVBoxLayout(kdj_g)
        self.kdj_period = _sld("Period", 3, 30, KDJ_PERIOD)
        kdj_l.addWidget(self.kdj_period)
        self.kdj_signal = _sld("Signal Period", 1, 10, KDJ_SIGNAL)
        kdj_l.addWidget(self.kdj_signal)
        self.div_lookback = _sld("Div Lookback", 10, 60, DIVERGENCE_LOOKBACK, 5)
        kdj_l.addWidget(self.div_lookback)
        pl.addWidget(kdj_g)

        # --- Scoring ---
        score_g = QGroupBox("Scoring System")
        score_l = QVBoxLayout(score_g)
        self.score_trend_p = _multi("Trend Periods", [10, 20, 50, 100, 200], SCORE_TREND_PERIODS)
        score_l.addWidget(self.score_trend_p)
        self.score_trend_div = _dbl("Trend Divergence %", 1.0, 20.0, SCORE_TREND_THRESHOLD, 0.5)
        score_l.addWidget(self.score_trend_div)
        self.score_slope = _sld("EMA200 Slope Bars", 5, 60, SCORE_EMA200_SLOPE_BARS, 5)
        score_l.addWidget(self.score_slope)
        self.score_vol_p = _sld("Vol Period", 5, 120, SCORE_VOL_PERIOD, 5)
        score_l.addWidget(self.score_vol_p)
        self.score_vol_t = _dbl("Vol Threshold %", 1.0, 50.0, SCORE_VOL_THRESHOLD, 1.0)
        score_l.addWidget(self.score_vol_t)
        self.score_vol_ma_b = _sld("Vol MA Bars", 2, 20, SCORE_VOL_MA_BARS)
        score_l.addWidget(self.score_vol_ma_b)
        self.score_vol_ma_t = _dbl("Vol MA Threshold", 1.0, 20.0, SCORE_VOL_MA_THRESHOLD, 1.0)
        score_l.addWidget(self.score_vol_ma_t)
        self.score_top_n = _sp("Top N", 5, 100, SCORE_TOP_N, 5)
        score_l.addWidget(self.score_top_n)
        pl.addWidget(score_g)

        pl.addStretch()
        scroll.setWidget(pw)
        layout.addWidget(scroll)

        # ── Run button ────────────────────────────────────────────────
        self.run_btn = QPushButton("▶  Run Screeners")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        self.run_btn.setMinimumHeight(44)
        layout.addWidget(self.run_btn)

        # ── Auto-refresh ──────────────────────────────────────────────
        ar = QHBoxLayout()
        self.auto_refresh = QCheckBox("Auto-refresh (5 min)")
        ar.addWidget(self.auto_refresh)
        ar.addStretch()
        self.status_tip = QLabel("")
        self.status_tip.setStyleSheet("color:#484f58; font-size:11px;")
        ar.addWidget(self.status_tip)
        layout.addLayout(ar)

    def _on_market_changed(self, index):
        code = self.market_combo.currentData()
        if code:
            m = get_market(code)
            d = m.defaults
            self.vol_daily.spin.setValue(d.get("vol_d", 200_000))
            self.vol_hourly.spin.setValue(d.get("vol_h", 20_000))
            self.vol_weekly.spin.setValue(d.get("vol_w", 500_000))
            self.vol_d_kdj.spin.setValue(d.get("vol_d_kdj", 500_000))
            self.market_changed.emit(code)

    def get_params(self) -> dict:
        def _sld_val(w):
            step = w.step
            v = w.slider.value()
            return v * step if step < 1 else v

        def _multi_vals(w):
            return [w.options[i] for i, cb in enumerate(w.boxes) if cb.isChecked()]

        return {
            "market_code": self.market_combo.currentData(),
            "ema_periods": _multi_vals(self.ema_periods),
            "ema_threshold": _sld_val(self.divergence_pct),
            "compress_bars": _sld_val(self.compress_bars),
            "vol_daily": self.vol_daily.spin.value(),
            "vol_hourly": self.vol_hourly.spin.value(),
            "vol_weekly": self.vol_weekly.spin.value(),
            "vol_daily_kdj": self.vol_d_kdj.spin.value(),
            "daily_vol_ratio": _sld_val(self.daily_vol_r),
            "kdj_period": _sld_val(self.kdj_period),
            "kdj_signal": _sld_val(self.kdj_signal),
            "div_lookback": _sld_val(self.div_lookback),
            "score_trend_periods": _multi_vals(self.score_trend_p),
            "score_trend_div": self.score_trend_div.spin.value(),
            "score_slope_bars": _sld_val(self.score_slope),
            "score_vol_p": _sld_val(self.score_vol_p),
            "score_vol_t": self.score_vol_t.spin.value(),
            "score_vol_ma_b": _sld_val(self.score_vol_ma_b),
            "score_vol_ma_t": self.score_vol_ma_t.spin.value(),
            "score_top_n": self.score_top_n.spin.value(),
        }
