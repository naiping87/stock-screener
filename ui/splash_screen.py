"""Splash screen shown during app startup."""

from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient


def create_splash() -> QSplashScreen:
    """Create and show a splash screen. Returns the splash object."""
    pixmap = QPixmap(480, 260)
    pixmap.fill(QColor("#0d1117"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Gradient accent line at top
    gradient = QLinearGradient(0, 0, pixmap.width(), 0)
    gradient.setColorAt(0.0, QColor("#1f6feb"))
    gradient.setColorAt(0.5, QColor("#3fb950"))
    gradient.setColorAt(1.0, QColor("#58a6ff"))
    painter.fillRect(0, 0, pixmap.width(), 3, gradient)

    # Title
    font_title = QFont("Segoe UI", 28, QFont.Weight.Bold)
    painter.setFont(font_title)
    painter.setPen(QColor("#e6edf3"))
    painter.drawText(pixmap.rect().adjusted(0, 40, 0, -120),
                     Qt.AlignmentFlag.AlignHCenter, "Stock Screener Pro")

    # Subtitle
    font_sub = QFont("Segoe UI", 13)
    painter.setFont(font_sub)
    painter.setPen(QColor("#8b949e"))
    painter.drawText(pixmap.rect().adjusted(0, 80, 0, -80),
                     Qt.AlignmentFlag.AlignHCenter, "Multi-Market Stock Screening Terminal")

    # Version
    font_ver = QFont("Segoe UI", 10)
    painter.setFont(font_ver)
    painter.setPen(QColor("#484f58"))
    painter.drawText(pixmap.rect().adjusted(0, 180, 0, -20),
                     Qt.AlignmentFlag.AlignHCenter, "v1.0.0  |  Bursa · NYSE · NASDAQ · SSE")

    painter.end()

    splash = QSplashScreen(pixmap, Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    QApplication.processEvents()
    return splash
