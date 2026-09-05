# AGENTS.md — Stock Screener Pro

> Read this FIRST before touching the repo. It is the agent-side working manual,
> not user-facing docs. Ground rules are derived from the actual source; where a
> rule is a product decision (not derivable from code) it is labelled as such.
> Keep it updated when structure, tooling, or a hard-won gotcha changes.

---

## 0. Mandatory Working Guidelines — Karpathy Rules (apply to EVERY task)

Every task on this project MUST follow the
[karpathy-guidelines](C:\Users\ediso\.codex\skills\karpathy-guidelines\SKILL.md).
Read that skill first; the four rules below are its distilled contract:

1. **Think before coding** — never guess, never hide confusion. State assumptions
   explicitly; if uncertain, ask. Name what is unclear before touching code.
2. **Simplicity first** — minimum code that solves the problem, nothing
   speculative. No features/abstractions/error-handling beyond what was asked.
   If it could be half the lines, rewrite it.
3. **Surgical changes** — touch only what you must. Don't "improve" adjacent
   code, comments, or formatting. Match existing style. Remove only orphans
   YOUR change created. Every changed line must trace to the user's request.
4. **Goal-driven execution** — define verifiable success criteria, then loop
   until verified (reproduce a bug with a test before fixing it; prove a refactor
   with tests before and after). "Make it work" is not a success criterion.

If a decision/step would violate these rules, stop and surface it explicitly.

---

## 1. Project Overview

**What it is:** Stock Screener Pro — a multi-market stock screening *terminal*
for Bursa Malaysia (primary) plus US and Shanghai A-shares. It is a **PyQt6
desktop app (primary product, packaged with PyInstaller + Inno Setup)** and a
**Streamlit web version** (`streamlit_app.py`). It is **not** an Electron app
(no `package.json`, no Node runtime; `licensing/license_manager.py`'s
`platform.node()` is machine-binding for activation, not Node.js).

**Primary purpose:** identify stocks that are *accumulating strength* —
Relative Strength, improving Price Action, Volume/Effort confirmation — that may
form a **breakout setup**. It is **not** "today's biggest gainers" (see §3).

**Target user:** a discretionary Bursa trader/researcher who wants a
TradingView-style, explainable shortlist. Every signal row carries a `reasons`
list explaining *why* it was selected.

**Architecture:** local, pure-function screening engine (causal, no lookahead) +
network data provider (Yahoo Finance, AkShare) + QThread background workers +
PyQt6 UI. No separate backend/server; offline Ed25519 activation.

**Core features (real, from source):**
- Markets: `markets/bursa.py` (`my`, `.KL`), `markets/us.py` (`us`, no suffix),
  `markets/shanghai.py` (`sh`, `.SS`, `data_provider="akshare"`).
- Screeners (**8**: EMA Compression Daily/Hourly/Weekly, KDJ Divergence,
  Weekly/Daily KDJ Golden Cross, 11-factor Scoring, and **Phase-1 "Ignition"** —
  RS + sector + setup + CLV + breakout + R:R). The additional **Top Movers** and
  **New Picks** tabs are boards, not screeners (per `ui/results_panel.py`).
- Chart drill-down (pyqtgraph candlestick + EMA + volume + KDJ, Daily/Weekly).
- Weekly KDJ golden-cross tray alerts, "New Picks" first-time board, Top Movers.
- Live search, sector filter, CSV export, cancel/retry, single-instance lock,
  language switch (en/ms/zh), offline signed-key activation.

---

## 2. Development Principles

**DO**
- Understand the existing architecture/data flow before editing (read the source;
  `AGENTS.md` is the index, but verify against code — never guess).
- Keep existing features; extend rather than replace.
- Fix root cause; make small, verifiable edits.
- Keep screener calculations **deterministic** and **causal** (no lookahead).
- Reuse existing utilities/services (`utils.resource_path/cache_dir`,
  `screener._calc_kdj`, `indicators.gm_kdj`, `screener_rs`, `screener_setup`).
- Be extra cautious in performance-sensitive code (download, per-stock loops).
- After touching core logic: run `pytest`, import chain, then check affected UI.

**DON'T**
- Don't rewrite a whole module without a stated reason and user approval.
- Don't add dependencies without need (see `requirements.txt` — it is pinned
  for a reason, e.g. `PyQt6>=6.7,<6.8`).
- Don't delete existing features.
- Don't hide real problems with mock/stubbed data.
- Don't hard-code stock results.
- Don't change `run_scoring_screener` behavior — it is test-locked.
- Don't make a build pass by weakening correctness or dropping data.
- Don't silently swallow errors (the codebase has some `try/except: pass`; fix
  them to at least log, and never let a real failure vanish).

---

## 3. Stock Screener Philosophy

This is the most important section. **The goal is not "find the stock that rose
the most today."** It is to find stocks that are **building the conditions for a
move**: Relative Strength vs market/sector, improving Price Action, and
Volume/Effort **confirming** the move — the kind that precede a **breakout
setup**.

Concrete axes used (all real, in `screener_phase1.run_phase1_screener`):
- **Price** — trend, consolidation/base (`base_quality`), breakout
  (`breakout_quality`), pullback/reclaim (`ema_pullback_reclaim`), support
  (`nearest_support`) & resistance (`nearest_pivot`, `next_resistance`),
  price strength (`closing_strength`/CLV, `price_extension`).
- **Volume** — expansion/contraction/MA in `run_scoring_screener` (vol MA20>MA60,
  spike, MA threshold) and `screener_setup` (vol dry-up, vol ratio).
- **Price Effort** — `effort_vs_result()` (`vol_ratio`/`price_move`/`upper_wick`
  → `accumulation` / `potential_supply` / `high_vol_ambiguous`). **Volume big does
  not mean good:** high volume with no price progress + long upper wick is
  `potential_supply` (distribution-ish), not a buy.
- **Relative Strength** — stock vs market (`stock_rs`), stock vs own sector
  (`stock_vs_sector_rs`), cross-sectional rank (`rs_rank`, `rs_rank_chg20/60`),
  sector strength (`sector_rank`).
- **Classification** — `classify()` maps the sub-scores to 12 setup labels (§7).

> Rule: do not simplify "strength" to a single metric. A valid setup requires
> Price + Volume + Effort + RS to agree; the score decomposes these explicitly.

---

## 4. Relative Strength

**RS ≠ RSI.** RS is *relative performance vs a benchmark* (FBMKLCI `^KLSE` for
`my`, `^GSPC` for `us`) and vs the stock's own sector. Implementation:
`screener_rs.py`:
- `stock_rs(close, bench, lookbacks=(5,20,60,120))`: `rs_Nd = stock %ret − bench
  %ret` on **aligned** dates (`_aligned`), NaN gaps dropped, returns from last-two
  valid prices (`_pct_change`) so suspensions never poison a number.
- Cross-sectional rank (`rs_rank_history` → `_rank_snapshot`): percentile (0-100)
  of RS20 across the whole universe at the same date; `rs_rank`, `rs_rank_m20/40/60`,
  `rs_rank_chg20/60`. **Penny guard:** price < RM0.20 excluded from rank; a single
  tick ≥ half the return with <2% move excluded (`_tick_size`).
- `stock_vs_sector_rs`: stock − equal-weight sector avg. `sector_rank`: sector
  strength = `rel_score_20d*0.6 + rel_score_60d*0.4` (momentum carried separately).
- `rs_momentum_batch` / `compute_rs_momentum`: now-vs-`window`-ago 5d RS.
- **Rule:** RS is the *leadership axis*. `classify()` derives
  LEADER/EMERGING LEADER/WEAKENING from `rs_rank`/`rs_rank_chg20` alone.
- **Do not change the RS definition** unless it is confirmed a bug; if you think
  RS is wrong, report it first, never silently redefine.

---

## 5. CLV (Close Location Value)

**CLV ≠ "higher close = stronger".** Implemented in `screener_setup.py`:
- `closing_strength(high, low, close)` = `(close − low) / (high − low)`, clamped
  0..1; **returns `None` when the day has no range (high == low)** or the last
  bar is non-finite — never a false strength.
- `meaningful_range(high, low, close, n=20, offset=0)` = `range / ATR20`
  (`_wild_atr`, Wilder, causal). Threshold `MEANINGFUL_RANGE_ATR = 0.8`.
- **The anti-mislabel fix:** in Phase-1, `clv >= 0.8` only gets the big
  `trigger_score +30` when `meaningful` is True; if CLV is high but the day
  barely moved (range/ATR < 0.8) it gets only **+10** ("High close, low
  significance") so a low-volatility micro-tick can't earn a big score.
- `yesterday_clv` (last completed day — used in **intraday** mode where today's
  close is unfinished and unreliable), `intraday_position` (info), `clv_series`
  (backtests). Filtering: `clv_min` (default 0.8) hard-filters in **EOD** mode
  only; skipped intraday.
- **If you suspect CLV mislabels:** mark as a potential issue and report — do not
  rewrite the CLV definition, and never remove the meaningful-range gate.

---

## 6. Price Action

Detected in `screener_setup.py`, all **causal** (only bars up to current):
- **Breakout:** `breakout_quality()` (score vs nearest pivot: close-through 40%,
  volume 20%, CLV 15%, RS 15%, no-failed-breakout 10%).
- **Failed breakout:** `failed_breakout()` (traded above pivot on volume, closed
  back below) → subtracts from `trigger_score`.
- **Pullback/reclaim:** `ema_pullback_reclaim()` (EMA60 rising + run-up + pullback
  within ±4% of EMA60 + volume dry-up + fresh reclaim ≤5 bars + upper-half close).
- **Accumulation/distribution:** `base_quality()` (range %, higher-low, vol
  dry-up, ATR slope), `shakeout_check()` / `failed_breakdown()` (support undercut
  with volume then reclaimed + close in upper half).
- **Support/resistance/compression:** `nearest_support()`, `nearest_pivot()`,
  `next_resistance()` (measured-move target, not the pivot itself), `detect_pivots()`
  (5-bar-each-side swing highs/lows).
- **Rule:** Price Action must be judged **together** with Price + Volume + Effort +
  RS — never from a single indicator. `run_phase1_screener` combines them into
  `strength/setup/trigger/breakout` sub-scores.

---

## 7. Setup Classification

**Use the real labels from `screener_phase1.classify()`** — the 12 labels, in
priority order:

```
BREAKOUT > EXPANSION > EMA RECLAIM > TRIGGER WATCH > SETUP
  > STRONG BUT EXTENDED > LEADER > EMERGING LEADER > WEAKENING > BASE > LAGGARD
```

- `breakout.attempt & score >= 75` → BREAKOUT; `>= 60` → EXPANSION.
- `ema_reclaim.detected & strength >= 40` → EMA RECLAIM (just under a real breakout).
- `trigger >= 80 & setup >= 50 & pivot_distance <= 5%` → TRIGGER WATCH, but R:R<1.0
  downgrades to SETUP.
- Leader axis: `rs_rank_chg20 <= -10` → WEAKENING; `rs_rank >= 80 & confirmed
  holding` → LEADER; rank in [55,85) & climbing → EMERGING LEADER. **A rank
  without a chg20 is NOT read as holding** (this was the INARI data-gap bug — now
  fixed in the working tree; LEADER requires non-None chg20).
- Structure fallbacks: `strength>=80` → LEADER; `extension>=15% & strength>=70` →
  STRONG BUT EXTENDED; `setup>=60 & ...` → SETUP; `strength>=45` → BASE; `setup>=45`
  → SETUP; `strength>=30` → WEAKENING; else LAGGARD.
- **Not implemented (per source):** ADX/DMI, and a user "Watchlist"/saved-list
  feature. A stock that fails screeners is simply absent from results — there is
  no Weak/Avoid tier (the "Ignition" tab only lists what passes).
- **Before changing classification:** explain (1) original logic, (2) new logic,
  (3) why, (4) effect on false positives/negatives.

---

## 8. Performance Rules

Target scale: **1000+ Bursa** (~1009 in `tickers.csv`), 2500 US, ~1700 A-shares.
- Never do heavy computation on the UI/main thread — download/screeners/meta run
  in `workers/*` QThreads (their `*Worker` classes).
- Avoid repeated indicator computation: the 11-factor scorer is called **once per
  universe** in `run_phase1_screener`; RS/rank/sector tables are batched once.
  Still, `detect_pivots` is recomputed per stock per axis (nearest_pivot/support/
  next_resistance) — a known CPU cost, in a background thread.
- Avoid duplicate API requests: day-cache (`cache/{market}_{date}.pkl`) + Web
  `@st.cache_data(ttl=3600)` + meta cache (`meta_cache.pkl`). But per the product
  decision (**Option A**), the desktop app still downloads daily+hourly+weekly for
  every run and **auto-refresh forces a full re-download every 5 min**
  (`main_window._on_refresh` → `force_refresh=True`). That is the accepted
  freshness-vs-cost trade-off; do not silently switch it to daily-only unless
  asked (it would break the Hourly/Weekly tabs).
- Search: desktop uses a **precomputed per-row lowercase text key**
  (`ui/table_model._build_search_keys`) so `SortFilterProxy.filterAcceptsRow` is
  one substring test per row (~1.2ms/keystroke, was ~280ms). Web uses AgGrid's
  client-side column filter. Do not regress to an all-cells scan.
- Charts: pyqtgraph; crosshair uses `np.searchsorted` (O(log n)); weekly tab is
  lazy; background runs / auto-refresh are **paused while a chart is open**
  (`_open_chart` stops the timer + defers `_finalize_results`).
- Before optimizing: find the real bottleneck (profile). Do not fake a speedup by
  asking for fewer tickers or dropping data.

---

## 9. Data Integrity

Financial data — treat it carefully:
- Do not mutate real market data (no rewriting OHLCV).
- Do not silently forward-fill; do not propagate NaN blindly. Data holes
  (suspensions, missing prints) are handled by `_aligned`/`_pct_change`
  (last-two-valid-prices) and `close.dropna()` — preserve that intent.
- Don't confuse trading date / session: `market_session.py` distinguishes
  **EOD** (completed day; CLV/volume final, `clv_min` applies) from **intraday**
  (unfinished; use `yesterday_clv`, no CLV hard-filter, volume verdict neutralized).
- Yahoo returns recent bars with `timestamp` but `null` OHLC (e.g. a day whose
  `close` is `None`). The code drops any bar without full OHLCV via the OHLCV
  index intersection — this is intentional (no invented prices). Do not fabricate
  a close; note when data lags (e.g. "as of 08-28; Yahoo hasn't posted 9-1 close").
- Use the correct timeframe per indicator; derive weekly from daily only in the
  `daily_only` A-share path (which skips the 1w/1h network calls and resamples).

---

## 10. Financial Logic Safety

- Never present results as a guarantee of gains or a deterministic prediction.
- "Setup" is a **watch/analysis label, not a buy signal**. Keep the disclaimer
  ("Data is for reference only — not investment advice") and any risk text.
- Keep calculations **transparent/explainable** (every Phase-1 row has `reasons`);
  don't hide the basis for a label. Do not delete risk annotations.

---

## 11. Coding Rules

- **Language/runtime:** Python 3.12 target (`pyproject` `requires-python >=3.10`,
  `ruff.target-version = py312`); PyQt6 pinned `<6.8` (see §Env). PowerShell shell.
- **Naming:** snake_case functions/modules; `_`-prefixed private helpers; constants
  UPPER_SNAKE. UI column display names are Title Case (`Code`, `Setup Type`).
- **Components:** PyQt6 widgets in `ui/` (each file = one concern); QThread workers
  in `workers/` with `progress/finished/error/cancelled` signals convention.
- **Services:** pure engine functions in `screener*.py` / `indicators/` (no network,
  no side effects, causal); network/data in `screener.py` + `workers/*`; market
  config in `markets/base.py` (dataclass + registry).
- **State management:** desktop = `QSettings("StockScreenerPro", ...)` for
  persistence (language, window geometry, alert toggle) + in-memory
  `self._meta_cache`/`_result_dfs`; file caches in `utils.cache_dir()` (pickle for
  data/meta, JSON for alert/new-picks state); web = `st.session_state` +
  `@st.cache_data`.
- **Error handling:** validate inputs → return `None`/empty rather than crashing
  (see the engine's "never raises" convention). Don't swallow errors silently —
  use `logger.warning/exception`. `DownloadCancelled` is a control-flow exception.
- **Async/threading:** `QThread` + signals; cooperative cancellation via a
  `threading.Event` / `requestInterruption()` checked between steps.
- **Typing:** type hints used across the engine (`float | None`, `dict[str, Any]`).
- **Testing:** pytest in `tests/` (offline, deterministic; `conftest.py` adds root
  to `sys.path`). Core engine tests are pure-function (no network). See §Tests.
- **Logging:** `logging` to `cache/app.log` + console (`main._setup_logging`).
- **File organization:** engine (`screener*.py`), indicators (`indicators/`),
  markets (`markets/`), workers (`workers/`), UI (`ui/`), tools (`tools/`),
  tests (`tests/`), licensing (`licensing/`, `seller_tools/`).

---

## 12. Change Management

Before changing core logic:
1. Find the relevant implementation (grep; use `rg`).
2. Understand the data flow (read the function + its callers/tests).
3. Find dependencies (what calls it, what it calls, what tests lock it).
4. Make the minimal change.
5. Run `pytest` (and, if relevant, the import chain / `ruff`).
6. Check the affected feature in the UI (or reproduce with a cached snapshot).
7. Report: what changed, why, files affected, tests run, remaining risks.

---

## 13. Git Rules

Protect the user's existing work. Do **not**:
- `git reset --hard`, `git checkout --`, force-push, or overwrite user changes —
  unless the user explicitly asked.
- Delete uncommitted changes. There may be in-development local work; preserve it.
- Work destructively over broad paths (`$HOME`, repo root) when deleting.
- Push to `origin/main` without the user's go-ahead (it is a published repo).

---

## 14. Debugging Rules

Follow **Reproduce → Trace → Identify Root Cause → Fix → Verify**. Do not patch a
symptom. If you cannot determine the root cause, state plainly what is uncertain —
**never guess/hand-wave**. (Example from this repo: "data stuck at 08-28" was traced
to Yahoo returning `close: null` for the last bar, not a rate-limit or a code bug.)

---

## 15. AI Agent Behavior

On any task: (1) understand the problem → (2) search the relevant code → (3)
confirm architecture & data flow → (4) propose a change plan → (5) implement the
minimal change → (6) verify → (7) summarize (Changed / Why / Files affected / Tests
/ Remaining risks). For large changes, present a plan to the user first; do not
launch a large refactor unilaterally.

---

## 16. Project-Specific Priorities

1. **Correctness**
2. **Financial calculation integrity**
3. **Screener signal quality**
4. **Performance**
5. **Maintainability**
6. **UI polish**

Never sacrifice screener correctness for UI aesthetics. (Examples: CLV is gated by
`meaningful_range` to avoid mislabeling; the penny-stock guards prevent a RM0.05
tick from ranking above a RM5 name.)

---

## 17. Documentation

When behavior is uncertain, **read the source and existing docs first** — do not
invent new behavior. Keep `AGENTS.md` current when structure/tooling/gotchas change.

---

## Environment / Toolchain (hard-won — do not "fix" these)

- Local Python 3.12 path on the seller's machine:
  `C:\Users\ediso\AppData\Local\Programs\Python\Python312\python.exe`.
- **PyQt6 MUST stay `>=6.7,<6.8` (6.7.1).** PyInstaller 6.22 cannot freeze
  PyQt6 6.8+/6.11 — the exe crashes at launch with
  `DLL load failed while importing QtCore: The specified procedure could not be found`.
- Inno Setup: `C:\Users\ediso\AppData\Local\Programs\Inno Setup 6\ISCC.exe`
  (`installer.iss` at repo root). `gh` and `vercel` CLIs signed in as `naiping87`.
- Shell = PowerShell (`head`/`test` unavailable; use `Get-Content`,
  `Test-Path`, `Select-Object -First`). Build: `py -m PyInstaller --noconfirm
  StockScreenerPro.spec` (repo root).

## Build / Release SOP (follow every release)

1. `git add <files> && git commit`, then `git push origin main`.
2. `py -m PyInstaller --noconfirm StockScreenerPro.spec` → `dist/StockScreenerPro.exe`.
3. Launch `dist\StockScreenerPro.exe`; confirm the main-window title is exactly
   "Stock Screener Pro" and the process `Responding=True`. If empty/exit → bundle
   is broken; do NOT build the installer.
4. `"...\Inno Setup 6\ISCC.exe" installer.iss` → `installer/StockScreenerPro_Setup.exe`.
5. `gh release create vX.Y.Z ...` (or `gh release upload <ver> ... --clobber`) with
   the exe + installer.
6. Verify digest: `gh release view <ver> --json assets --jq '.assets[].digest'` vs
   local `(Get-FileHash <file> -Algorithm SHA256).Hash`.
7. If the landing page changed: the site is a **non-git** folder
   `C:\Users\ediso\OneDrive\Documents\harness\vercel-license-generator`; bump the
   version there and `cd ..\harness\vercel-license-generator && vercel --prod --yes`.
8. Sanity: `python tools/verify_release.py --version vX.Y.Z` (exits 0 only when the
   page link, GitHub asset, and local installer all agree).

Bump `AppVersion` in `installer.iss` (and `version` in `pyproject.toml` if relevant)
before release.

### Release gotchas (learned the hard way — check every release)

- **Auto-update is intentionally DEFERRED.** User asked for in-app "check for
  update / auto-update" (2026-09-06) and decided NOT to build it yet; revisit
  only when the product is stable. If you do it later, the prerequisites are:
  (a) version string is now centralized in `version.APP_VERSION` (splash and
  About both read it — fixed in 7e7aaf4, do NOT hard-code it again); (b) add a
  GitHub Releases API check; (c) prefer "notify + open download page" over
  silent self-replace (a running PyInstaller onefile exe cannot overwrite
  itself).
- **STARTUP HANG (2026-09-06, ROOT-CAUSED + FIXED in `30fb8c1`):** app reached
  splash then the main thread HUNG (Responding=False, CPU frozen ~1.3). Root
  cause was the earlier sort fix `b6cb6fa`: it called `sourceModel()` /
  `headerData()` / `_df_ref()` INSIDE `SortFilterProxy.lessThan`.
  `QSortFilterProxyModel.setSourceModel()` re-applies sort+filter during
  `MainWindow.__init__` (via `_refresh_new_picks` → New-Picks table), and
  calling model/header methods from lessThan at that moment DEADLOCKED the main
  thread. Manual `proxy.sort()` tests passed (source already attached), which
  hid it; the hang only fired on the FIRST setSourceModel with 171 rows.
  RULE: **lessThan must stay pure (compare left/right UserRole only).** Put
  sort keys in `PandasModel.data(UserRole)` instead (Liq → ADTV60 value,
  Setup Type → business-order rank). Verified live: MainWindow constructs,
  PrintWindow shows a real rendered UI, asc/desc correct, pytest 62/62.
- **CURRENT RELEASE = v1.2.10** (tag + GitHub assets + landing pages all bumped;
  verified by `tools/verify_release.py --version v1.2.10`, exit 0). It contains
  the "EMA60 rising only" hard filter (v1.2.10), the Structure/Trend separation
  (v1.2.9), the startup-hang fix, UserRole-based Liq/Setup-Type sorting, version
  centralization (`version.APP_VERSION`), and the chart cleanup. To release
  again: bump version.py + installer.iss + pyproject.toml together, push, then
  follow the Build/Release SOP.
- **`tools/bump_landing_version.py` is hard-coded OLD/NEW** (e.g. `v1.2.5 -> v1.2.6`).
  It is NOT generic — after a version jump this makes it wrong. Run a one-off
  replace script instead (see below), then delete it or update OLD/NEW.
- **Three landing pages must be bumped, not two**: `index.html`, `download.html`
  AND `ssp-landing.html`. They drift (ssp was on v1.2.2 while index/download
  were v1.2.3). `tools/verify_release.py` only checks index + download, so
  **stale ssp-landing.html silently ships an old link**.
- All three pages carry version tokens in plain HTML AND inside the inline
  `#i18n-data` JSON (en/bm/zh). A naive `vX` string replace is fine because the
  token is always exactly `v1.2.X`; count occurrences and assert zero old ones
  after. This also updates the CTA button text (e.g. `(v1.2.X)`).
- `installer.iss` `AppVersion` and `pyproject.toml` `version` must match the
  release tag. v1.2.6 was released by another machine at 09-03; if you build a
  NEWer code change you MUST bump a new version instead of re-loading v1.2.6.
- `verify_release.py --version vX.Y.Z` compares web links, the remote GitHub
  asset *size*, and the local installer *size*. All three must equal the bytes
  you just built (133,926,880 B for the v1.2.7 setup).
- Quick web size sanity (no screenshot tool needed):
  `python -c "import urllib.request; t=urllib.request.urlopen('https://vercel-license-generator-zeta.vercel.app/').read().decode(); print('releases/download/v1.2.7/StockScreenerPro_Setup.exe' in t)"`.

## Repo Layout (agent index)

Core engine (pure, causal, no network):
- `screener_setup.py` — pre-breakout structure detectors: `closing_strength`,
  `yesterday_clv`, `intraday_position`, `_wild_atr`, `meaningful_range`,
  `effort_vs_result`, `base_quality`, `shakeout_check`, `breakout_quality`,
  `ema_pullback_reclaim`, `failed_breakdown`, `failed_breakout`,
  `nearest_pivot`, `nearest_support`, `next_resistance`, `risk_reward`,
  `price_extension`, `detect_pivots`.
- `screener_rs.py` — RS + sector: `stock_rs`, `stock_rs_batch`,
  `rs_rank_history`, `rs_momentum_batch`, `stock_vs_sector_rs`, `sector_rank`,
  `sector_performances`, `apply_sector_override`, penny/tick guards.
- `screener_phase1.py` — `run_phase1_screener`, `classify`, `set_lang`;
  weights `W_STRENGTH=0.30, W_SETUP=0.25, W_TRIGGER=0.25, W_BREAKOUT=0.20`;
  `master_rr = master * rr_mult`.
- `screener.py` — legacy/market engine: `load_tickers`, `_build_session`,
  `_fetch_chart`, `_fetch_ticker`, `download_data`, `_download_yahoo`
  (supports `daily_only`), `_download_akshare`, the 5 legacy screeners,
  `run_scoring_screener` (11-factor, **test-locked**), `run_*_kdj_screener`,
  `backtest_scoring`.
- `indicators/gm_kdj.py` — Pine-parity KDJ (`gm_kdj`, `kdj_cross`,
  `kdj_divergence`, `kdj_state`); `screener._calc_kdj` delegates here.
- `market_regime.py` (RISK_ON/NEUTRAL/RISK_OFF), `market_session.py` (eod/intraday).

UI (PyQt6): `ui/main_window.py` (orchestration, chart-open pause, benchmark,
top movers), `ui/sidebar.py`, `ui/results_panel.py` (tabs: Top Movers, Daily/Hourly/
Weekly EMA, KDJ Div, Weekly/Daily KDJ, Scoring, **Ignition**, New Picks),
`ui/table_model.py` (precomputed text-key search, `COLUMN_HELP`), `ui/table_view.py`
(`SortFilterProxy`), `ui/chart_view.py` (pyqtgraph + `np.searchsorted` crosshair,
pivot/CLV annotations), `ui/styles.py`, `ui/splash_screen.py`, `ui/welcome.py`,
`ui/system_tray.py`, `ui/activation.py`.

Workers (`workers/`): `download_worker.py` (day-cache pickle), `screener_worker.py`
(8 screeners + Phase-1 column renaming + signal journal), `meta_worker.py`
(ROE/sector + `meta_cache.pkl`), `alert_worker.py` (weekly KDJ tray alerts).

Others: `markets/` (base/bursa/us/shanghai), `i18n.py` (en/ms/zh),
`licensing/license_manager.py` (Ed25519 offline activation), `seller_tools/`,
`utils.py` (`cache_dir`, `resource_path`), `tools/` (backtests, e2e/golden/smoke/
verify scripts, `signal_journal.py`, `new_stock_monitor.py`), `tests/`.

## Cached market data (test without network)

- `cache/{market}_{YYYY-MM-DD}.pkl` → pickle `(instr, meta)`:
  - `instr` = `{ticker: {close, high, low, volume, name, close_hourly, ...,
    close_weekly, ...}}`.
  - `meta` = `{ticker: company_name}`.
- `cache/meta_cache.pkl` → `{ticker: {roe, sector, industry}}` (persisted by
  `workers/meta_worker`).
- `cache/alerts_state.json` (weekly-KDJ notified set), `cache/picks_state.json` /
  `cache/picks_board.json` (New Picks board).
- Ticker lists: `tickers.csv` (no `.KL` suffix; loader appends it),
  `tickers/us.csv`, `tickers/shanghai_1700.csv`; sector override:
  `tickers/sector_map.csv` (`CODE,SECTOR`).

## Known gotchas / past fixes (do not reintroduce)

- **CLV mislabel:** gated by `meaningful_range` (range/ATR20 ≥ 0.8). Real strength
  +30, high-close-but-tiny +10. Do not remove the gate.
- **Structure vs Trend are SEPARATE axes (user-approved, do not regress):**
  a stock can be `SETUP` (structure forming) while `trend_status` says
  `below_ema200_weak` (e.g. Sunway 4.96 vs EMA200 5.255). `classify()` /
  `setup_score` / trigger / breakout / RS are UNCHANGED — trend is REPORTED
  only (row fields `ema200_dist_pct`, `ema200_slope`, `trend_status`). The
  naive "price < EMA200 ⇒ not SETUP" gate was explicitly REJECTED. `weak =
  price below EMA200 AND EMA200 slope <= 0`; below + rising = healthy pullback.
  `trend_position()` in screener_setup reuses `_ema_slope`, returns None when
  <200 bars so new listings are never judged.
- **Search lag:** was `setFilterFixedString` over all columns (~280ms/keystroke);
  fixed with per-row lowercase text-key precompute (~1.2ms).
- **Chart stutter:** fixed by pausing auto-refresh + deferring `_finalize_results`
  while a modal chart is open.
- **Ignition classification:** penny/tick-guarded stocks with no `rs_rank` must not
  collapse to WEAKENING; set-up triggers stay SETUP when rank is missing.
- **Top N is a ceiling, not a guarantee**: `Min Closing Strength` (default 0.8)
  filters first, so a 300 request can return ~200; Ignition shows a yellow hint.
- **INARI `rs_rank_chg20=None`→LEADER bug:** fixed in the working tree —
  `classify()` now requires a non-None chg20 for LEADER. If you see code re-adding
  `ors_rank_chg20 is None` in the LEADER condition, that is the regression.

## Tests / sanity

- `py -m pytest -q` (currently **53 passing**, incl. `tests/test_phase1.py` which
  locks `classify`, `closing_strength`, `meaningful_range`, `effort_vs_result`,
  `price_extension`, `risk_reward`).
- Import chain: `python -c "import i18n,pyqtgraph,ui.chart_view,ui.main_window,workers.meta_worker; print('OK')"`.
- Engine smoke: `python tools/smoke_phase1.py` (needs network).
- Reproduce CLV/meaningful-range on a real snapshot: load `cache/my_<date>.pkl`,
  feed `run_phase1_screener` with the `^KLSE` benchmark.
- CI: `.github/workflows/ci.yml` runs pytest + import chain on push/PR (Python 3.12,
  PyQt6<6.8, `QT_QPA_PLATFORM=offscreen`).

## Known gaps / caveats (from source, not fixes)

- **ADX / DMI: not implemented.**
- **User Watchlist / saved-list: not implemented** (the only "portfolio" refs are
  backtest NAV, not a product feature).
- **Desktop engine** is PyQt6 (not Electron); the web version is Streamlit.
- `main_window._get_benchmark` handles `my`/`us`/`cn` symbols (`^KLSE`/`^GSPC`/
  `000001.SS`), but the A-share market code is registered as **`sh`**, so the
  desktop benchmark returns `None` for Shanghai (RS degrades to None there).
- **Download behavior (Option A, product decision):** full daily+hourly+weekly per
  run + 5-min forced re-download on auto-refresh. Do not silently change this.
  Episodic "data looks stale" is usually Yahoo returning `close:null` for the latest
  bar (see Data Integrity), not a code bug.
