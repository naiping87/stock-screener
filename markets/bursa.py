"""Bursa Malaysia market configuration."""

from .base import MarketConfig, register

BURSA = register(MarketConfig(
    code="my",
    label="🇲🇾 Bursa Malaysia",
    yahoo_suffix=".KL",
    timezone="Asia/Kuala_Lumpur",
    tickers_csv="tickers.csv",

    vol_daily_min=200_000,
    vol_weekly_min=500_000,
    vol_hourly_min=20_000,
    vol_daily_kdj=500_000,

    defaults={
        "vol_d": 200_000,
        "vol_w": 500_000,
        "vol_h": 20_000,
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
