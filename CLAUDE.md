# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Bursa Malaysia stock screener. Two interfaces: CLI (`screener.py`) and Streamlit web app (`streamlit_app.py`). Both pull data from Yahoo Finance (free, no API key). 1,000+ tickers in `tickers.csv`.

## Commands

```bash
# CLI — runs screener.py, writes output/ CSV
python screener.py

# Web app — local dev (hot-reloads on file change)
streamlit run streamlit_app.py

# Refresh ticker list from Bursa source
python update_tickers.py

# Install deps
pip install -r requirements.txt
```

## Architecture

**`screener.py`** — pure engine. No UI. Three screener functions:
- `run_sma_screener(data, ...)` → daily SMA compression filter
- `run_sma_hourly_screener(data, ...)` → hourly SMA compression filter
- `run_divergence_screener(data, ...)` → KDJ bullish divergence filter

All three consume the same data dict from `download_data()`, which fetches daily + hourly OHLCV from Yahoo v8 chart API concurrently (ThreadPoolExecutor, 10 workers). Data dict keys: `close`, `high`, `low`, `volume` (daily); `close_hourly`, `volume_hourly` (hourly); `name`.

**`streamlit_app.py`** — imports screening functions from `screener.py`. Adds password-protected UI, progress bars, ROE scoring (Yahoo quoteSummary endpoint with crumb auth), and parameter controls. Raw data cached 1hr in `st.session_state`; param changes re-run screeners on cached data without re-downloading.

**`update_tickers.py`** — scrapes `bestar-my.com` for latest Bursa Malaysia stock list, writes `tickers.csv`. Run manually when listings change.

## Data sources

| Data | Source | Auth |
|------|--------|------|
| Price/OHLCV (daily + hourly) | `query1.finance.yahoo.com/v8/finance/chart` | Session cookie from `fc.yahoo.com` |
| ROE | `query2.finance.yahoo.com/v10/finance/quoteSummary` | Cookie + crumb from `/v1/test/getcrumb` |
| Stock list | `bestar-my.com/post/list-of-public-listed-companies-bursa-malaysia` | None |

## Key config (screener.py top)

- `SMA_PERIODS` — MA periods used by compression filter
- `DIVERGENCE_THRESHOLD` — max divergence % for SMA compression
- `MIN_COMPRESSION_BARS` — how many consecutive bars must be tight
- `VOL_MIN` / `VOL_MIN_HOURLY` — volume MA thresholds
- `KDJ_PERIOD` / `KDJ_SIGNAL` / `DIVERGENCE_LOOKBACK` — KDJ params
- `DAILY_DAYS` / `HOURLY_DAYS` — how far back to fetch data

## Streamlit deployment

Deployed on Streamlit Cloud from `main` branch. Secrets managed in Cloud dashboard (not committed):
```toml
APP_PASSWORD = "your-password"
```
`.streamlit/secrets.toml` is gitignored (local dev only).

## Files never committed

- `output/` — generated CSV results
- `.claude/` — Claude local settings
- `.streamlit/secrets.toml` — local password

## Conventions

- `.KL` suffix on tickers internally, stripped for display
- Volume thresholds in raw units (e.g. 500000, not 500k)
- ROE stored as percentage (e.g. 11.16, not 0.1116)
- Result dicts share common keys where possible (`ticker`, `name`, `close`) with script-specific extras
- `_check_volume()` reads `VOL_MIN` at call time (not import time) so Streamlit param overrides work
