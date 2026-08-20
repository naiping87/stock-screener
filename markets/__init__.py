"""Market configuration registry — auto-loads all known markets."""

# Auto-register built-in markets
from . import (
    bursa,  # noqa: F401  — registers "my"
    shanghai,  # noqa: F401  — registers "sh"
    us,  # noqa: F401  — registers "us"
)
from .base import MarketConfig, get, list_all, register

__all__ = ["MarketConfig", "get", "list_all", "register"]
