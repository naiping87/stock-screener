"""
Bursa Malaysia Stock Screener — Streamlit Web App.
Access from any device: mobile, tablet, desktop.
"""
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
import streamlit as st

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screener import (
    load_tickers, download_data,
    run_sma_screener, run_sma_hourly_screener, run_divergence_screener,
    run_weekly_kdj_screener, run_scoring_screener, backtest_scoring,
    SMA_PERIODS, DIVERGENCE_THRESHOLD, MIN_COMPRESSION_BARS,
    KDJ_PERIOD, KDJ_SIGNAL, DIVERGENCE_LOOKBACK,
    VOL_MIN, VOL_MIN_HOURLY, WEEKLY_VOL_MIN,
    SCORE_TREND_PERIODS, SCORE_TREND_THRESHOLD, SCORE_SMA200_SLOPE_BARS,
    SCORE_VOL_PERIOD, SCORE_VOL_THRESHOLD, SCORE_VOL_MA_BARS, SCORE_VOL_MA_THRESHOLD,
    SCORE_TOP_N,
    TICKERS_FILE,
)

# ── Defaults for reset ─────────────────────────────────────────────────────
DEFAULTS = {
    "periods": "5,10,20,30,50",
    "div": DIVERGENCE_THRESHOLD,
    "bars": MIN_COMPRESSION_BARS,
    "vol_d": VOL_MIN,
    "vol_h": VOL_MIN_HOURLY,
    "vol_w": WEEKLY_VOL_MIN,
    "kdj_p": KDJ_PERIOD,
    "kdj_s": KDJ_SIGNAL,
    "div_lb": DIVERGENCE_LOOKBACK,
    "score_trend_periods": [20, 30, 60, 120],
    "score_trend_div": SCORE_TREND_THRESHOLD,
    "score_slope_bars": SCORE_SMA200_SLOPE_BARS,
    "score_vol_p": SCORE_VOL_PERIOD,
    "score_vol_t": SCORE_VOL_THRESHOLD,
    "score_vol_ma_b": SCORE_VOL_MA_BARS,
    "score_vol_ma_t": SCORE_VOL_MA_THRESHOLD,
    "score_top_n": SCORE_TOP_N,
}

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bursa Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Keep-alive ──────────────────────────────────────────────────────────────
# Prevent mobile browser from sleeping / WebSocket timeout during long downloads
st.markdown("""
<script>
(function(){
    var _active = false;
    var _interval = null;
    function _startPing() {
        if (_active) return;
        _active = true;
        _interval = setInterval(function(){
            fetch(window.location.origin + '/_stcore/health').catch(function(){});
        }, 20000);
    }
    function _stopPing() {
        _active = false;
        if (_interval) { clearInterval(_interval); _interval = null; }
    }
    // Start pinging when any button is clicked (download triggers)
    document.addEventListener('click', function(e){
        if (e.target && e.target.tagName === 'BUTTON') _startPing();
    });
    // Stop after 8 minutes (safety timeout)
    setTimeout(_stopPing, 480000);
})();
</script>
""", unsafe_allow_html=True)

# ── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Global dark theme ─────────────────────────────── */
    .stApp { background: #0d1117; }
    .main .block-container { padding-top: 1rem; }
    h1, h2, h3, h4, p, span, div, label { color: #c9d1d9; }

    /* ── Sidebar dark ──────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #0d1117; border-right: 1px solid #21262d;
    }
    [data-testid="stSidebar"] * {
        color: #c9d1d9 !important;
    }
    [data-testid="stSidebar"] .st-emotion-cache-1cypcdb,
    [data-testid="stSidebar"] .st-emotion-cache-6qob1r {
        background: #0d1117;
    }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] .st-bb {
        background: #161b22 !important; border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
    }
    [data-testid="stSidebar"] input:focus {
        border-color: #58a6ff !important; box-shadow: 0 0 0 1px #58a6ff !important;
    }
    /* Sidebar slider track */
    [data-testid="stSidebar"] .st-bg { background: #30363d !important; }
    [data-testid="stSidebar"] .st-b2 { background: #30363d !important; }
    /* Sidebar expander */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: transparent !important; border: 1px solid #21262d !important;
        border-radius: 8px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        color: #c9d1d9 !important;
    }
    /* Sidebar buttons keep green gradient */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #238636, #2ea043) !important;
        color: #fff !important;
    }

    /* ── Buttons ───────────────────────────────────────── */
    .stButton > button {
        width: 100%; border-radius: 8px; font-weight: 600;
        background: linear-gradient(135deg, #238636, #2ea043);
        border: none; color: #fff; padding: 0.6rem 1rem; transition: all 0.2s;
    }
    .stButton > button:hover { opacity: 0.9; transform: translateY(-1px); }
    .stButton > button:active { transform: translateY(0); }

    /* ── Cards ─────────────────────────────────────────── */
    .metric-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 1rem; text-align: center;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #58a6ff; }
    .metric-label { font-size: 0.8rem; color: #8b949e; margin-top: 0.25rem; }

    /* ── Tags ──────────────────────────────────────────── */
    .section-tag {
        font-size: 0.75rem; font-weight: 600; padding: 2px 8px;
        border-radius: 6px; display: inline-block; margin-bottom: 0.4rem;
    }
    .tag-daily { background: #1a3a2e; color: #3fb950; }
    .tag-hourly { background: #1a2e3a; color: #58a6ff; }
    .tag-div { background: #3a1a2e; color: #f78166; }

    /* ── Table ─────────────────────────────────────────── */
    div[data-testid="stDataFrame"] td { font-size: 0.8rem; }

    /* ── Mobile ────────────────────────────────────────── */
    .mobile-hint { display: none; }
    @media (max-width: 768px) {
        .metric-value { font-size: 1.5rem; }
        div[data-testid="column"] { padding: 0.25rem !important; }
        .mobile-hint { display: block; }
    }
</style>
""", unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────
for key, default in [
    ("authenticated", False),
    ("pwd_input", ""),
    ("results_sma_daily", None),
    ("results_sma_hourly", None),
    ("results_div", None),
    ("run_done", False),
    ("data_loaded", False),
    ("last_params", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "demo123")


# ── Password gate ──────────────────────────────────────────────────────────
def handle_unlock():
    if st.session_state.pwd_input == APP_PASSWORD:
        st.session_state.authenticated = True
    else:
        st.session_state.pwd_error = True


if not st.session_state.authenticated:
    st.markdown("""
    <style>[data-testid="stSidebar"] { display: none; }</style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-top:30vh;">
            <div style="font-size:2.5rem;">🔐</div>
            <div style="font-size:1.3rem;font-weight:600;margin-top:0.5rem;">Bursa Screener</div>
            <div style="font-size:0.8rem;color:#8b949e;margin-bottom:1.5rem;">Secure access</div>
        </div>
        """, unsafe_allow_html=True)
        st.text_input(
            "Password", type="password", key="pwd_input",
            label_visibility="collapsed", placeholder="Enter password",
            on_change=handle_unlock,
        )
        if st.button("Unlock", use_container_width=True, type="primary"):
            handle_unlock()
            if st.session_state.authenticated:
                st.rerun()
            else:
                st.error("Wrong password")
    st.stop()

# ── Logout button (top-right) ──────────────────────────────────────────────
c1, c2 = st.columns([6, 1])
with c2:
    if st.button("🔒 Lock", key="lock_btn", help="Lock the app"):
        st.session_state.authenticated = False
        st.session_state.pwd_input = ""
        st.rerun()

# ── Header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.5rem;">
    <span style="font-size:1.6rem;font-weight:700;">Bursa Malaysia Screener</span>
    <span style="background:#21262d;color:#8b949e;font-size:0.7rem;padding:2px 8px;border-radius:12px;">v2.0</span>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: Parameters ────────────────────────────────────────────────────
with st.sidebar:
    # Mobile hint
    st.markdown("""
    <div class="mobile-hint" style="background:#161b22;border:1px solid #30363d;
        border-radius:8px;padding:0.5rem;text-align:center;margin-bottom:0.5rem;
        font-size:0.75rem;color:#8b949e;">
        ← Tap arrow at top-left to open sidebar
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### ⚙️ Parameters")

    with st.expander("SMA Compression", expanded=True):
        periods_str = st.text_input(
            "SMA Periods", value=DEFAULTS["periods"],
            help="Comma-separated", key="cfg_periods",
        )
        sma_periods = [int(x.strip()) for x in periods_str.split(",") if x.strip().isdigit()]
        if not sma_periods:
            sma_periods = [5, 10, 20, 30, 50]

        divergence_pct = st.slider(
            "Divergence ≤ %", 0.5, 10.0, DEFAULTS["div"], 0.5, key="cfg_div",
        )
        compression_bars = st.slider(
            "Min Compression Bars", 5, 60, DEFAULTS["bars"], 5, key="cfg_bars",
        )

    with st.expander("Volume", expanded=True):
        vol_daily = st.number_input(
            "Daily Vol MA >", 0, 10_000_000, DEFAULTS["vol_d"], 100_000,
            format="%d", key="cfg_vol_d",
        )
        vol_hourly = st.number_input(
            "Hourly Vol MA >", 0, 5_000_000, DEFAULTS["vol_h"], 50_000,
            format="%d", key="cfg_vol_h",
        )
        vol_weekly = st.number_input(
            "Weekly Vol MA >", 0, 10_000_000, DEFAULTS["vol_w"], 100_000,
            format="%d", key="cfg_vol_w",
        )

    with st.expander("KDJ Divergence", expanded=True):
        kdj_period = st.slider("KDJ Period", 3, 30, DEFAULTS["kdj_p"], 1, key="cfg_kdj_p")
        kdj_signal = st.slider("KDJ Signal", 1, 10, DEFAULTS["kdj_s"], 1, key="cfg_kdj_s")
        div_lookback = st.slider("Div Lookback", 10, 60, DEFAULTS["div_lb"], 5, key="cfg_div_lb")

    with st.expander("Scoring System", expanded=True):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            score_trend_periods_sel = st.multiselect(
                "Trend Periods",
                options=[5, 10, 20, 30, 50, 60, 120, 200],
                default=DEFAULTS["score_trend_periods"],
                key="cfg_score_trend_periods",
            )
            score_trend_div = st.number_input(
                "Trend Div <%", 0.1, 10.0, DEFAULTS["score_trend_div"], 0.5,
                key="cfg_score_trend_div",
            )
            score_slope_bars = st.slider(
                "SMA200 Slope Bars", 5, 60, DEFAULTS["score_slope_bars"], 5,
                key="cfg_score_slope_bars",
            )
            score_vol_p = st.slider(
                "Vol Period Days", 10, 120, DEFAULTS["score_vol_p"], 10,
                key="cfg_score_vol_p",
            )
        with col_s2:
            score_vol_t = st.number_input(
                "Volatility >%", 1.0, 50.0, DEFAULTS["score_vol_t"], 1.0,
                key="cfg_score_vol_t",
            )
            score_vol_ma_b = st.slider(
                "Vol MA Bars", 3, 50, DEFAULTS["score_vol_ma_b"], 1,
                key="cfg_score_vol_ma_b",
            )
            score_vol_ma_t = st.number_input(
                "Vol MA >", 0, 10_000_000, DEFAULTS["score_vol_ma_t"], 100_000,
                format="%d", key="cfg_score_vol_ma_t",
            )
            score_top_n = st.slider(
                "Top N", 10, 200, DEFAULTS["score_top_n"], 10,
                key="cfg_score_top_n",
            )

    with st.expander("Auto-Refresh", expanded=True):
        auto_refresh = st.toggle("Enable", value=False, key="auto_refresh",
                                 help="Auto-reload data every N minutes")
        refresh_min = st.select_slider(
            "Interval", options=[5, 10, 15, 30], value=10, key="refresh_interval",
            disabled=not auto_refresh,
        )

    # Auto-reload JavaScript
    if auto_refresh and st.session_state.get("run_done"):
        js = f"""
        <script>
        (function(){{
            var sec = {refresh_min * 60};
            var el = document.getElementById('countdown');
            if (el) el.textContent = Math.floor(sec/60) + 'm ' + (sec%60) + 's';
            var t = setInterval(function(){{
                sec--;
                if (el) el.textContent = Math.floor(sec/60) + 'm ' + (sec%60) + 's';
                if (sec <= 0) window.location.reload();
            }}, 1000);
        }})();
        </script>
        """
        st.components.v1.html(js, height=0)
        st.info(f"⏱ Next refresh in {refresh_min} min")

    st.markdown("---")

    col_run, col_reset = st.columns([3, 1])
    with col_run:
        refresh_clicked = st.button("🔄 Refresh Data", type="primary", use_container_width=True,
                                    help="Force fresh download from Yahoo Finance")
    with col_reset:
        reset_clicked = st.button("↺", help="Reset all parameters to defaults", key="reset_btn",
                                  type="secondary", use_container_width=True)
        if reset_clicked:
            for k in list(st.session_state.keys()):
                if k.startswith("cfg_"):
                    del st.session_state[k]
            st.rerun()

    cache_age = ""
    if st.session_state.get("_data_ts"):
        age_min = (time.time() - st.session_state["_data_ts"]) // 60
        cache_age = f" | Cache: {int(age_min)}m ago"
    st.caption(f"Tickers: {len(load_tickers(TICKERS_FILE))}{cache_age}")


# ── ROE fetcher ────────────────────────────────────────────────────────────
def _fetch_one_roe(tkr):
    """Fetch ROE for a single ticker (own session + crumb, avoids thread conflicts)."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    try:
        sess.get("https://fc.yahoo.com/", timeout=10)
        r = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if r.status_code != 200:
            return None
        crumb = r.text.strip()

        r = sess.get(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{tkr}",
            params={"modules": "financialData", "crumb": crumb},
            timeout=10,
        )
        if r.status_code == 200:
            j = r.json()
            fd = j.get("quoteSummary", {}).get("result", [{}])[0].get("financialData", {})
            roe = fd.get("returnOnEquity", {})
            if isinstance(roe, dict) and roe.get("raw") is not None:
                return roe["raw"]
    except Exception:
        pass
    return None


def fetch_roe_batch(tickers, workers=4):
    """Fetch ROE for a list of tickers (concurrent, each gets its own session)."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch_one_roe, tkr): tkr for tkr in tickers}
        for f in as_completed(futs):
            tkr = futs[f]
            try:
                roe = f.result()
                if roe is not None:
                    results[tkr] = round(roe * 100, 2)
            except Exception:
                pass
    return results


# ── Helpers ─────────────────────────────────────────────────────────────────
def _strip_kl(tkr):
    return tkr.replace(".KL", "") if isinstance(tkr, str) else tkr


def _make_df(results, cols_show, col_map, col_fmt=None):
    """Build display dataframe with .KL stripped and ROE scored."""
    if not results:
        return None
    df = pd.DataFrame(results)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].apply(_strip_kl)
    cols = [c for c in cols_show if c in df.columns]
    df = df[cols].rename(columns=col_map)
    return df


# ── Data loader (manual cache, 1hr TTL) ────────────────────────────────────
DATA_CACHE_TTL = 3600  # seconds

def load_data_with_progress(tickers):
    """Download all data with real-time progress bar."""
    progress = st.progress(0, text="Connecting...")
    status = st.empty()

    last_pct = [0]  # mutable for closure

    def on_ticker(done, total):
        pct = int(done / total * 100)
        if pct > last_pct[0]:
            last_pct[0] = pct
            progress.progress(pct, text=f"Downloading {done}/{total}")
            status.info(f"{done}/{total} tickers loaded — ~{(total - done) * 0.3 // 60:.0f}m remaining")

    data = download_data(tickers, progress_cb=on_ticker)
    progress.progress(100, text=f"Complete — {len(data)} stocks")
    progress.empty()
    status.empty()
    return data


def get_cached_data(force=False):
    """Return cached data if fresh, otherwise download. force=True always re-downloads."""
    now = time.time()
    cache = st.session_state.get("_data_cache")
    cache_time = st.session_state.get("_data_ts", 0)

    if not force and cache is not None and (now - cache_time) < DATA_CACHE_TTL:
        return cache

    tickers = load_tickers(TICKERS_FILE)
    ticker_names = {f"{c}.KL": n for c, n in tickers.items()}
    data = load_data_with_progress(tickers)

    st.session_state._data_cache = data
    st.session_state._data_ts = now
    st.session_state._ticker_names = ticker_names
    return data


# ── Run screeners (auto if cached data exists) ──────────────────────────────
import screener as scr

# Override volume thresholds
scr.VOL_MIN = vol_daily
scr.VOL_MIN_HOURLY = vol_hourly
scr.WEEKLY_VOL_MIN = vol_weekly

# Stage 1: Download (only when forced refresh or no cache)
have_cache = st.session_state.get("_data_cache") is not None
need_download = refresh_clicked or not have_cache

if need_download:
    data = get_cached_data(force=refresh_clicked)
    ticker_names = st.session_state.get("_ticker_names", {})
else:
    data = st.session_state._data_cache
    ticker_names = st.session_state.get("_ticker_names", {})

# Stage 2: Run screeners — cached by param fingerprint, skip on unrelated changes
show_progress = need_download
screener_progress = st.empty()
if show_progress:
    screener_progress = st.progress(0, text="Running screeners...")

# Screener 1: Daily SMA — params: periods, divergence, compression, vol_daily
fp1 = (str(sma_periods), divergence_pct, compression_bars, vol_daily)
if need_download or st.session_state.get("_fp1") != fp1:
    if show_progress:
        screener_progress.progress(30, text="Daily SMA...")
    results1 = list(run_sma_screener(
        data, ticker_names, periods=sma_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))
    st.session_state.results_sma_daily = results1
    st.session_state._fp1 = fp1
else:
    results1 = st.session_state.results_sma_daily

# Screener 2: Hourly SMA — params: periods, divergence, compression, vol_hourly
fp2 = (str(sma_periods), divergence_pct, compression_bars, vol_hourly)
if need_download or st.session_state.get("_fp2") != fp2:
    if show_progress:
        screener_progress.progress(60, text="Hourly SMA...")
    results2 = list(run_sma_hourly_screener(
        data, ticker_names, periods=sma_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))
    st.session_state.results_sma_hourly = results2
    st.session_state._fp2 = fp2
else:
    results2 = st.session_state.results_sma_hourly

# Screener 3: KDJ Divergence — params: div_lookback, vol_daily, kdj_period, kdj_signal
fp3 = (div_lookback, vol_daily, kdj_period, kdj_signal)
if need_download or st.session_state.get("_fp3") != fp3:
    if show_progress:
        screener_progress.progress(75, text="KDJ Divergence...")
    results3 = list(run_divergence_screener(data, ticker_names, lookback=div_lookback))
    st.session_state.results_div = results3
    st.session_state._fp3 = fp3
else:
    results3 = st.session_state.results_div

# Screener 4: Weekly KDJ — params: kdj_period, kdj_signal, vol_weekly
fp4 = (kdj_period, kdj_signal, vol_weekly)
if need_download or st.session_state.get("_fp4") != fp4:
    if show_progress:
        screener_progress.progress(83, text="Weekly KDJ Cross...")
    results4 = list(run_weekly_kdj_screener(data, ticker_names))
    st.session_state.results_weekly = results4
    st.session_state._fp4 = fp4
else:
    results4 = st.session_state.results_weekly

# Screener 5: Scoring — only re-run if data refreshed or scoring params changed
stp = sorted(score_trend_periods_sel) or [20, 30, 60, 120]
score_fingerprint = (tuple(stp), score_trend_div, score_slope_bars, score_vol_p,
                     score_vol_t, score_vol_ma_b, score_vol_ma_t, score_top_n)
last_fp = st.session_state.get("_score_fp")

if need_download or last_fp != score_fingerprint:
    if show_progress:
        screener_progress.progress(88, text="Scoring all stocks...")
    results5 = run_scoring_screener(
        data, ticker_names,
        trend_periods=stp, trend_threshold=score_trend_div,
        sma200_slope_bars=score_slope_bars,
        vol_period=score_vol_p, vol_threshold=score_vol_t,
        vol_ma_bars=score_vol_ma_b, vol_ma_threshold=score_vol_ma_t,
        top_n=score_top_n,
    )
    st.session_state.results_scoring = results5
    st.session_state._score_fp = score_fingerprint
else:
    results5 = st.session_state.results_scoring

# Stage 3: ROE scoring (cache ROE results in session)
all_tickers = set()
for r in results1:
    all_tickers.add(r["ticker"])
for r in results2:
    all_tickers.add(r["ticker"])
for r in results3:
    all_tickers.add(r["ticker"])
for r in results4:
    all_tickers.add(r["ticker"])
for r in results5:
    all_tickers.add(r["ticker"])

roe_cache = st.session_state.get("_roe_cache", {})
new_tickers = all_tickers - set(roe_cache.keys())
roe_map = {t: v for t, v in roe_cache.items() if t in all_tickers}

if new_tickers:
    if show_progress:
        screener_progress.progress(90, text=f"Fetching ROE for {len(new_tickers)} stocks...")
    new_roe = fetch_roe_batch(new_tickers)
    roe_map.update(new_roe)
    roe_cache.update(new_roe)
    st.session_state._roe_cache = roe_cache

# Merge ROE and sort
def _attach_roe(results, roe_map):
    for r in results:
        r["ROE"] = roe_map.get(r["ticker"])
    results.sort(key=lambda r: (
        r["ROE"] is None,
        -(r["ROE"] or 0),
        r.get("divergence_pct", 999),
    ))

_attach_roe(results1, roe_map)
_attach_roe(results2, roe_map)
_attach_roe(results3, roe_map)
_attach_roe(results4, roe_map)
_attach_roe(results5, roe_map)

if show_progress:
    screener_progress.progress(100, text="Done")
    screener_progress.empty()

st.session_state.run_done = True

# ── Show results ───────────────────────────────────────────────────────────
if st.session_state.run_done:
    results1 = st.session_state.results_sma_daily or []
    results2 = st.session_state.results_sma_hourly or []
    results3 = st.session_state.results_div or []
    results4 = st.session_state.results_weekly or []
    results5 = st.session_state.results_scoring or []

    # Summary bar — 5 columns
    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    with tc1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(results1)}</div>
            <div class="metric-label"><span class="tag-daily section-tag">Daily SMA</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(results2)}</div>
            <div class="metric-label"><span class="tag-hourly section-tag">Hourly SMA</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(results3)}</div>
            <div class="metric-label"><span class="tag-div section-tag">KDJ Divergence</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(results4)}</div>
            <div class="metric-label"><span class="tag-div section-tag">Weekly KDJ Cross</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(results5)}</div>
            <div class="metric-label"><span style="background:#2a1a3a;color:#bc8cff;" class="section-tag">Scoring Top</span></div>
        </div>
        """, unsafe_allow_html=True)

    # Detail tables
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        f"📅 Daily SMA ({len(results1)})",
        f"⏱ Hourly SMA ({len(results2)})",
        f"📉 KDJ Divergence ({len(results3)})",
        f"📆 Weekly KDJ ({len(results4)})",
        f"⭐ Scoring ({len(results5)})",
    ])

    with tab1:
        if results1:
            df = _make_df(results1,
                          ["ticker", "name", "close", "trend", "MA20", "divergence_pct", "vol_ma", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "trend": "T", "divergence_pct": "Div%",
                           "vol_ma": "Vol MA", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "T": st.column_config.TextColumn(width="small"),
                             "Div%": st.column_config.NumberColumn(format="%.2f%%", width="small"),
                             "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
                             "Vol MA": st.column_config.NumberColumn(format="%d", width="small"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab2:
        if results2:
            df = _make_df(results2,
                          ["ticker", "name", "close", "trend", "MA20", "divergence_pct", "vol_ma", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "trend": "T", "divergence_pct": "Div%",
                           "vol_ma": "Vol MA", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "T": st.column_config.TextColumn(width="small"),
                             "Div%": st.column_config.NumberColumn(format="%.2f%%", width="small"),
                             "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
                             "Vol MA": st.column_config.NumberColumn(format="%d", width="small"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab3:
        if results3:
            df = _make_df(results3,
                          ["ticker", "name", "close", "kdj_k", "kdj_d", "vol_ma", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "vol_ma": "Vol MA", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
                             "Vol MA": st.column_config.NumberColumn(format="%d", width="small"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab4:
        if results4:
            df = _make_df(results4,
                          ["ticker", "name", "close", "kdj_k", "kdj_d", "kdj_j", "kdj_signal", "vol_ma", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "kdj_signal": "Signal", "vol_ma": "Vol MA", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
                             "Signal": st.column_config.TextColumn(width="small"),
                             "Vol MA": st.column_config.NumberColumn(format="%d", width="small"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab5:
        if results5:
            df = _make_df(results5,
                          ["ticker", "name", "close", "score",
                           "above_200", "sma200_up", "trend_tight", "kdj_sig", "vol_ok", "vol_ma_ok", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "score": "Score",
                           "above_200": ">200", "sma200_up": "200↑", "trend_tight": "Tight",
                           "kdj_sig": "KDJ", "vol_ok": "Vol%", "vol_ma_ok": "VolMA", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Price": st.column_config.NumberColumn(format="%.2f", width="small"),
                             "Score": st.column_config.NumberColumn(format="%d", width="small"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                         })
        else:
            st.caption("No stocks scored.")

        # Backtest
        st.markdown("---")
        st.markdown("#### 🔬 Backtest Scoring System")
        col_bt1, col_bt2, col_bt3 = st.columns(3)
        with col_bt1:
            bt_top_n = st.number_input("Top N", 5, 30, 20, 5, key="bt_top_n")
        with col_bt2:
            bt_interval = st.slider("Interval (weeks)", 1, 4, 2, key="bt_interval")
        with col_bt3:
            bt_run = st.button("Run Backtest", type="secondary", use_container_width=True)

        if bt_run:
            with st.spinner(f"Backtesting over historical dates..."):
                bt_results = backtest_scoring(
                    data, ticker_names,
                    trend_periods=stp, trend_threshold=score_trend_div,
                    sma200_slope_bars=score_slope_bars,
                    vol_period=score_vol_p, vol_threshold=score_vol_t,
                    vol_ma_bars=score_vol_ma_b, vol_ma_threshold=score_vol_ma_t,
                    top_n=bt_top_n, interval_weeks=bt_interval,
                )
            if bt_results:
                df_bt = pd.DataFrame(bt_results)
                # Summary stats
                avg_4w = df_bt["avg_4w"].mean()
                win_4w = df_bt["win_4w"].mean()
                c1, c2 = st.columns(2)
                c1.metric("Avg 4-Week Return", f"{avg_4w:.2f}%")
                c2.metric("Avg 4-Week Win Rate", f"{win_4w:.1f}%")
                st.dataframe(df_bt, hide_index=True, use_container_width=True, height=300)
            else:
                st.warning("Not enough historical data for backtest.")

else:
    # Idle state
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:50vh;gap:1rem;">
        <div style="font-size:3rem;">📊</div>
        <div style="font-size:1.2rem;color:#8b949e;">
            Tap <b>🔄 Refresh Data</b> in the sidebar to start
        </div>
        <div style="font-size:0.8rem;color:#484f58;">
            First run downloads market data (~1-2 min) • Then param tweaks are instant
        </div>
    </div>
    """, unsafe_allow_html=True)
