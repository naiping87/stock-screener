"""Utility to resolve resource paths (works both in dev and PyInstaller bundles)."""

import os
import sys


def base_dir() -> str:
    """Return the project root directory.

    In development:       the directory containing main.py
    In PyInstaller bundle: the temp extraction directory (sys._MEIPASS)
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    # utils.py lives at the project root, so a single dirname() is the root.
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    """Resolve a path relative to the project root."""
    return os.path.join(base_dir(), relative_path)


def cache_dir() -> str:
    """Return a writable cache directory (created if missing).

    In development: <project root>/cache
    In PyInstaller bundle: %APPDATA%/StockScreenerPro/cache  (Program Files is not writable)
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "StockScreenerPro", "cache")
    else:
        d = os.path.join(base_dir(), "cache")
    os.makedirs(d, exist_ok=True)
    return d
