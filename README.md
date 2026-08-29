# Stock Screener Pro

Multi-market stock screening terminal — **PyQt6 desktop app** (primary product) + **Streamlit web version**.

TradingView-inspired dark theme with candlestick drill-down charts, weekly KDJ golden-cross alerts, and a weighted 11-factor scoring system.

## Features

| Feature | Description |
|---|---|
| Markets | 🇲🇾 Bursa Malaysia · 🇺🇸 NYSE/NASDAQ/AMEX · 🇨🇳 Shanghai A-Shares |
| Top Movers | 🔺 instant day board of top gainers / losers / actives when data loads |
| Screeners | EMA Compression (Daily / Hourly / Weekly) · KDJ Divergence · Weekly/Daily KDJ Cross · 11-factor Scoring |
| Charts | Double-click any result row → candlestick + EMA 20/50/100/200 + volume + KDJ (Daily/Weekly), zoom/pan/crosshair |
| Alerts | Weekly KDJ golden-cross detection after every run → system tray notifications (once per cross) |
| New Picks | 🆕 board that lists every stock passing the screeners for the FIRST time — checked after every 5-min refresh, per-market baseline, tray notification, no duplicates |
| UX | Dark theme, per-market defaults, live search, sector filter, CSV export, cancel/retry, single-instance lock |
| Web | Streamlit version with password gate, auto-refresh and the same screeners |

## Data sources

- **Yahoo Finance** (default): Bursa, US markets.
- **AkShare**: Shanghai A-Shares — now bundled in the desktop build, so the China feature works out of the box.

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

## RELEASE SOP — every time you publish an update (DO NOT SKIP)

Buyers download straight from the landing page, so the page version MUST match
the release asset. Run these steps in order after any code change you want
shipped:

1. **Bump version everywhere**: `installer.iss` AppVersion + `ui/splash_screen.py`
   (if it shows a version) + `ui/main_window.py` About dialog.
2. **Build**: `python -m PyInstaller --noconfirm StockScreenerPro.spec`
   → `dist/StockScreenerPro.exe`.
3. **Installer**: `ISCC.exe installer.iss` (path:
   `C:\Users\ediso\AppData\Local\Programs\Inno Setup 6\ISCC.exe`)
   → `installer/StockScreenerPro_Setup.exe`.
4. **Release**: `gh release create vX.Y.Z "installer\StockScreenerPro_Setup.exe" --title "..." --notes "..."` —
   or overwrite if the tag exists:
   `gh release upload vX.Y.Z "installer\StockScreenerPro_Setup.exe" --clobber`.
5. **Update the web pages**: replace the version in
   `../vercel-license-generator/index.html` + `download.html`
   (Python one-liner with UTF-8 — NEVER `Set-Content` in PowerShell, it shreds emoji):
   ```python
   t = open(p, encoding='utf-8').read()
   open(p, 'w', encoding='utf-8', newline='').write(t.replace('vX.Y.Z-old', 'vX.Y.Z'))
   ```
6. **Deploy**: `cd ../vercel-license-generator && vercel --prod --yes`.
7. **VERIFY (mandatory)**: `python tools/verify_release.py --version vX.Y.Z`
   — exits 0 only when the page link, the GitHub asset and the local installer
   all agree. A mismatch means customers would download an old build; fix and
   re-upload before telling anyone.
8. **Commit & push** both repos (`stock-screener` + `vercel-license-generator`).

The landing/download pages are static; if you forget step 5-7, the page keeps
pointing at an older tag. `verify_release.py` is the safety net — run it
every time.

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

## Licensing / activation

The desktop app is gated by an **offline signed-key activation** (no server needed). A valid activation code is required on first launch; without it the app won't start. After activation the license binds to the machine (configurable) and stays active (perpetual).

**How it works:** your private `Ed25519` key signs each buyer's activation code; the app verifies it with an embedded public key, so nothing can be forged by modifying the client.

Seller setup (do this yourself, keep the private key secret):
```bash
# 1) 生成密钥对(只跑一次)
pip install cryptography
python seller_tools/gen_keys.py        # 会打印 PUBLIC_KEY_B64，填到 licensing/license_manager.py

# 2) 每卖一单生成一个激活码
#    pre 模式(当前默认, 一码一机, 防共享):必须带买家机器码
python seller_tools/create_license.py --name "买家A" --order 12345 --machine "<买家激活框里的机器码>"
```

- `private.pem`（卖家私钥）已 `gitignore`，**严禁提交/外发**；丢失则无法再为老买家出码。
- `licensing/license_manager.py` 的 `BIND_MODE`：`pre`（当前默认，激活码绑定单机、一码一机、防转卖/共享）、`self`（首次激活自绑定本机、买家粘码即用，但同码可在另一台电脑再激活）、`none`（不绑机器）。
- 开发时可用 `SCREENER_SKIP_LICENSE=1` **仅**在非打包运行下跳过激活（打包版无效，避免当后门）。

## Roadmap status

- [x] P0 correctness (single instance, per-market defaults, A-share source)
- [x] P1 TradingView dark theme + number formatting + search + empty states
- [x] P2 robustness (busy guard, cancel, retry, logging)
- [x] P3 weekly KDJ alerts in-app
- [x] P4 chart drill-down
- [x] P5 tests / lint / README / first-run welcome
- [x] Code signing — **declined by decision** (unsigned exe shows a SmartScreen
      warning; end users must click "More info → Run anyway")
- [x] Licensing/activation — offline Ed25519 signed key, machine binding, perpetual
