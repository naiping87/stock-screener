"""
Demo automation: launch the desktop app, trigger a screening run (it will
reuse today's day-cache, no network needed), wait for Phase-1 results, and
save screenshots of the main window + the Phase-1 tab.

Run: python tools/demo_screenshot.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "demo")
os.makedirs(OUT, exist_ok=True)

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from ui.main_window import MainWindow
    win = MainWindow()
    win.show()

    def capture(name: str) -> None:
        try:
            pixmap = win.grab()
            path = os.path.join(OUT, name)
            pixmap.save(path, "PNG")
            print(f"  saved {path}", flush=True)
        except Exception as e:
            print(f"  capture {name} failed: {e}", flush=True)

    def step_run():
        try:
            print("triggering screeners...", flush=True)
            win._on_run_screeners()
        except Exception:
            import traceback
            traceback.print_exc()

    def step_wait():
        import traceback
        try:
            for _ in range(300):
                app.processEvents()
                _p1 = win._result_dfs.get("phase1")
                if _p1 is not None and not win._busy:
                    break
                time.sleep(0.5)
            _p1 = win._result_dfs.get("phase1")
            _n = 0 if _p1 is None else (len(_p1) if isinstance(_p1, (list, tuple)) else len(_p1.index))
            print("busy:", win._busy, "phase1 rows:", _n, flush=True)
            capture("01_main.png")

            try:
                panel = win.results_panel
                idx = panel._tab_index.get("phase1")
                if idx is not None:
                    panel.tabs.setCurrentIndex(idx)
                    app.processEvents()
                    time.sleep(0.8)
                    capture("02_phase1.png")
            except Exception as e:
                print("tab switch failed:", e, flush=True)
            print("DONE", flush=True)
        except Exception:
            traceback.print_exc()
        app.quit()

    # first entry: run screeners after window shows
    QTimer.singleShot(1200, step_run)
    QTimer.singleShot(2500, step_wait)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
