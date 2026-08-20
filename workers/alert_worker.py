"""Weekly KDJ golden-cross alert worker (built into the desktop app).

After each completed screening run, this worker re-runs the weekly KDJ
screener over the already-loaded market data, finds fresh 'crossed' signals
and compares them against the last-notified state persisted in
<cache>/alerts_state.json. New crosses are emitted for tray notifications.
"""

import json
import logging
import os
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from screener import WEEKLY_VOL_MIN, run_weekly_kdj_screener
from utils import cache_dir

logger = logging.getLogger(__name__)


def alerts_state_path() -> str:
    """Persisted alert state lives next to the day-cache."""
    return os.path.join(cache_dir(), "alerts_state.json")


def load_state(path: str | None = None) -> dict:
    """Load {notified: {ticker: {signal, time}}} — never raises."""
    path = path or alerts_state_path()
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
            if isinstance(state, dict) and isinstance(state.get("notified"), dict):
                return state
    except (OSError, ValueError) as e:
        logger.warning("Alert state read failed (%s): %s", path, e)
    return {"notified": {}}


def save_state(state: dict, path: str | None = None) -> None:
    """Best-effort write of the alert state."""
    path = path or alerts_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("Alert state write failed (%s): %s", path, e)


def find_new_crosses(data, ticker_names, vol_min: int, state: dict) -> list[dict]:
    """Run the weekly KDJ screener and return only fresh golden crosses.

    A stock alerts once per 'crossed' signal; re-notifying only happens after
    the signal changed (e.g. crossed -> above -> crossed again).
    """
    results = list(run_weekly_kdj_screener(
        data, ticker_names, vol_min=vol_min,
    ))
    notified = state.setdefault("notified", {})
    new_alerts = []
    for r in results:
        signal = r.get("kdj_signal")
        if signal != "crossed":
            continue
        ticker = r.get("ticker")
        prev = notified.get(ticker, {})
        if prev.get("signal") == "crossed":
            continue  # already alerted for this cross
        notified[ticker] = {
            "signal": signal,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        new_alerts.append(r)
    return new_alerts


class AlertWorker(QThread):
    """Runs the weekly KDJ check in the background; emits new alerts."""

    finished = pyqtSignal(list)   # list of new alert dicts
    error = pyqtSignal(str)

    def __init__(self, data, ticker_names, vol_min: int = WEEKLY_VOL_MIN, parent=None):
        super().__init__(parent)
        self.data = data
        self.ticker_names = ticker_names
        self.vol_min = vol_min

    def run(self):
        try:
            state = load_state()
            new_alerts = find_new_crosses(self.data, self.ticker_names, self.vol_min, state)
            if new_alerts:
                save_state(state)
                logger.info("AlertWorker: %d new weekly KDJ crosses", len(new_alerts))
            self.finished.emit(new_alerts)
        except Exception as e:
            logger.exception("AlertWorker failed")
            self.error.emit(str(e))
