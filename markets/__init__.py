"""Market configuration registry — auto-loads all known markets."""

from .base import MarketConfig, get, list_all, register

# Auto-register built-in markets
from . import bursa   # noqa: F401  — registers "my"
from . import us       # noqa: F401  — registers "us"

__all__ = ["MarketConfig", "get", "list_all", "register"]
