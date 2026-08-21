# Stock Screener Pro

Multi-market stock screening terminal — **PyQt6 desktop app** (primary product) + **Streamlit web version**.

TradingView-inspired dark theme with candlestick drill-down charts, weekly KDJ golden-cross alerts, and a weighted 11-factor scoring system.

## Features

| Feature | Description |
|---|---|
| Markets | 🇲🇾 Bursa Malaysia · 🇺🇸 NYSE/NASDAQ/AMEX · 🇨🇳 Shanghai A-Shares |
| Screeners | EMA Compression (Daily / Hourly / Weekly) · KDJ Divergence · Weekly/Daily KDJ Cross · 11-factor Scoring |
| Charts | Double-click any result row → candlestick + EMA 20/50/100/200 + volume + KDJ (Daily/Weekly), zoom/pan/crosshair |
| Alerts | Weekly KDJ golden-cross detection after every run → system tray notifications (once per cross) |
| New Listings | 🆕 board that accumulates every stock appearing in the ticker list for the first time (per-market baseline, tray notification, no duplicates) |
| UX | Dark theme, per-market defaults, live search, sector filter, CSV export, cancel/retry, single-instance lock |
| Web | Streamlit version with password gate, auto-refresh and the same screeners |

## Data sources

- **Yahoo Finance** (default): Bursa, US markets.
- **AkShare**: Shanghai A-Shares (set `data_provider="akshare"` in `markets/shanghai.py`).

> Data is for reference only — not investment advice.

## Quick start (desktop)

```bash
pip install -r requirements.txt
python main.py            # or: pythonw main.py (no console window)
```

First launch shows a short welcome screen. Logs: `cache/app.log`.

## Quick start (web)

```bash
streamlit run streamlit_app.py
```

Set `APP_PASSWORD` via Streamlit secrets (default fallback: `demo123`).

## Tests & lint

```bash
pytest                       # unit tests (no network required)
ruff check .                 # lint (config in pyproject.toml)
```

## Build the installer

```bash
build.bat                    # PyInstaller onefile exe -> dist\StockScreenerPro.exe
# then open installer.iss in Inno Setup to produce the setup package
```

`StockScreenerPro.spec` is the canonical PyInstaller config (also git-tracked now).

## Project layout

```
main.py                  entry point (splash, single-instance lock, logging)
screener.py              data download (Yahoo/AkShare) + all screener logic
markets/                 market registry (base + bursa/us/shanghai)
workers/                 QThread workers: download, screeners, meta (ROE), alerts
ui/                      desktop UI: styles (TV dark theme), sidebar, results,
                         table model/view, chart drill-down, splash, tray
streamlit_app.py         web version
tickers/                 ticker lists per market
tools/make_icon.py       regenerates resources/icon.ico
tests/                   pytest unit tests
```

## Roadmap status

- [x] P0 correctness (single instance, per-market defaults, A-share source)
- [x] P1 TradingView dark theme + number formatting + search + empty states
- [x] P2 robustness (busy guard, cancel, retry, logging)
- [x] P3 weekly KDJ alerts in-app
- [x] P4 chart drill-down
- [x] P5 tests / lint / README / first-run welcome
- [x] Code signing — **declined by decision** (unsigned exe shows a SmartScreen
      warning; end users must click "More info → Run anyway")
- [ ] Licensing/activation (deferred by decision)
