# AGENTS.md — Stock Screener Pro (working manual for the coding agent)

> Read this FIRST before touching the repo. It is the agent-side index so the
> workspace context is recoverable in seconds instead of re-grepping the tree.
> This file is NOT user-facing docs; it is a work manual. Keep it updated when
> structure, tooling, or a hard-won gotcha changes.

## Project & owner

- Git repo, owner: **naiping87** (GitHub + Vercel). Canonical repo:
  `https://github.com/naiping87/stock-screener`.
- Product: **Stock Screener Pro** — PyQt6 desktop app (primary) + a
  Streamlit web version (`streamlit_app.py`).
- User preferences (respect strictly):
  - Audit first / get evidence — **never guess**. Find root cause before editing.
  - **Minimal changes only.** Do not rewrite screening / scoring / indicators /
    UI design / DB structure.
  - After a fix: **push + rebuild exe + rebuild installer + update GitHub
    Release + (when web changed) deploy Vercel**.
  - Explain *why* in the reply.
  - Non-technical UI preferred for the user-facing answer.

## Env / toolchain (hard-won — do not "fix" these)

- Local Python: `C:\Users\ediso\AppData\Local\Programs\Python\Python312\python.exe`.
- **PyQt6 MUST stay `>=6.7,<6.8` (currently 6.7.1).** PyInstaller 6.22 cannot
  freeze PyQt6 6.8+/6.11 → exe crashes on launch with
  `DLL load failed while importing QtCore: The specified procedure could not be found`.
- Inno Setup compiler: `C:\Users\ediso\AppData\Local\Programs\Inno Setup 6\ISCC.exe`
  (script at repo root: `installer.iss`).
- `gh` CLI signed in as `naiping87`. `vercel` CLI signed in as `naiping87`.
- Shell is PowerShell. `head`/`test` are NOT available; use `Get-Content`,
  `Test-Path`, `Select-Object -First`.
- `py -m PyInstaller` from the repo root. Clean build first only when necessary.

## Build / release SOP (use every time)

1. `git add <files> && git commit` then `git push origin main`.
2. Build exe: `py -m PyInstaller --noconfirm StockScreenerPro.spec` (repo root).
3. **Launch `dist\StockScreenerPro.exe`** and confirm the main-window title is
   exactly **"Stock Screener Pro"** and the process `Responding=True`. If the
   title is empty / it exits, the bundle is broken — do NOT build the installer.
4. Build installer: `"C:\...\Inno Setup 6\ISCC.exe" installer.iss`
   (output: `installer\StockScreenerPro_Setup.exe`).
5. Upload: `gh release upload <version> "dist\StockScreenerPro.exe" "installer\StockScreenerPro_Setup.exe" --clobber`.
6. Verify digest matches:
   `gh release view <version> --json assets --jq '.assets[].digest'` vs local
   `(Get-FileHash <file> -Algorithm SHA256).Hash`.
7. Web (only if the landing page changed): the site is a **non-git** folder
   `C:\Users\ediso\OneDrive\Documents\harness\vercel-license-generator`;
   deploy with `cd ..\harness\vercel-license-generator && vercel --prod --yes`.

Current release tag/digests live in the reference snippet below; bump `AppVersion`
in `installer.iss` (and `version` in `pyproject.toml` if relevant) before release.

## Repo layout (agent index — key files)

Core engine (pure functions, causal, no network):
- `screener_setup.py` — PRE-BREAKOUT structure detectors. **Everything here is
  causal** (reads only bars up to current). Key fns:
  - `closing_strength()` (CLV, returns None on zero-range day),
    `yesterday_clv()`, `intraday_position()`.
  - `_wild_atr()` (causal Wilder ATR) + `meaningful_range()` (range/ATR20, the
    "did the day actually move" gate). Threshold `MEANINGFUL_RANGE_ATR = 0.8`.
  - `effort_vs_result()` → `vol_ratio / price_move / upper_wick / verdict`
    (`accumulation` / `potential_supply` / `high_vol_ambiguous`).
  - `base_quality()`, `shakeout_check()`, `breakout_quality()`,
    `failed_breakdown()`, `failed_breakout()`, `ema_pullback_reclaim()`,
    `nearest_pivot()`, `nearest_support()`, `next_resistance()`,
    `risk_reward()`, `price_extension()`.
- `screener_rs.py` — RS + sector engine. `stock_rs_batch`, `rs_rank_history`
  (cross-sectional rank: `rs_rank`, `rs_rank_chg20/60`), `sector_rank`,
  `stock_vs_sector_rs` (stock vs OWN sector), RS momentum, `apply_sector_override`.
- `screener_phase1.py` — the **Phase-1 pulse detector** built on top of the
  existing 11-factor scorer. Produces the "Ignition" tab. Key fns:
  - `classify()` → one of the setup labels, priority order: BREAKOUT >
    EXPANSION > EMA RECLAIM > TRIGGER WATCH > SETUP > STRONG BUT EXTENDED >
    LEADER > EMERGING LEADER > WEAKENING > BASE > LAGGARD. **Leadership axis**
    (`rs_rank`/`rs_rank_chg20`) alone decides Leader/Emerging/Weakening.
  - `run_phase1_screener(...)` → returns rows with `strength_score`,
    `setup_score`, `trigger_score`, `breakout_score`, `master_score`,
    `master_rr`, `classification`, plus `clv`, `range_atr`, `meaningful_range`,
    RS/sector columns, `reasons`.
  - Weights: `W_STRENGTH=0.30, W_SETUP=0.25, W_TRIGGER=0.25, W_BREAKOUT=0.20`.
    `master_rr = master * rr_mult` (R:R <1.0 → ×0.6, <1.5 → ×0.9).
  - `set_lang("en"|"ms"|"zh")` changes the `reasons` language.
- `screener.py` — legacy/market engine: `load_tickers()`, `_build_session()`,
  `_fetch_chart()` (Yahoo), `run_scoring_screener()` (the 11-factor scorer —
  **do not change its behavior; tests depend on it**), benchmark `^KLSE`.

UI (PyQt6):
- `ui/main_window.py` — top-level window, wires screeners + chart open/close.
  Chart-open pauses auto-refresh and blocks background run/market switches;
  `_finalize_results` is deferred until the chart closes.
- `ui/chart_view.py` — pyqtgraph candlestick. Crosshair uses `np.searchsorted`
  (O(log n)); OHLCV labels rebuilt only on K-line change; weekly tab lazy.
- `ui/table_model.py` — `PandasModel` + `SortFilterProxy`. **Search uses a
  precomputed per-row lowercase key over TEXT columns only** (fixed ~280ms →
  ~1.2ms per keystroke). `COLUMN_HELP` maps column names → hover tooltips.
- `ui/table_view.py`, `ui/results_panel.py` — table + the tab container.
  `results_panel._tab_index` holds tab keys; `set_results(tab, df)` populates.
- `ui/sidebar.py`, `ui/welcome.py`, `ui/activation.py`, `ui/splash_screen.py`,
  `ui/system_tray.py`, `ui/styles.py`.

Workers:
- `workers/screener_worker.py` — runs `run_phase1_screener`, then **renames
  phase1 columns to friendly names** and reorders them: `Code, Name, Setup Type,
  Value(master_rr), Master(master_score), Strength, Setup, Trigger, Breakout,
  RS Rank(rs_rank), CLV, R:R(rr), Score(score), Sector, Price(close)` followed
  by remaining raw columns. Changing friendly naming here changes the UI table.
- `workers/meta_worker.py` (sector/name meta), `download_worker.py`,
  `alert_worker.py` (KDJ golden-cross tray alerts).

Others:
- `markets/` — `base.py` (`data_provider`), `bursa.py`, `us.py`, `shanghai.py`.
- `indicators/gm_kdj.py` — KDJ (daily/weekly). `market_regime.py` —
  RISK_ON/NEUTRAL/RISK_OFF. `market_session.py` — eod vs intraday.
- `licensing/license_manager.py` — Ed25519 offline activation.
- `i18n.py`, `utils.py` (cache_dir, resource_path), `conftest.py`.

## Cached market data (test without network)

- `cache\my_<YYYY-MM-DD>.pkl` — `pickle.load` → `(instr, meta)` tuple.
  - `instr` = `{ticker: {"close","high","low","volume","name", ...}}` (daily + hourly + weekly).
  - `meta` = `{ticker: company_name}`.
- As of a 2026-08-30 cache: ~959 Bursa tickers; INARI = `0166.KL`,
  KLK = `2445.KL`. Ticker list: `tickers.csv` (no `.KL` suffix in the file;
  suffix appended by loader). Sector map: `tickers/sector_map.csv`
  (`CODE,SECTOR`, applied by raw code).

## Known gotchas / past fixes (reference, do not reintroduce)

- **CLV alone mislabels**: a high CLV (~1.0) on a tiny-range bar looks strong
  but is not. Fixed by gating the strong-close `trigger_score` bonus behind
  `meaningful_range` (range/ATR20 >= 0.8). Low-significance bars get +10
  ("High close, low significance CLV=…"), real moves get +30.
- **Search lag**: `QSortFilterProxyModel.setFilterFixedString` over all columns
  was ~280ms/keystroke. Fixed with per-row lowercase text-key precompute.
- **Chart stutter**: auto-refresh / background run during an open chart caused
  repaints; fixed by pausing refresh + deferring `_finalize_results`.
- **Ignition classification**: penny / tick-guarded stocks that get no
  `rs_rank` should not collapse to WEAKENING; setup90/trig75 stay SETUP when
  rank is missing.
- **CLV cap hint**: Top N is a ceiling only; `Min Closing Strength` (default
  0.8) filters first, so 300 request can return ~200. The Ignition tab shows a
  yellow hint when this happens.
- **Known open question (NOT fixed)**: INARI `rs_rank_chg20 = None` (20d-ago
  rank is a data gap) is treated as "holding" in `classify()`, so a high
  `rs_rank` can silently pass as LEADER. Out of scope for CLV; flagged to user.

## Keys to the Ignition score (for the user-facing explanation)

- **`Value` = the ranking score** (`master_rr`, R:R-adjusted composite).
- **`Setup Type`** = one-line label (BREAKOUT/TRIGGER WATCH/SETUP/LEADER/…).
- **`RS Rank`** = cross-sectional RS percentile (0-100), the leadership axis.
- `Strength` (30%) + `Setup` (25%) + `Trigger` (25%) + `Breakout` (20%)
  decompose `Value`. `Why` lists per-stock reasons. `CLV` = today close
  location; `R:R` = risk/reward.
- Default reading rule: **sort by `Value`, judge by `Setup Type`**, drill into
  `Why`/components only to understand a pick.

## Tests / sanity

- Unit tests: `py -m pytest -q` (currently 36/36 green).
- Import chain check:
  `py -c "import i18n,pyqtgraph,ui.chart_view,ui.main_window; print('OK')"`.
- A quick engine smoke: `py tools/smoke_phase1.py`.
- To reproduce the CLV/meaningful-range behavior on a real snapshot, load
  `cache\my_<date>.pkl` and feed `run_phase1_screener` with the `^KLSE`
  benchmark (fetch via `_fetch_chart(sess, "^KLSE", ...)`).
