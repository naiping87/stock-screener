"""
Market session model (time-of-day awareness).

The whole Phase-1 pipeline must know whether it is seeing a COMPLETED trading
day (EOD mode — the close, the CLV, the volume are all final) or an
IN-PROGRESS one (intraday mode — CLV is unstable, the day's volume is only a
fraction of the eventual total). This module answers that question so the
engine can switch behaviour without knowing wall-clock times itself.

Bursa Malaysia sessions (Asia/Kuala_Lumpur):
  09:00–12:30  morning session
  12:30–14:30  lunch break
  14:30–17:00  afternoon session
  16:00–17:00  pre-close window (closing strength increasingly meaningful)

US (NYSE/NASDAQ, America/New_York):
  09:30–16:00  continuous (no lunch break)

Statuses returned by market_status():
  PRE_MARKET   — before the open
  OPENING      — first 30 minutes of the session (opening-noise protection)
  MORNING      — morning continuous session
  LUNCH        — market lunch break (Bursa only)
  AFTERNOON    — afternoon continuous session
  PRE_CLOSE    — last 60 minutes (closing strength becomes meaningful)
  CLOSED       — after the close / weekends / holidays

Pure functions — no I/O, fully unit-testable.
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Tuple

# Market session definitions (market code → list of (start, end, status) in
# local market time). Keep this table small and explicit; extend per market.
_SESSIONS: dict[str, list[Tuple[dtime, dtime, str]]] = {
    "my": [
        (dtime(9, 0), dtime(9, 30), "OPENING"),
        (dtime(9, 30), dtime(12, 30), "MORNING"),
        (dtime(12, 30), dtime(14, 30), "LUNCH"),
        (dtime(14, 30), dtime(16, 0), "AFTERNOON"),
        (dtime(16, 0), dtime(17, 0), "PRE_CLOSE"),
        (dtime(17, 0), dtime(17, 30), "CLOSED"),  # no evening session on Bursa
    ],
    "us": [
        (dtime(9, 30), dtime(10, 0), "OPENING"),
        (dtime(10, 0), dtime(15, 0), "MORNING"),
        (dtime(15, 0), dtime(16, 0), "PRE_CLOSE"),
    ],
}


def session_count() -> int:
    return len(_SESSIONS)


def market_status(market_code: str, now: datetime, tz_name: str = "Asia/Kuala_Lumpur") -> str:
    """The market session at `now` (a tz-aware datetime).

    `now` should already be in the market's local time (or be converted here —
    the caller passes market-local time; timezone conversion is the caller's
    concern so this stays a pure lookup).
    """
    t = now.time()
    sessions = _SESSIONS.get(market_code, [])
    for start, end, status in sessions:
        if start <= t < end:
            return status
    # Between the last session and midnight (or before the first): closed.
    return "CLOSED"


def is_closed(market_code: str, now: datetime, tz_name: str = "Asia/Kuala_Lumpur") -> bool:
    """True when the market is not trading at `now` (weekend included is
    handled by the caller — a Saturday 10:00 has no session in the table, so
    this returns CLOSED; the caller decides weekend handling)."""
    return market_status(market_code, now, tz_name) in ("CLOSED", "PRE_MARKET")


def session_mode(market_code: str, now: datetime, tz_name: str = "Asia/Kuala_Lumpur") -> str:
    """High-level mode for the screener:
      "eod"      — market closed; CLV and volume are FINAL (hard filter OK)
      "intraday" — market trading (or in lunch/pre-close); CLV unstable,
                   volume partial — CLV must NOT hard-filter, volume needs
                   time-of-day normalization.
    """
    s = market_status(market_code, now, tz_name)
    if s in ("CLOSED", "PRE_MARKET"):
        return "eod"
    return "intraday"


def session_label(status: str) -> str:
    """Human label for the UI badge."""
    return {
        "PRE_MARKET": "Pre-market",
        "OPENING": "Opening",
        "MORNING": "Morning session",
        "LUNCH": "Lunch break",
        "AFTERNOON": "Afternoon session",
        "PRE_CLOSE": "Pre-close",
        "CLOSED": "Market closed",
    }.get(status, status)
