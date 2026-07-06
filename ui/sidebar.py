"""Sidebar — market selector + parameter groups."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QGroupBox, QPushButton,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox, QSlider,
    QHBoxLayout, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from markets import list_all, get as get_market


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
        layout.setSpacing(8)

        # ── Market selector ───────────────────────────────────────────
        market_label = QLabel("Market")
        market_label.setStyleSheet("font-weight:600; color:#58a6ff;")
        layout.addWidget(market_label)

        self.market_combo = QComboBox()
        markets = list_all()
        for m in markets:
            self.market_combo.addItem(m.label, m.code)
        self.market_combo.currentIndexChanged.connect(self._on_market_changed)
        layout.addWidget(self.market_combo)

        # ── Scrollable parameter area ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        param_widget = QWidget()
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.setSpacing(6)

        # EMA Compression group
        ema_group = QGroupBox("EMA Compression")
        ema_layout = QVBoxLayout(ema_group)
        ema_layout.addWidget(QLabel("EMA Periods (comma-separated)"))
        ema_layout.addWidget(QLabel("(e.g. 20,50,100,200)"))
        ema_layout.addWidget(QLabel("Not yet implemented"))
        param_layout.addWidget(ema_group)

        # KDJ group
        kdj_group = QGroupBox("KDJ Parameters")
        kdj_layout = QVBoxLayout(kdj_group)

        kdj_layout.addWidget(QLabel("KDJ Period"))
        self.kdj_period = QSpinBox()
        self.kdj_period.setRange(3, 30)
        self.kdj_period.setValue(20)
        kdj_layout.addWidget(self.kdj_period)

        kdj_layout.addWidget(QLabel("KDJ Signal Period"))
        self.kdj_signal = QSpinBox()
        self.kdj_signal.setRange(1, 10)
        self.kdj_signal.setValue(5)
        kdj_layout.addWidget(self.kdj_signal)
        param_layout.addWidget(kdj_group)

        # Volume group
        vol_group = QGroupBox("Volume Thresholds")
        vol_layout = QVBoxLayout(vol_group)
        vol_layout.addWidget(QLabel("Daily Vol Min"))
        self.vol_daily = QSpinBox()
        self.vol_daily.setRange(0, 100_000_000)
        self.vol_daily.setSingleStep(100_000)
        self.vol_daily.setValue(200_000)
        vol_layout.addWidget(self.vol_daily)

        vol_layout.addWidget(QLabel("Weekly Vol Min"))
        self.vol_weekly = QSpinBox()
        self.vol_weekly.setRange(0, 100_000_000)
        self.vol_weekly.setSingleStep(100_000)
        self.vol_weekly.setValue(500_000)
        vol_layout.addWidget(self.vol_weekly)
        param_layout.addWidget(vol_group)

        # Scoring group
        score_group = QGroupBox("Scoring")
        score_layout = QVBoxLayout(score_group)
        score_layout.addWidget(QLabel("Not yet implemented"))
        param_layout.addWidget(score_group)

        param_layout.addStretch()
        scroll.setWidget(param_widget)
        layout.addWidget(scroll)

        # ── Run button ────────────────────────────────────────────────
        self.run_btn = QPushButton("▶  Run Screeners")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        layout.addWidget(self.run_btn)

        # ── Auto-refresh ──────────────────────────────────────────────
        refresh_layout = QHBoxLayout()
        self.auto_refresh = QCheckBox("Auto-refresh (5 min)")
        refresh_layout.addWidget(self.auto_refresh)
        layout.addLayout(refresh_layout)

    def _on_market_changed(self, index):
        code = self.market_combo.currentData()
        if code:
            self.market_changed.emit(code)

    def get_params(self) -> dict:
        return {
            "market_code": self.market_combo.currentData(),
            "kdj_period": self.kdj_period.value(),
            "kdj_signal": self.kdj_signal.value(),
            "vol_daily": self.vol_daily.value(),
            "vol_weekly": self.vol_weekly.value(),
        }
