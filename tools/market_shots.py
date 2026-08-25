"""
Marketing screenshots: launch the app windowed (real Windows rendering),
wait for the Ignition tab to populate, capture:
  - main window (full UI)
  - Ignition tab (large, scroll to top)
  - chart drill-down (pivot lines visible)

Saves to web project /screenshots/. Window closes automatically.

Run: python tools/market_shots.py
"""
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
    from PyQt6.QtGui import QFont

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1500, 940)
    win.show()

    def snap(widget, name: str):
        try:
            pm = widget.grab()
            path = os.path.join(WEB_SHOTS, name)
            pm.save(path, "PNG")
            print(f"  saved {path}", flush=True)
            return path
        except Exception as e:
            print(f"  snap {name} failed: {e}", flush=True)
            return None

    def step_run():
        try:
            win._on_run_screeners()
        except Exception:
            import traceback
            traceback.print_exc()

    def step_wait():
        for _ in range(600):
            app.processEvents()
            p1 = win._result_dfs.get("phase1")
            if p1 is not None and not win._busy:
                # let meta finish attaching + tables render
                for _ in range(10):
                    app.processEvents()
                    time.sleep(0.4)
                break
            time.sleep(0.5)
        print("ready. busy:", win._busy, flush=True)
        app.processEvents()
        time.sleep(1.0)
        snap(win, "app_main.png")

        # ── Ignition tab ────────────────
        try:
            panel = win.results_panel
            idx = panel._tab_index.get("phase1")
            if idx is not None:
                panel.tabs.setCurrentIndex(idx)
                app.processEvents()
                time.sleep(1.2)
                snap(win, "ignition_tab.png")
            else:
                print("no phase1 tab", flush=True)
        except Exception as e:
            print("ignition tab snap failed:", e, flush=True)

        # ── Chart drill-down (first ignition row) ────────────────
        try:
            p1 = win._result_dfs.get("phase1")
            if p1 is not None and not p1.empty:
                first = p1.iloc[0]["ticker"]
                win._open_chart(first)
                app.processEvents()
                time.sleep(2.5)
                for w in app.topLevelWidgets():
                    t = w.windowTitle()
                    if t and "(" in t:
                        w.resize(1100, 780)
                        app.processEvents()
                        time.sleep(0.8)
                        snap(w, "chart_pivot.png")
                        w.close()
                        break
            else:
                print("no rows for chart", flush=True)
        except Exception as e:
            print("chart snap failed:", e, flush=True)

        print("DONE", flush=True)
        win.close()
        app.quit()

    QTimer.singleShot(1200, step_run)
    QTimer.singleShot(3000, step_wait)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
