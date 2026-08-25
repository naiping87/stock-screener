"""Chart-only marketing shot: open a real stock's chart dialog with pivot lines
and CLV chip, capture it, close. Run: python tools/chart_shot.py"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEB_SHOTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vercel-license-generator", "screenshots")
os.makedirs(WEB_SHOTS, exist_ok=True)


def main() -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Load market data through the normal path (cache or download)
    from workers.download_worker import DownloadWorker
    holder = {}

    win_holder = {}

    def on_data(data, ticker_names):
        holder["data"] = data
        holder["names"] = ticker_names
        print("data loaded:", len(data), flush=True)
        # pick a liquid stock with a clear recent pivot for the chart
        pick = None
        for tkr in ("5211.KL", "6262.KL", "5027.KL", "7167.KL", "6351.KL"):
            if tkr in data:
                pick = tkr
                break
        # fallback: first ticker
        if pick is None:
            pick = next(iter(data))
        print("picking:", pick, flush=True)
        from ui.chart_view import ChartDialog
        dlg = ChartDialog(pick, ticker_names.get(pick, pick), data[pick], None)
        dlg.resize(1120, 800)
        dlg.show()
        win_holder["dlg"] = dlg
        QTimer.singleShot(2500, snap)

    def snap():
        dlg = win_holder.get("dlg")
        if dlg is None:
            print("no dialog", flush=True)
            app.quit()
            return
        pm = dlg.grab()
        path = os.path.join(WEB_SHOTS, "chart_pivot.png")
        pm.save(path, "PNG")
        print("saved", path, flush=True)
        app.quit()

    worker = DownloadWorker("my", force_refresh=False)
    worker.finished.connect(on_data)
    worker.error.connect(lambda e: print("download error:", e, flush=True))
    worker.start()

    QTimer.singleShot(150000, lambda: (print("TIMEOUT", flush=True), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
