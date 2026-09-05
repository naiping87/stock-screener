"""Single source of truth for the app version shown in the UI.

Keep this in sync with `installer.iss` (AppVersion) and `pyproject.toml`.
Splash screen and the About box read from here so a release bump cannot
silently leave the UI on an old version.
"""

APP_VERSION = "1.2.9"
