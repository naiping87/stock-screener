"""System tray icon with dock-to-tray + notifications."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class SystemTray(QObject):
    show_window = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(self._make_icon(), parent)
        self._tray.setToolTip("Stock Screener Pro")

        menu = QMenu()
        show_action = QAction("Show", menu)
        show_action.triggered.connect(self.show_window.emit)
        menu.addAction(show_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

        self._alert_count = 0

    def _make_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(QColor("#0d1117"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#3fb950"))
        font = QFont("Segoe UI", 36, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pix.rect(), 0, "S")
        painter.end()
        return QIcon(pix)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window.emit()

    def notify(self, title: str, message: str):
        """Show a Windows toast notification."""
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def set_alert_count(self, count: int):
        self._alert_count = count
        if count > 0:
            self._tray.setToolTip(f"Stock Screener Pro — {count} alerts")
