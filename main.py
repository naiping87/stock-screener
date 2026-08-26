"""Stock Screener Pro — Multi-market stock screening terminal.

Usage:
    python main.py              # launch with splash screen
    python main.py --no-splash  # skip splash
"""

import logging
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import i18n
from PyQt6.QtCore import QLockFile, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from licensing.license_manager import LicenseManager
from ui.activation import ActivationDialog
from ui.main_window import MainWindow
from ui.splash_screen import create_splash
from ui.styles import STYLESHEET
from ui.welcome import WelcomeDialog, should_show_welcome
from utils import cache_dir, resource_path

# Keep the lock alive for the whole process lifetime (GC would release it).
_APP_LOCK = None


def _setup_logging() -> None:
    """Log to <cache>/app.log (dev: <project>/cache; bundle: %APPDATA%) plus console."""
    log_path = os.path.join(cache_dir(), "app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _acquire_single_instance_lock() -> bool:
    """Prevent multiple app instances (a QLockFile in the temp dir).

    Returns False when another instance already holds the lock.
    """
    global _APP_LOCK
    lock_path = os.path.join(
        os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp",
        "StockScreenerPro.lock",
    )
    _APP_LOCK = QLockFile(lock_path)
    _APP_LOCK.setStaleLockTime(0)  # 0 = never auto-expire; crashed instances
    # leave a stale lock that must be cleaned up on next successful launch.
    if not _APP_LOCK.tryLock(100):
        return False
    return True


def main():
    _setup_logging()
    app = QApplication(sys.argv)
    # Fusion style — the dark STYLESHEET below targets Fusion's control
    # structure (checkbox indicators, slider grooves, combo arrows). Windows'
    # native style ignores part of it, so the packaged app rendered a
    # half-native/half-dark hybrid and looked worse than the dev run, which
    # always used Fusion. Keeping the two entry points identical.
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.setApplicationName("Stock Screener Pro")
    app.setOrganizationName("StockScreenerPro")

    icon_path = resource_path("resources/icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    if not _acquire_single_instance_lock():
        QMessageBox.information(
            None, "Stock Screener Pro",
            i18n.t("Stock Screener Pro is already running.\n\nOnly one instance can run at a time — check the system tray."),
        )
        sys.exit(0)

    # ── License check (block launch until activated) ─────────────────
    license_manager = LicenseManager()
    if not license_manager.is_activated():
        activation_dialog = ActivationDialog(license_manager)
        if activation_dialog.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.information(
                None, "Stock Screener Pro",
                i18n.t("This software requires a valid activation code to run.\n\nPlease contact the seller to obtain one."),
            )
            sys.exit(0)

    # ── Splash screen ──────────────────────────────────────────────────
    no_splash = "--no-splash" in sys.argv
    splash = None if no_splash else create_splash()

    # ── Main window ────────────────────────────────────────────────────
    window = MainWindow()

    def _finish_startup():
        window.show()
        if should_show_welcome():
            WelcomeDialog(window).exec()

    if splash:
        # Close splash after a brief delay
        QTimer.singleShot(800, lambda: splash.close())
        QTimer.singleShot(900, _finish_startup)
    else:
        _finish_startup()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
