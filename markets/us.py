"""US Stock Market (NYSE + NASDAQ) configuration."""

from .base import MarketConfig, register

US = register(MarketConfig(
    code="us",
    label="🇺🇸 US Market",
    yahoo_suffix="",            # US stocks have no suffix
    timezone="America/New_York",
    tickers_csv="tickers/us.csv",

    # US stocks trade much higher volume — raise thresholds
    vol_daily_min=500_000,
    vol_weekly_min=1_000_000,
    vol_hourly_min=50_000,
    vol_daily_kdj=500_000,

    defaults={
        "vol_d": 500_000,
        "vol_w": 1_000_000,
        "vol_h": 50_000,
        "vol_d_kdj": 500_000,
        "daily_vol_r": 1.5,
        "kdj_p": 20,
        "kdj_s": 5,
        "div_lookback": 20,
        "daily_days": 400,
        "hourly_days": 50,
        "ema_p": 20,
    },
))
