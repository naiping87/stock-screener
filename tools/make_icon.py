"""Generate resources/icon.ico — TradingView-blue rounded square + white 'S'.

Usage: python tools/make_icon.py

Produces a multi-resolution ICO (16–256px, PNG-embedded Vista+ format).
PyQt6 is used only to rasterize the design; the ICO container is written
manually so no Qt ICO-writer plugin support is required.
"""

import os
import struct
import sys

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPixmap,
    QPolygonF,
)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _draw(size: int) -> bytes:
    """Rasterize one icon size and return PNG bytes."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    rect = QRectF(0, 0, size, size)
    radius = size * 0.22

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#2e6bff"))
    grad.setColorAt(1.0, QColor("#1e53e5"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(rect, radius, radius)

    if size >= 24:
        font = QFont("Segoe UI", int(size * 0.52), QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "S")

    if size >= 32:
        # Small green up-arrow (bullish) at bottom-right.
        s = float(size)
        tri = QPolygonF([
            QPointF(s * 0.70, s * 0.58),
            QPointF(s * 0.88, s * 0.58),
            QPointF(s * 0.79, s * 0.40),
        ])
        p.setBrush(QBrush(QColor("#089981")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(tri)

    p.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pm.save(buf, "PNG"):
        raise RuntimeError(f"PNG encode failed at size {size}")
    return bytes(buf.data())


def _write_ico(path: str, pngs: list[tuple[int, bytes]]) -> None:
    """Assemble a PNG-in-ICO container (Vista+ format)."""
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    offset = 6 + 16 * count
    for size, data in pngs:
        dim = 0 if size >= 256 else size  # 0 encodes 256 in the ICO header
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + entries)
        for _, data in pngs:
            f.write(data)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 — required for QPixmap
    pngs = [(size, _draw(size)) for size in SIZES]
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "resources", "icon.ico",
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    _write_ico(out, pngs)
    print(f"Wrote {out} ({os.path.getsize(out)} bytes, "
          f"{len(pngs)} resolutions: {SIZES})")


if __name__ == "__main__":
    main()
