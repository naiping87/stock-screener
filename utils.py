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
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative_path: str) -> str:
    """Resolve a path relative to the project root."""
    return os.path.join(base_dir(), relative_path)
