"""Stock Screener Pro — Multi-market stock screening terminal.

Usage:
    python main.py              # launch with splash screen
    python main.py --no-splash  # skip splash
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from ui.splash_screen import create_splash
from ui.main_window import MainWindow
from ui.styles import STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("Stock Screener Pro")
    app.setOrganizationName("StockScreenerPro")

    # ── Splash screen ──────────────────────────────────────────────────
    no_splash = "--no-splash" in sys.argv
    splash = None if no_splash else create_splash()

    # ── Main window ────────────────────────────────────────────────────
    window = MainWindow()

    if splash:
        # Close splash after a brief delay
        QTimer.singleShot(800, lambda: splash.close())
        QTimer.singleShot(900, window.show)
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
