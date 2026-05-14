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
    SMA_PERIODS, DIVERGENCE_THRESHOLD, MIN_COMPRESSION_BARS,
    KDJ_PERIOD, KDJ_SIGNAL, DIVERGENCE_LOOKBACK,
    VOL_MIN, VOL_MIN_HOURLY,
    TICKERS_FILE,
)

# ── Defaults for reset ─────────────────────────────────────────────────────
DEFAULTS = {
    "periods": "5,10,20,30,50",
    "divergence": DIVERGENCE_THRESHOLD,
    "compression": MIN_COMPRESSION_BARS,
    "vol_daily": VOL_MIN,
    "vol_hourly": VOL_MIN_HOURLY,
    "kdj_period": KDJ_PERIOD,
    "kdj_signal": KDJ_SIGNAL,
    "div_lookback": DIVERGENCE_LOOKBACK,
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
            "Divergence ≤ %", 0.5, 10.0, DEFAULTS["divergence"], 0.5, key="cfg_div",
        )
        compression_bars = st.slider(
            "Min Compression Bars", 5, 60, DEFAULTS["compression"], 5, key="cfg_bars",
        )

    with st.expander("Volume", expanded=True):
        vol_daily = st.number_input(
            "Daily Vol MA >", 0, 10_000_000, DEFAULTS["vol_daily"], 100_000,
            format="%d", key="cfg_vol_d",
        )
        vol_hourly = st.number_input(
            "Hourly Vol MA >", 0, 5_000_000, DEFAULTS["vol_hourly"], 50_000,
            format="%d", key="cfg_vol_h",
        )

    with st.expander("KDJ Divergence", expanded=True):
        kdj_period = st.slider("KDJ Period", 3, 30, DEFAULTS["kdj_period"], 1, key="cfg_kdj_p")
        kdj_signal = st.slider("KDJ Signal", 1, 10, DEFAULTS["kdj_signal"], 1, key="cfg_kdj_s")
        div_lookback = st.slider("Div Lookback", 10, 60, DEFAULTS["div_lookback"], 5, key="cfg_div_lb")

    st.markdown("---")

    col_run, col_reset = st.columns([3, 1])
    with col_run:
        run_clicked = st.button("▶ Run Screener", type="primary", use_container_width=True)
    with col_reset:
        reset_clicked = st.button("↺", help="Reset all parameters to defaults", key="reset_btn",
                                  type="secondary", use_container_width=True)
        if reset_clicked:
            for k, v in DEFAULTS.items():
                st.session_state[f"cfg_{k}"] = v
            st.rerun()

    st.caption(f"Tickers: {len(load_tickers(TICKERS_FILE))} | Data cached 1hr")


# ── ROE fetcher ────────────────────────────────────────────────────────────
def _fetch_roe(tkr, sess, retries=2):
    """Fetch ROE for one ticker via Yahoo quoteSummary."""
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{tkr}"
    params = {"modules": "financialData"}
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, params=params, timeout=10)
            if r.status_code == 200:
                j = r.json()
                fd = j.get("quoteSummary", {}).get("result", [{}])[0].get("financialData", {})
                roe = fd.get("returnOnEquity", {})
                if isinstance(roe, dict):
                    return roe.get("raw")
            time.sleep(0.5)
        except Exception:
            pass
    return None


def fetch_roe_batch(tickers, workers=8):
    """Fetch ROE for a list of tickers concurrently."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch_roe, tkr, sess): tkr for tkr in tickers}
        for f in as_completed(futs):
            tkr = futs[f]
            try:
                roe = f.result()
                if roe is not None:
                    results[tkr] = roe
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


def get_cached_data():
    """Return cached data if fresh, otherwise download."""
    now = time.time()
    cache = st.session_state.get("_data_cache")
    cache_time = st.session_state.get("_data_ts", 0)

    if cache is not None and (now - cache_time) < DATA_CACHE_TTL:
        return cache

    tickers = load_tickers(TICKERS_FILE)
    ticker_names = {f"{c}.KL": n for c, n in tickers.items()}
    data = load_data_with_progress(tickers)

    st.session_state._data_cache = data
    st.session_state._data_ts = now
    st.session_state._ticker_names = ticker_names
    return data


# ── Run screener ───────────────────────────────────────────────────────────
if run_clicked:
    import screener as scr

    # Override volume thresholds
    scr.VOL_MIN = vol_daily
    scr.VOL_MIN_HOURLY = vol_hourly

    # Stage 1: Download (with progress, cached 1hr)
    data = get_cached_data()
    ticker_names = st.session_state.get("_ticker_names", {})

    # Stage 2: Run screeners
    progress = st.progress(0, text="Running screeners...")

    progress.progress(30, text="Daily SMA...")
    results1 = list(run_sma_screener(
        data, ticker_names, periods=sma_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))

    progress.progress(60, text="Hourly SMA...")
    results2 = list(run_sma_hourly_screener(
        data, ticker_names, periods=sma_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))

    progress.progress(80, text="KDJ Divergence...")
    results3 = list(run_divergence_screener(data, ticker_names, lookback=div_lookback))

    # Stage 3: ROE scoring
    all_tickers = set()
    for r in results1:
        all_tickers.add(r["ticker"])
    for r in results2:
        all_tickers.add(r["ticker"])
    for r in results3:
        all_tickers.add(r["ticker"])

    roe_map = {}
    if all_tickers:
        progress.progress(90, text=f"Fetching ROE for {len(all_tickers)} stocks...")
        roe_map = fetch_roe_batch(all_tickers)

    # Merge ROE and sort
    def _attach_roe(results, roe_map):
        for r in results:
            r["ROE"] = roe_map.get(r["ticker"])
        results.sort(key=lambda r: (r["ROE"] is None, -(r["ROE"] or 0)))

    _attach_roe(results1, roe_map)
    _attach_roe(results2, roe_map)
    _attach_roe(results3, roe_map)

    progress.progress(100, text="Done")
    progress.empty()

    st.session_state.results_sma_daily = results1
    st.session_state.results_sma_hourly = results2
    st.session_state.results_div = results3
    st.session_state.run_done = True

# ── Show results ───────────────────────────────────────────────────────────
if st.session_state.run_done:
    results1 = st.session_state.results_sma_daily or []
    results2 = st.session_state.results_sma_hourly or []
    results3 = st.session_state.results_div or []

    # Summary bar
    tc1, tc2, tc3 = st.columns(3)
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

    # Detail tables — tabs on mobile-friendly
    tab1, tab2, tab3 = st.tabs([
        f"📅 Daily SMA ({len(results1)})",
        f"⏱ Hourly SMA ({len(results2)})",
        f"📉 KDJ Divergence ({len(results3)})",
    ])

    with tab1:
        if results1:
            df = _make_df(results1,
                          ["ticker", "name", "close", "MA20", "divergence_pct", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "divergence_pct": "Div%", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Div%": st.column_config.NumberColumn(format="%.2f%%"),
                             "Price": st.column_config.NumberColumn(format="%.2f"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab2:
        if results2:
            df = _make_df(results2,
                          ["ticker", "name", "close", "MA20", "divergence_pct", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "divergence_pct": "Div%", "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Div%": st.column_config.NumberColumn(format="%.2f%%"),
                             "Price": st.column_config.NumberColumn(format="%.2f"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%"),
                         })
        else:
            st.caption("No stocks passed the filter.")

    with tab3:
        if results3:
            df = _make_df(results3,
                          ["ticker", "name", "close", "kdj_k", "kdj_d", "ROE"],
                          {"ticker": "Code", "name": "Name", "close": "Price",
                           "ROE": "ROE%"})
            st.dataframe(df, hide_index=True, use_container_width=True, height=420,
                         column_config={
                             "Price": st.column_config.NumberColumn(format="%.2f"),
                             "ROE%": st.column_config.NumberColumn(format="%.1f%%"),
                         })
        else:
            st.caption("No stocks passed the filter.")

else:
    # Idle state
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:50vh;gap:1rem;">
        <div style="font-size:3rem;">📊</div>
        <div style="font-size:1.2rem;color:#8b949e;">
            Tap <b>▶ Run Screener</b> in the sidebar to scan
        </div>
        <div style="font-size:0.8rem;color:#484f58;">
            1,000+ Bursa Malaysia stocks • 3 strategies • Real-time data
        </div>
    </div>
    """, unsafe_allow_html=True)
