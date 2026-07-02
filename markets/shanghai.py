"""Shanghai A-Share market configuration (AkShare data)."""

from .base import MarketConfig, register

SHANGHAI = register(MarketConfig(
    code="sh",
    label="🇨🇳 上海 A股",
    yahoo_suffix="",             # not used — data via AkShare
    timezone="Asia/Shanghai",
    tickers_csv="tickers/shanghai.csv",
    data_provider="akshare",     # use AkShare instead of Yahoo Finance

    vol_daily_min=2_000_000,     # A-shares trade high volume
    vol_weekly_min=2_000_000,
    vol_hourly_min=100_000,
    vol_daily_kdj=2_000_000,

    defaults={
        "vol_d": 2_000_000,
        "vol_w": 2_000_000,
        "vol_h": 100_000,
        "vol_d_kdj": 2_000_000,
        "daily_vol_r": 1.5,
        "kdj_p": 20,
        "kdj_s": 5,
        "div_lookback": 20,
        "daily_days": 400,
        "hourly_days": 50,
        "ema_p": 20,
    },
))
