#!/usr/bin/env python3
"""
Stock Screener Alert Monitor
Run every 10 minutes via Windows Task Scheduler.
Detects new Weekly KDJ golden crosses and shows Windows desktop notifications.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from screener import (
    load_tickers, download_data,
    run_weekly_kdj_screener,
    KDJ_PERIOD, KDJ_SIGNAL, WEEKLY_VOL_MIN,
)

STATE_FILE = SCRIPT_DIR / "alert_state.json"
TICKERS_FILE = SCRIPT_DIR / "tickers.csv"

# ===== Windows Toast Notification =====

def show_toast(title, message):
    """Show Windows toast notification using PowerShell."""
    try:
        import subprocess
        ps_script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Stock Screener").Show($toast)
        '''
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        # Fallback: print to console
        print(f"[NOTIFICATION] {title}: {message}")
        print(f"  (Toast failed: {e})")


# ===== Alert State Management =====

def load_state():
    """Load previously alerted stocks."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"alerted": {}}


def save_state(state):
    """Save alerted stocks state."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def should_alert(ticker, signal, state):
    """
    Decide whether to alert for this ticker.
    - New cross → alert
    - Already alerted with same signal → skip
    - Changed signal (e.g., 'above' → 'crossed') → alert
    """
    prev = state["alerted"].get(ticker, {})
    prev_signal = prev.get("signal")
    prev_time = prev.get("time", "")

    if signal != prev_signal:
        return True  # signal changed → alert
    if signal == "crossed" and prev_signal == "crossed":
        # Already alerted for this cross, skip
        return False
    return False


def update_alerted(ticker, signal, name, state):
    """Record that we alerted this ticker."""
    state["alerted"][ticker] = {
        "signal": signal,
        "name": name,
        "time": datetime.now().isoformat(),
    }


# ===== Main =====

def main():
    print(f"\n{'='*50}")
    print(f"  Stock Screener Alert Monitor")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    # 1. Load tickers
    tickers = load_tickers(str(TICKERS_FILE))
    print(f"\n[INFO] {len(tickers)} tickers loaded")

    # 2. Download latest daily data
    print("[INFO] Downloading latest data...")
    data = download_data(tickers, progress_cb=None)
    print(f"[INFO] Data for {len(data)} tickers")

    # 3. Run weekly KDJ screener
    print("[INFO] Running weekly KDJ screener...")
    results = list(run_weekly_kdj_screener(
        data, tickers, vol_min=WEEKLY_VOL_MIN,
    ))
    print(f"[INFO] {len(results)} stocks passed weekly KDJ filter")

    # 4. Filter for 'crossed' signals only
    crossed = [r for r in results if r.get("kdj_signal") == "crossed"]
    print(f"[INFO] {len(crossed)} with fresh golden cross")

    # 5. Check against alert state
    state = load_state()
    new_alerts = []
    changed_alerts = []

    for r in sorted(crossed, key=lambda x: x.get("ticker", "")):
        ticker = r["ticker"]
        name = r["name"]
        signal = r["kdj_signal"]
        j_val = r.get("kdj_j", "?")
        k_val = r.get("kdj_k", "?")

        if should_alert(ticker, signal, state):
            prev = state["alerted"].get(ticker, {})
            if prev.get("signal") is None:
                new_alerts.append(r)
            else:
                changed_alerts.append(r)
            update_alerted(ticker, signal, name, state)
            print(f"  [NEW] ALERT: {name} ({ticker}) KDJ J={j_val} K={k_val}")

    save_state(state)

    # 6. Show notifications
    total = len(new_alerts) + len(changed_alerts)
    if total == 0:
        print("[INFO] No new alerts. All quiet.")
        # Optional: silent exit, no notification
        return

    # Group notifications
    if total <= 3:
        for r in new_alerts + changed_alerts:
            name = r["name"]
            ticker = r["ticker"]
            k = r.get("kdj_k", "?")
            j = r.get("kdj_j", "?")
            d = r.get("kdj_d", "?")
            price = r.get("close", "?")
            show_toast(
                f"KDJ Cross: {name}",
                f"{ticker} | Price: RM{price} | J={j} K={k} D={d} | Weekly KDJ crossed"
            )
    else:
        show_toast(
            f"🔔 Stock Screener Alert",
            f"{total} stocks with new weekly KDJ golden cross detected"
        )
        for r in new_alerts[:5]:
            print(f"  - {r['name']} ({r['ticker']})")

    print(f"\n[DONE] {total} alerts sent")


if __name__ == "__main__":
    main()
