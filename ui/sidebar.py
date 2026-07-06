"""Sidebar — market selector + all screener parameter groups."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QGroupBox, QPushButton,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QSlider,
    QHBoxLayout, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings

from markets import list_all, get as get_market


class LabeledSpin(QWidget):
    """A label + spin box pair, saves boilerplate."""
    def __init__(self, label, min_val, max_val, default, step=1, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label)
        lbl.setMinimumWidth(100)
        layout.addWidget(lbl)
        self.spin = QSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setValue(default)
        self.spin.setSingleStep(step)
        layout.addWidget(self.spin)
        layout.addStretch()

    def value(self):
        return self.spin.value()

    def setValue(self, v):
        self.spin.setValue(v)


class LabeledDouble(QWidget):
    def __init__(self, label, min_val, max_val, default, step=0.1, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label)
        lbl.setMinimumWidth(100)
        layout.addWidget(lbl)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(min_val, max_val)
        self.spin.setValue(default)
        self.spin.setSingleStep(step)
        layout.addWidget(self.spin)
        layout.addStretch()

    def value(self):
        return self.spin.value()

    def setValue(self, v):
        self.spin.setValue(v)


class Sidebar(QWidget):
    run_clicked = pyqtSignal()
    market_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Market selector ───────────────────────────────────────────
        market_label = QLabel("Market")
        market_label.setStyleSheet("font-weight:600; color:#58a6ff; font-size:13px;")
        layout.addWidget(market_label)

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
        pl.setSpacing(8)

        # --- EMA Compression ---
        ema_g = QGroupBox("EMA Compression")
        ema_l = QVBoxLayout(ema_g)
        self.ema_periods_label = QLabel("Periods: 20, 50, 100, 200")
        ema_l.addWidget(self.ema_periods_label)
        self.ema_threshold = LabeledDouble("Threshold %", 1.0, 20.0, 5.0)
        ema_l.addWidget(self.ema_threshold)
        self.compress_bars = LabeledSpin("Min Bars", 2, 50, 8)
        ema_l.addWidget(self.compress_bars)
        pl.addWidget(ema_g)

        # --- KDJ ---
        kdj_g = QGroupBox("KDJ Parameters")
        kdj_l = QVBoxLayout(kdj_g)
        self.kdj_period = LabeledSpin("Period", 3, 30, 20)
        kdj_l.addWidget(self.kdj_period)
        self.kdj_signal = LabeledSpin("Signal", 1, 10, 5)
        kdj_l.addWidget(self.kdj_signal)
        self.div_lookback = LabeledSpin("Div Lookback", 5, 60, 20)
        kdj_l.addWidget(self.div_lookback)
        pl.addWidget(kdj_g)

        # --- Volume ---
        vol_g = QGroupBox("Volume Thresholds")
        vol_l = QVBoxLayout(vol_g)
        self.vol_daily = LabeledSpin("Daily Min", 0, 100_000_000, 200_000, 100_000)
        vol_l.addWidget(self.vol_daily)
        self.vol_weekly = LabeledSpin("Weekly Min", 0, 100_000_000, 500_000, 100_000)
        vol_l.addWidget(self.vol_weekly)
        self.vol_hourly = LabeledSpin("Hourly Min", 0, 100_000_000, 20_000, 10_000)
        vol_l.addWidget(self.vol_hourly)
        self.daily_vol_ratio = LabeledDouble("Vol Ratio", 0.1, 10.0, 1.5)
        vol_l.addWidget(self.daily_vol_ratio)
        pl.addWidget(vol_g)

        # --- Scoring ---
        score_g = QGroupBox("Scoring")
        score_l = QVBoxLayout(score_g)
        self.score_top_n = LabeledSpin("Top N", 5, 100, 20)
        score_l.addWidget(self.score_top_n)
        pl.addWidget(score_g)

        pl.addStretch()
        scroll.setWidget(pw)
        layout.addWidget(scroll)

        # ── Run button ────────────────────────────────────────────────
        self.run_btn = QPushButton("▶  Run Screeners")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        self.run_btn.setMinimumHeight(42)
        layout.addWidget(self.run_btn)

        # ── Auto-refresh ──────────────────────────────────────────────
        ar_layout = QHBoxLayout()
        self.auto_refresh = QCheckBox("Auto-refresh (5 min)")
        ar_layout.addWidget(self.auto_refresh)
        layout.addLayout(ar_layout)

    def _on_market_changed(self, index):
        code = self.market_combo.currentData()
        if code:
            m = get_market(code)
            d = m.defaults
            self.vol_daily.setValue(d.get("vol_d", 200_000))
            self.vol_weekly.setValue(d.get("vol_w", 500_000))
            self.vol_hourly.setValue(d.get("vol_h", 20_000))
            self.kdj_period.setValue(d.get("kdj_p", 20))
            self.kdj_signal.setValue(d.get("kdj_s", 5))
            self.market_changed.emit(code)

    def get_params(self) -> dict:
        return {
            "market_code": self.market_combo.currentData(),
            "ema_periods": [20, 50, 100, 200],
            "ema_threshold": self.ema_threshold.value(),
            "compress_bars": self.compress_bars.value(),
            "kdj_period": self.kdj_period.value(),
            "kdj_signal": self.kdj_signal.value(),
            "div_lookback": self.div_lookback.value(),
            "vol_daily": self.vol_daily.value(),
            "vol_weekly": self.vol_weekly.value(),
            "vol_hourly": self.vol_hourly.value(),
            "daily_vol_ratio": self.daily_vol_ratio.value(),
            "score_top_n": self.score_top_n.value(),
        }
