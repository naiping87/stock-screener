"""First-run welcome dialog — quick orientation for new users."""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .styles import ACCENT, BG_SURFACE, BG_WINDOW, BORDER, TEXT, TEXT_SEC

_SETTINGS_ORG = "StockScreenerPro"
_SETTINGS_APP = "Onboarding"
_WELCOME_KEY = "welcome_shown"

_TIPS = [
    ("1. Pick a market & run",
     "Choose a market in the sidebar, tweak the filters, then click Run Screeners."),
    ("2. Read the tables",
     "Every tab shows one screener with result counts. Hover column headers for "
     "tooltips; use the search box to filter any column."),
    ("3. Drill into any stock",
     "Double-click a result row to open the candlestick chart (Daily/Weekly, "
     "EMA + KDJ + volume). Scroll to zoom, drag to pan."),
    ("4. Get alerted",
     "Enable 'Weekly KDJ alerts' to get a tray notification the first time a "
     "stock prints a weekly golden cross."),
    ("5. Stay fresh",
     "F5 / Refresh Data forces a fresh download; Auto-refresh re-runs every 5 minutes."),
]


def should_show_welcome() -> bool:
    return not QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_WELCOME_KEY, False, type=bool)


class WelcomeDialog(QDialog):
    """One-time orientation dialog shown after the first launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Stock Screener Pro")
        self.setModal(True)
        self.resize(560, 460)
        self.setStyleSheet(
            f"QDialog {{ background: {BG_WINDOW}; }}"
            f"QLabel {{ color: {TEXT}; background: transparent; }}"
            f"QCheckBox {{ color: {TEXT_SEC}; font-size: 12px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        title = QLabel("Welcome to Stock Screener Pro")
        title.setStyleSheet(f"color:{TEXT}; font-size:22px; font-weight:700;")
        layout.addWidget(title)

        sub = QLabel("A multi-market screening terminal — here's how to get the most out of it:")
        sub.setStyleSheet(f"color:{TEXT_SEC}; font-size:13px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(6)

        for head, body in _TIPS:
            card = QLabel(f"<b>{head}</b><br/><span style='color:{TEXT_SEC};font-weight:400'>{body}</span>")
            card.setTextFormat(Qt.TextFormat.RichText)
            card.setWordWrap(True)
            card.setStyleSheet(
                f"background:{BG_SURFACE}; border:1px solid {BORDER}; border-radius:8px;"
                f" padding:10px 12px; font-size:12px;")
            layout.addWidget(card)

        layout.addStretch(1)

        self.dont_show = QCheckBox("Don't show this again")
        layout.addWidget(self.dont_show)

        row = QHBoxLayout()
        row.addStretch(1)
        get_started = QPushButton("Get Started")
        get_started.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none; border-radius:8px;"
            f" padding:10px 28px; font-size:14px; font-weight:600; }}"
            f"QPushButton:hover {{ background:#3b7aff; }}")
        get_started.clicked.connect(self.accept)
        row.addWidget(get_started)
        layout.addLayout(row)

    def accept(self):
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_WELCOME_KEY, True)
        super().accept()
