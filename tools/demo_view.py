"""
Launch the desktop app windowed (real Windows rendering — proper fonts),
auto-trigger one screening run (reuses today's day-cache), and save a
Phase-1 screenshot for reference. The window STAYS OPEN for the user.

Run: python tools/demo_view.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "demo")
os.makedirs(OUT, exist_ok=True)


def main() -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1440, 900)
    win.show()

    def step_run():
        try:
            print("triggering screeners...", flush=True)
            win._on_run_screeners()
        except Exception:
            import traceback
            traceback.print_exc()

    def step_wait_capture():
        import traceback
        try:
            _p1 = win._result_dfs.get("phase1")
            if _p1 is None:
                print("no phase1 yet, will retry in 30s...", flush=True)
                QTimer.singleShot(30000, step_wait_capture)
                return
            app.processEvents()
            time.sleep(0.5)
            try:
                pixmap = win.grab()
                pixmap.save(os.path.join(OUT, "real_main.png"), "PNG")
                print("saved real_main.png", flush=True)
            except Exception as e:
                print("capture failed:", e, flush=True)
        except Exception:
            traceback.print_exc()
        print("WINDOW OPEN — run screeners already triggered. You can interact now.", flush=True)

    QTimer.singleShot(1000, step_run)
    QTimer.singleShot(4000, step_wait_capture)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
