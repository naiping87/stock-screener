"""
Market configuration base class.
Each market subclasses or instantiates MarketConfig with its own parameters.
"""

from dataclasses import dataclass, field


@dataclass
class MarketConfig:
    # ── Identity ────────────────────────────────────────────────────────
    code: str                # "my", "us", "hk", "cn"
    label: str               # "🇲🇾 Bursa Malaysia"
    yahoo_suffix: str        # ".KL", "", ".HK", ".SS"
    timezone: str            # "Asia/Kuala_Lumpur", "America/New_York", ...

    # ── Tickers ─────────────────────────────────────────────────────────
    tickers_csv: str = ""    # path to tickers CSV (relative to project root)

    # ── Data provider ────────────────────────────────────────────────────
    data_provider: str = "yahoo"   # "yahoo" or "akshare"

    # ── Volume thresholds (daily/weekly MA) ─────────────────────────────
    vol_daily_min: int = 500_000
    vol_weekly_min: int = 500_000
    vol_hourly_min: int = 20_000
    vol_daily_kdj: int = 500_000  # daily KDJ volume filter

    # ── UI defaults ─────────────────────────────────────────────────────
    defaults: dict = field(default_factory=dict)

    # ── Derived helpers ─────────────────────────────────────────────────
    @property
    def strip_suffix(self) -> str:
        """Suffix to strip when displaying tickers."""
        return self.yahoo_suffix

    def add_suffix(self, raw_code: str) -> str:
        """Add Yahoo suffix to a raw ticker code."""
        return f"{raw_code}{self.yahoo_suffix}"

    def display_ticker(self, full_ticker: str) -> str:
        """Convert internal ticker to display format (strip suffix)."""
        if self.yahoo_suffix and isinstance(full_ticker, str):
            return full_ticker.replace(self.yahoo_suffix, "")
        return full_ticker


# ── Registry ────────────────────────────────────────────────────────────

_BUILTIN: dict[str, MarketConfig] = {}

def register(config: MarketConfig) -> MarketConfig:
    _BUILTIN[config.code] = config
    return config

def get(code: str) -> MarketConfig | None:
    return _BUILTIN.get(code)

def list_all() -> list[MarketConfig]:
    return list(_BUILTIN.values())
