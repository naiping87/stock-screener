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
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screener import (
    load_tickers, download_data,
    run_ema_screener, run_ema_hourly_screener, run_divergence_screener,
    run_weekly_kdj_screener, run_daily_kdj_screener, run_scoring_screener, backtest_scoring,
    EMA_PERIODS, DIVERGENCE_THRESHOLD, MIN_COMPRESSION_BARS,
    KDJ_PERIOD, KDJ_SIGNAL, DIVERGENCE_LOOKBACK,
    VOL_MIN, VOL_MIN_HOURLY, WEEKLY_VOL_MIN, DAILY_VOL_MIN, DAILY_VOL_RATIO,
    SCORE_TREND_PERIODS, SCORE_TREND_THRESHOLD, SCORE_EMA200_SLOPE_BARS,
    SCORE_VOL_PERIOD, SCORE_VOL_THRESHOLD, SCORE_VOL_MA_BARS, SCORE_VOL_MA_THRESHOLD,
    SCORE_TOP_N,
    TICKERS_FILE,
)

from markets import get as get_market, list_all as list_markets

# ── Defaults for reset ─────────────────────────────────────────────────────
DEFAULTS = {
    "periods": [10, 20, 50, 100, 200],
    "div": DIVERGENCE_THRESHOLD,
    "bars": MIN_COMPRESSION_BARS,
    "vol_d": VOL_MIN,
    "vol_h": VOL_MIN_HOURLY,
    "vol_w": WEEKLY_VOL_MIN,
    "vol_d_kdj": DAILY_VOL_MIN,
    "daily_vol_r": DAILY_VOL_RATIO,
    "kdj_p": KDJ_PERIOD,
    "kdj_s": KDJ_SIGNAL,
    "div_lb": DIVERGENCE_LOOKBACK,
    "score_trend_periods": [10, 20, 50, 100, 200],
    "score_trend_div": SCORE_TREND_THRESHOLD,
    "score_slope_bars": SCORE_EMA200_SLOPE_BARS,
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
    /* ══════════════════════════════════════════════════════════════════════════
       Global — dark premium theme
       ══════════════════════════════════════════════════════════════════════ */
    :root {
        --bg-deep: #0d1117;
        --bg-card: rgba(255,255,255,0.03);
        --bg-elevated: #131720;
        --border-subtle: rgba(255,255,255,0.06);
        --border-card: rgba(255,255,255,0.08);
        --text-primary: #e6edf3;
        --text-secondary: #6e7681;
        --text-muted: #484f58;
        --accent: #58a6ff;
        --accent-glow: rgba(88,166,255,0.15);
        --green: #3fb950;
        --green-bg: rgba(63,185,80,0.10);
        --red: #f85149;
        --orange: #d2991d;
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 16px;
        --font-mono: 'SF Mono', 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
    }

    /* Force dark Streamlit theme */
    .stApp {
        background: var(--bg-deep);
    }

    .main .block-container {
        padding-top: 0.75rem;
        max-width: 100%;
    }

    /* Hide Streamlit default elements */
    header[data-testid="stHeader"] { background: transparent !important; }
    #MainMenu, footer { display: none !important; }

    /* ══════════════════════════════════════════════════════════════════════════
       Top Navigation Bar — frosted glass
       ══════════════════════════════════════════════════════════════════════ */
    .nav-bar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.6rem 1.2rem; margin-bottom: 0.75rem;
        background: rgba(13,17,23,0.85);
        backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border-subtle); border-radius: var(--radius-lg);
        position: sticky; top: 0; z-index: 100;
    }
    .nav-brand {
        display: flex; align-items: center; gap: 0.5rem;
        font-size: 1.1rem; font-weight: 700; color: var(--text-primary);
        letter-spacing: -0.02em;
    }
    .nav-brand-icon {
        width: 28px; height: 28px; border-radius: 7px;
        background: linear-gradient(135deg, #1a6ff5, #3b9fff);
        display: flex; align-items: center; justify-content: center;
        font-size: 0.8rem;
    }
    .nav-badge {
        font-size: 0.65rem; font-weight: 600; padding: 2px 8px;
        border-radius: 10px; background: var(--accent-glow); color: var(--accent);
        letter-spacing: 0.03em;
    }
    .nav-status {
        display: flex; align-items: center; gap: 0.4rem;
        font-size: 0.7rem; color: var(--text-secondary);
    }
    .nav-dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: var(--green); box-shadow: 0 0 6px var(--green);
        animation: pulse-dot 2s ease-in-out infinite;
    }
    @keyframes pulse-dot {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Sidebar — glass panel
       ══════════════════════════════════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        min-width: 320px !important; max-width: 480px !important;
        resize: horizontal; overflow: auto;
        background: rgba(13,17,23,0.7) !important;
        backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
        border-right: 1px solid var(--border-subtle) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        min-width: 320px !important; max-width: 480px !important; width: 100% !important;
        padding: 1rem 1.2rem !important;
    }

    /* Sidebar expanders */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        font-size: 0.82rem; font-weight: 600; color: var(--text-primary);
        border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
        padding: 0.6rem 0.8rem; background: var(--bg-card);
        transition: all 0.15s;
    }
    [data-testid="stSidebar"] .streamlit-expanderHeader:hover {
        border-color: rgba(255,255,255,0.12);
    }
    [data-testid="stSidebar"] .streamlit-expanderContent {
        border: 1px solid var(--border-subtle); border-top: none;
        border-radius: 0 0 var(--radius-sm) var(--radius-sm);
        padding: 0.6rem 0.8rem; margin-top: -1px;
    }

    /* Sidebar section titles */
    .sidebar-section-title {
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: var(--text-muted); margin: 1rem 0 0.4rem 0;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Buttons
       ══════════════════════════════════════════════════════════════════════ */
    .stButton > button {
        width: 100%; border-radius: var(--radius-sm); font-weight: 600;
        border: 1px solid rgba(255,255,255,0.1) !important;
        padding: 0.55rem 1rem; transition: all 0.2s ease;
        font-size: 0.82rem; letter-spacing: 0.01em;
    }
    .stButton > button:hover {
        border-color: rgba(255,255,255,0.2) !important;
        transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .stButton > button:active { transform: translateY(0); }

    /* Primary button — glow effect, 7px radius */
    button[kind="primary"] {
        background: linear-gradient(135deg, #1a6ff5, #3b9fff) !important;
        color: #fff !important; border: none !important;
        border-radius: 7px !important;
        box-shadow: 0 0 12px rgba(26,111,245,0.3), 0 2px 6px rgba(0,0,0,0.3) !important;
    }
    button[kind="primary"]:hover {
        box-shadow: 0 0 20px rgba(26,111,245,0.5), 0 4px 12px rgba(0,0,0,0.4) !important;
    }

    /* Lock button */
    button[kind="secondary"] {
        background: rgba(255,255,255,0.04) !important; color: var(--text-secondary) !important;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Metric cards — glass + subtle glow
       ══════════════════════════════════════════════════════════════════════ */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border-card); border-radius: var(--radius-md);
        padding: 1rem 0.8rem; text-align: center;
        backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
        transition: all 0.2s ease; cursor: default;
    }
    .metric-card:hover {
        border-color: rgba(255,255,255,0.14);
        transform: translateY(-1px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .metric-value {
        font-size: 2.2rem; font-weight: 700; color: var(--text-primary);
        letter-spacing: -0.03em; font-family: var(--font-mono);
        line-height: 1.1;
    }
    .metric-label {
        font-size: 0.72rem; margin-top: 0.35rem; opacity: 0.7;
        font-weight: 500; letter-spacing: 0.02em;
    }

    /* Metric accent colors */
    .metric-accent-daily .metric-value { color: var(--green); }
    .metric-accent-hourly .metric-value { color: var(--accent); }
    .metric-accent-kdj .metric-value { color: #f78166; }
    .metric-accent-weekly .metric-value { color: #d2a8ff; }
    .metric-accent-score .metric-value {
        background: linear-gradient(135deg, #f0883e, #ffd740);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Section tags
       ══════════════════════════════════════════════════════════════════════ */
    .section-tag {
        font-size: 0.68rem; font-weight: 600; padding: 2px 8px;
        border-radius: 5px; display: inline-block; margin-bottom: 0.3rem;
        letter-spacing: 0.02em;
    }
    .tag-daily { background: var(--green-bg); color: var(--green); }
    .tag-hourly { background: var(--accent-glow); color: var(--accent); }
    .tag-div { background: rgba(247,129,102,0.12); color: #f78166; }
    .tag-score { background: rgba(210,168,255,0.12); color: #d2a8ff; }

    /* ══════════════════════════════════════════════════════════════════════════
       Tabs — underline style
       ══════════════════════════════════════════════════════════════════════ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0; border-bottom: 1px solid var(--border-subtle);
        margin-bottom: 0.75rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.82rem; font-weight: 500; padding: 0.6rem 1rem;
        color: var(--text-secondary); border-radius: 0;
        background: transparent !important; border: none !important;
        border-bottom: 2px solid transparent !important;
        transition: all 0.15s;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--text-primary);
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--accent) !important;
        border-bottom-color: var(--accent) !important;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       AgGrid — Institutional Grade dark table (streamlit base)
       ══════════════════════════════════════════════════════════════════════ */

    .ag-theme-streamlit {
        --ag-background-color: #0d1117 !important;
        --ag-foreground-color: #e6edf3 !important;
        --ag-secondary-foreground-color: #6e7681 !important;
        --ag-header-background-color: #161b22 !important;
        --ag-header-foreground-color: #6e7681 !important;
        --ag-odd-row-background-color: #131720 !important;
        --ag-row-hover-color: rgba(31,111,235,0.10) !important;
        --ag-selected-row-background-color: rgba(31,111,235,0.14) !important;
        --ag-border-color: rgba(255,255,255,0.05) !important;
        --ag-secondary-border-color: rgba(255,255,255,0.03) !important;
        --ag-input-border-color: #30363d !important;
        --ag-input-focus-border-color: #58a6ff !important;
        --ag-input-disabled-background-color: rgba(255,255,255,0.02) !important;
        --ag-disabled-foreground-color: #484f58 !important;
        --ag-font-size: 13px !important;
        --ag-font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, sans-serif !important;
        --ag-row-height: 34px !important;
        --ag-header-height: 38px !important;
        background: #0d1117 !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }

    .ag-theme-streamlit .ag-header { background: #161b22 !important; border-bottom: 1px solid rgba(255,255,255,0.08) !important; }
    .ag-theme-streamlit .ag-header-cell { padding: 0 10px !important; color: #6e7681 !important; font-weight: 600; font-size: 10.5px; }
    .ag-theme-streamlit .ag-header-cell-label { font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; }
    .ag-theme-streamlit .ag-sort-indicator-icon { color: #58a6ff !important; opacity: 0.9; }
    .ag-theme-streamlit .ag-row { border-bottom: 1px solid rgba(255,255,255,0.015) !important; color: #e6edf3 !important; }
    .ag-theme-streamlit .ag-row:hover { background: rgba(31,111,235,0.10) !important; cursor: pointer; }
    .ag-theme-streamlit .ag-cell { padding: 0 10px !important; line-height: 34px !important; color: #e6edf3 !important; border-right: none !important; }
    .ag-theme-streamlit .ag-cell:focus { border-color: #58a6ff !important; box-shadow: inset 0 0 0 1px rgba(88,166,255,0.3) !important; outline: none !important; }
    .ag-theme-streamlit .ag-paging-panel { background: #0d1117 !important; border-top: 1px solid rgba(255,255,255,0.06) !important; color: #6e7681 !important; font-size: 12px !important; height: 40px !important; }
    .ag-theme-streamlit .ag-paging-button { background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 5px !important; color: #6e7681 !important; }
    .ag-theme-streamlit .ag-paging-button:hover { background: rgba(255,255,255,0.08) !important; }
    .ag-theme-streamlit .ag-floating-filter { background: #0d1117 !important; }
    .ag-theme-streamlit .ag-floating-filter-body input { background: rgba(255,255,255,0.04) !important; border: 1px solid #30363d !important; border-radius: 5px !important; color: #e6edf3 !important; font-size: 11.5px !important; padding: 4px 8px !important; }
    .ag-theme-streamlit .ag-floating-filter-body input:focus { border-color: #58a6ff !important; box-shadow: 0 0 0 2px rgba(88,166,255,0.12) !important; }
    .ag-theme-streamlit .ag-menu, .ag-theme-streamlit .ag-filter { background: #161b22 !important; border: 1px solid rgba(255,255,255,0.1) !important; border-radius: 8px !important; box-shadow: 0 8px 24px rgba(0,0,0,0.6) !important; }
    .ag-theme-streamlit ::-webkit-scrollbar { width: 5px; height: 5px; }
    .ag-theme-streamlit ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 3px; }
    .ag-theme-streamlit ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }

    /* ══════════════════════════════════════════════════════════════════════════
       Empty state
       ══════════════════════════════════════════════════════════════════════ */
    .empty-state {
        display: flex; flex-direction: column; align-items: center;
        padding: 2rem 1rem; gap: 0.5rem; text-align: center;
    }
    .empty-state-icon { font-size: 2rem; opacity: 0.3; }
    .empty-state-text { font-size: 0.85rem; color: var(--text-muted); }

    /* ══════════════════════════════════════════════════════════════════════════
       Backtest section
       ══════════════════════════════════════════════════════════════════════ */
    .backtest-divider {
        margin: 1.5rem 0 1rem 0; border: none;
        border-top: 1px solid var(--border-subtle);
    }
    .backtest-card {
        background: var(--bg-card); border: 1px solid var(--border-card);
        border-radius: var(--radius-md); padding: 1rem 1.2rem;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Form controls — dark modernized
       ══════════════════════════════════════════════════════════════════════ */

    /* Label */
    [data-testid="stSlider"] label, [data-testid="stNumberInput"] label,
    [data-testid="stSelectbox"] label, [data-testid="stToggle"] label {
        font-size: 0.76rem !important; font-weight: 500 !important;
        color: var(--text-secondary) !important; margin-bottom: 0.2rem !important;
    }

    /* ── Slider — track #30363D, active #58A6FF, round thumb ── */
    [data-testid="stSlider"] { padding-top: 0 !important; }
    /* Track */
    [data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stTrack"] {
        background: #30363d !important;
    }
    /* Filled track */
    [data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stTickBar"] ~ div {
        display: none;
    }
    /* Thumb — solid round */
    [data-testid="stSlider"] div[role="slider"] {
        background: #e6edf3 !important; border: 2px solid #58a6ff !important;
        box-shadow: 0 0 6px rgba(88,166,255,0.3), 0 1px 3px rgba(0,0,0,0.4) !important;
        width: 16px !important; height: 16px !important; border-radius: 50% !important;
        transition: box-shadow 0.15s;
    }
    [data-testid="stSlider"] div[role="slider"]:hover {
        box-shadow: 0 0 12px rgba(88,166,255,0.5), 0 1px 3px rgba(0,0,0,0.4) !important;
    }
    /* Slider fill bar */
    [data-testid="stSlider"] div[data-baseweb="slider"] > div > div:first-child {
        background: #58a6ff !important; height: 3px !important; border-radius: 2px;
    }
    /* Tick marks / scale */
    [data-testid="stSlider"] div[data-baseweb="slider"] div[data-testid="stTickBar"] {
        color: var(--text-muted) !important; font-size: 0.65rem !important;
    }

    /* ── Number Input ──────────────────────────────────── */
    [data-testid="stNumberInput"] input {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid #30363d !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
        font-family: 'SF Mono','JetBrains Mono','Consolas',monospace; font-size: 0.82rem !important;
        padding: 0.4rem 0.55rem !important;
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stNumberInput"] input:focus-visible {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px rgba(88,166,255,0.15) !important;
        outline: none !important;
    }
    [data-testid="stNumberInput"] button {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        color: var(--text-secondary) !important;
        border-radius: 4px !important;
    }
    [data-testid="stNumberInput"] button:hover {
        background: rgba(255,255,255,0.08) !important;
        color: var(--text-primary) !important;
    }

    /* ── Select / Dropdown ─────────────────────────────── */
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-primary) !important;
    }

    /* ── Multiselect ───────────────────────────────────── */
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: var(--radius-sm) !important;
    }
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
        font-size: 0.76rem !important; padding: 2px 7px !important;
        border-radius: 5px !important;
        background: rgba(88,166,255,0.12) !important; color: var(--accent) !important;
    }
    [data-testid="stMultiSelect"] li {
        font-size: 0.82rem !important;
    }

    /* Dropdown popup */
    [data-baseweb="popover"], [data-baseweb="menu"] {
        background: #0d1117 !important; border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: var(--radius-sm) !important;
    }

    /* ══════════════════════════════════════════════════════════════════════════
       Native component dark overrides
       ══════════════════════════════════════════════════════════════════════ */

    /* st.metric */
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important; font-family: var(--font-mono);
    }
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
    }
    [data-testid="stMetricDelta"] { font-family: var(--font-mono); }

    /* st.info / st.warning / st.error / st.success */
    [data-testid="stAlert"] {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: var(--radius-sm) !important;
        color: var(--text-secondary) !important;
    }
    [data-testid="stAlert"] svg { opacity: 0.7; }

    /* st.spinner */
    [data-testid="stSpinner"] { color: var(--accent) !important; }

    /* st.caption */
    [data-testid="stCaptionContainer"] { color: var(--text-muted) !important; }

    /* ══════════════════════════════════════════════════════════════════════════
       Idle state
       ══════════════════════════════════════════════════════════════════════ */
    .idle-container {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; min-height: 50vh; gap: 1rem;
        text-align: center;
    }
    .idle-icon { font-size: 3.5rem; opacity: 0.5; }
    .idle-title { font-size: 1.1rem; color: var(--text-secondary); }
    .idle-hint { font-size: 0.78rem; color: var(--text-muted); }

    /* ══════════════════════════════════════════════════════════════════════════
       Mobile
       ══════════════════════════════════════════════════════════════════════ */
    .mobile-hint { display: none; }
    @media (max-width: 768px) {
        .nav-bar { padding: 0.5rem 0.8rem; border-radius: var(--radius-md); }
        .nav-brand { font-size: 0.95rem; }
        .metric-value { font-size: 1.6rem; }
        .metric-card { padding: 0.7rem 0.5rem; }
        div[data-testid="column"] { padding: 0.2rem !important; }
        .mobile-hint { display: block; }
        [data-testid="stSidebar"] { min-width: 280px !important; max-width: 100vw !important; }
    }
</style>
""", unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────
for key, default in [
    ("authenticated", False),
    ("pwd_input", ""),
    ("results_ema_daily", None),
    ("results_ema_hourly", None),
    ("results_div", None),
    ("run_done", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Load alert_paused from alert_state.json (only on first run, before widget init)
if "_alert_pause_loaded" not in st.session_state:
    st.session_state._alert_pause_loaded = True
    _default_paused = False
    try:
        import json
        if os.path.exists(ALERT_STATE_FILE):
            with open(ALERT_STATE_FILE) as f:
                _default_paused = json.load(f).get("paused", False)
    except Exception:
        pass
    st.session_state.alert_paused = _default_paused
    st.session_state._prev_alert_paused = _default_paused

APP_PASSWORD = st.secrets.get("APP_PASSWORD", "demo123")

# Auto-login via URL query param (persists across refreshes)
if not st.session_state.authenticated:
    if "1" in st.query_params.get_all("auth"):
        st.session_state.authenticated = True
        st.rerun()

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
        <div style="text-align:center;margin-top:25vh;">
            <div style="font-size:3rem;margin-bottom:0.5rem;">🔐</div>
            <div style="font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;">Bursa Screener</div>
            <div style="font-size:0.8rem;color:#8b949e;margin-bottom:2rem;margin-top:0.3rem;">
                Professional Market Analytics
            </div>
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

# Redirect to ?auth=1 after first login so URL persists across refreshes
if not st.query_params.get("auth"):
    st.query_params["auth"] = "1"
    st.rerun()

# ── Heartbeat: touch a file so alert_monitor knows the page is open ────────
HEARTBEAT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_heartbeat.txt")
try:
    with open(HEARTBEAT_FILE, "w") as _hf:
        _hf.write(str(time.time()))
except Exception:
    pass  # never let heartbeat failure break the app

# ── Alert pause helper ─────────────────────────────────────────────────────
ALERT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_state.json")

def _update_alert_pause(paused):
    """Write the paused flag to alert_state.json so alert_monitor respects it."""
    import json
    state = {}
    if os.path.exists(ALERT_STATE_FILE):
        try:
            with open(ALERT_STATE_FILE) as f:
                state = json.load(f)
        except Exception:
            pass
    state["paused"] = paused
    try:
        with open(ALERT_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

# ── Logout button (top-right) ──────────────────────────────────────────────
c1, c2 = st.columns([6, 1])
with c2:
    if st.button("🔒 Lock", key="lock_btn", help="Lock the app"):
        st.session_state.authenticated = False
        st.session_state.pwd_input = ""
        st.query_params.clear()
        st.markdown("""<script>window.location.search='';</script>""", unsafe_allow_html=True)
        st.rerun()

# ── Header ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="nav-bar">
    <div class="nav-brand">
        <div class="nav-brand-icon">📈</div>
        Bursa Malaysia Screener
        <span class="nav-badge">PRO</span>
    </div>
    <div class="nav-status">
        <div class="nav-dot"></div>
        Live Market Data
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: Parameters ────────────────────────────────────────────────────
with st.sidebar:
    # ── Market selector ─────────────────────────────────────────────────
    st.markdown('<div class="sidebar-section-title">🌍 Market</div>', unsafe_allow_html=True)
    all_markets = list_markets()
    market_codes = [m.code for m in all_markets]
    market_labels = [m.label for m in all_markets]

    if "_market_code" not in st.session_state:
        st.session_state._market_code = market_codes[0] if market_codes else "my"

    cur_idx = market_codes.index(st.session_state._market_code) if st.session_state._market_code in market_codes else 0
    selected_label = st.selectbox(
        "Select Market", market_labels, index=cur_idx,
        key="market_selector", label_visibility="collapsed",
    )
    selected_code = market_codes[market_labels.index(selected_label)]

    if st.session_state._market_code != selected_code:
        st.session_state._market_code = selected_code
        st.session_state._clear_download_cache = True

        for k in list(st.session_state.keys()):
            if k.startswith("_fp") or k.startswith("results_") or k == "run_done":
                st.session_state.pop(k, None)
        st.rerun()

    market = get_market(selected_code)
    st.session_state._market_code = selected_code  # store code, not object
    st.session_state._market = market  # cached for use outside sidebar

    # Mobile hint
    st.markdown("""
    <div class="mobile-hint" style="background:#161b22;border:1px solid #30363d;
        border-radius:8px;padding:0.5rem;text-align:center;margin-bottom:0.5rem;
        font-size:0.75rem;color:#8b949e;">
        ← Tap arrow at top-left to open sidebar
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">Parameters</div>', unsafe_allow_html=True)

    with st.expander("🔔 Alerts", expanded=True):
        alert_paused = st.toggle(
            "Pause desktop alerts", value=False, key="alert_paused",
            help="When checked, alert_monitor will not send Windows notifications",
        )
        # Write pause flag to alert_state.json so alert_monitor can read it
        if alert_paused != st.session_state.get("_prev_alert_paused", None):
            _update_alert_pause(alert_paused)
            st.session_state._prev_alert_paused = alert_paused

    with st.expander("EMA Compression", expanded=True):
        ema_periods = st.multiselect(
            "EMA Periods",
            options=[10, 20, 50, 100, 200],
            default=DEFAULTS["periods"],
            key="cfg_periods",
        )
        if not ema_periods:
            ema_periods = [10, 20, 50, 100, 200]

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
        vol_daily = st.number_input(
            "Daily KDJ Vol MA >", 0, 10_000_000, DEFAULTS["vol_d_kdj"], 100_000,
            format="%d", key="cfg_kdj_vol_d",
        )
        daily_vol_ratio = st.slider("Daily KDJ Vol Ratio", 1.0, 3.0, DEFAULTS["daily_vol_r"], 0.1, key="cfg_kdj_vol_r")

    with st.expander("KDJ Divergence", expanded=True):
        kdj_period = st.slider("KDJ Period", 3, 30, DEFAULTS["kdj_p"], 1, key="cfg_kdj_p")
        kdj_signal = st.slider("KDJ Signal", 1, 10, DEFAULTS["kdj_s"], 1, key="cfg_kdj_s")
        div_lookback = st.slider("Div Lookback", 10, 60, DEFAULTS["div_lb"], 5, key="cfg_div_lb")

    with st.expander("Scoring System", expanded=True):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            score_trend_periods_sel = st.multiselect(
                "Trend Periods",
                options=[10, 20, 50, 100, 200],
                default=DEFAULTS["score_trend_periods"],
                key="cfg_score_trend_periods",
            )
            score_trend_div = st.number_input(
                "Trend Div <%", 0.1, 10.0, DEFAULTS["score_trend_div"], 0.5,
                key="cfg_score_trend_div",
            )
            score_slope_bars = st.slider(
                "EMA200 Slope Bars", 5, 60, DEFAULTS["score_slope_bars"], 5,
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

    with st.expander("🔄 Auto-Refresh", expanded=False):
        st.markdown('<div style="margin-bottom:0.25rem;font-size:0.7rem;color:#6e7681;display:flex;align-items:center;gap:0.25rem;">'
                     'Enable automatic data reload '
                     '<span title="Data is cached for 1 hour. Auto-refresh forces a fresh download from Yahoo Finance at the selected interval." '
                     'style="cursor:help;opacity:0.4;font-size:0.65rem;line-height:1;">ⓘ</span>'
                     '</div>', unsafe_allow_html=True)
        auto_refresh = st.toggle("Active", value=False, key="auto_refresh")
        st.write("")
        refresh_min = st.select_slider(
            "Interval", options=["5 min", "10 min", "15 min", "30 min"],
            value="10 min", key="refresh_interval", disabled=not auto_refresh,
        )
        _ref_map = {"5 min": 5, "10 min": 10, "15 min": 15, "30 min": 30}
        refresh_min_int = _ref_map.get(refresh_min, 10)

    # Auto-reload JavaScript + institutional status tag
    if auto_refresh and st.session_state.get("run_done"):
        js = f"""
        <script>
        (function(){{
            var sec = {refresh_min_int * 60};
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
        st.markdown(f"""
        <div style="margin-top:0.55rem;display:flex;align-items:center;gap:0.5rem;
                    background:rgba(63,185,80,0.07);border:1px solid rgba(63,185,80,0.18);
                    border-radius:6px;padding:0.4rem 0.7rem;line-height:1.4;">
            <span style="font-size:0.7rem;flex-shrink:0;">🔄</span>
            <span style="font-size:0.72rem;color:#6e7681;flex-shrink:0;">Next refresh in</span>
            <span id="countdown" style="font-size:0.78rem;font-weight:700;color:#3fb950;
                         font-family:'SF Mono','JetBrains Mono','Consolas',monospace;flex-shrink:0;">{refresh_min_int} min</span>
            <span style="font-size:0.7rem;color:#484f58;flex-shrink:0;">• {refresh_min_int}min interval</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="backtest-divider">', unsafe_allow_html=True)

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

    if "_ticker_count" not in st.session_state or st.session_state.get("_ticker_market") != selected_code:
        st.session_state._ticker_count = len(load_tickers(os.path.join(os.path.dirname(os.path.abspath(__file__)), market.tickers_csv), suffix=market.yahoo_suffix))
        st.session_state._ticker_market = selected_code
    st.caption(f"Tickers: {st.session_state._ticker_count} | Data cached 1hr")


# ── ROE fetcher ────────────────────────────────────────────────────────────
def _fetch_one_roe(tkr, crumb, cookies):
    """Fetch ROE for a single ticker using shared crumb + cookies."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    # Seed cookies from master session
    for name, value in (cookies or {}).items():
        sess.cookies.set(name, value)
    try:
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
    """Fetch ROE for a list of tickers (concurrent, shared crumb to reduce requests)."""
    # Get crumb + cookies once from a master session
    master = requests.Session()
    master.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    crumb = None
    cookies = None
    try:
        master.get("https://fc.yahoo.com/", timeout=10)
        crumb_resp = master.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if crumb_resp.status_code == 200:
            crumb = crumb_resp.text.strip()
            cookies = master.cookies.get_dict()
    except Exception:
        pass

    if crumb is None:
        # Fallback: each worker gets its own crumb (original behavior)
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {}
            for tkr in tickers:
                futs[pool.submit(_fetch_one_roe_fallback, tkr)] = tkr
            for f in as_completed(futs):
                tkr = futs[f]
                try:
                    roe = f.result()
                    if roe is not None:
                        results[tkr] = round(roe * 100, 2)
                except Exception:
                    pass
        return results

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch_one_roe, tkr, crumb, cookies): tkr for tkr in tickers}
        for f in as_completed(futs):
            tkr = futs[f]
            try:
                roe = f.result()
                if roe is not None:
                    results[tkr] = round(roe * 100, 2)
            except Exception:
                pass
    return results


def _fetch_one_roe_fallback(tkr):
    """Fallback: fetch ROE with own session + crumb (used when shared crumb fails)."""
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


# ── Helpers ─────────────────────────────────────────────────────────────────
def _strip_kl(tkr):
    """Strip market suffix for display (uses current market from session)."""
    m = st.session_state.get("_market")
    if m and isinstance(tkr, str):
        return m.display_ticker(tkr)
    return tkr.replace(".KL", "") if isinstance(tkr, str) else tkr


# AgGrid conditional formatting JS — Institutional grade
_ROE_CONDITION = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined || params.value === '') return null;
    var v = parseFloat(params.value);
    if (isNaN(v)) return null;
    if (v > 0)  return {'color': '#3fb950', 'fontWeight': '700'};
    if (v < 0)  return {'color': '#f85149', 'fontWeight': '700'};
    return {'color': '#e6edf3'};
}
""")

_PRICE_CONDITION = JsCode("""
function(params) {
    return {'color': '#e6edf3', 'fontWeight': '500', 'fontFamily': 'SF Mono, JetBrains Mono, Consolas, monospace'};
}
""")

_SCORE_CONDITION = JsCode("""
function(params) {
    if (params.value === null || params.value === undefined) return null;
    var v = parseInt(params.value);
    if (isNaN(v)) return null;
    if (v >= 10) return {'color': '#ffd740', 'fontWeight': '800', 'fontSize': '14px'};
    if (v >= 8)  return {'color': '#ffd740', 'fontWeight': '700', 'fontSize': '13px'};
    if (v >= 6)  return {'color': '#ffab40', 'fontWeight': '600'};
    if (v >= 4)  return {'color': '#d2991d', 'fontWeight': '500'};
    return {'color': '#6e7681'};
}
""")

# Zebra striping — Institutional: even #0D1117, odd #131720
_BLOOMBERG_ROW_STYLE = JsCode("""
function(params) {
    var isEven = params.node.rowIndex % 2 === 0;
    return {
        'background-color': isEven ? '#0d1117' : '#131720'
    };
}
""")


def _render_aggrid(df, height=420, roe_col=False, score_col=False):
    """Render an AgGrid table with dark theme, sorting, filtering, and conditional formatting."""
    if df is None or df.empty:
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        resizable=True, sortable=True, filterable=True,
        filterParams={"buttons": ["apply", "reset"], "closeOnApply": True},
    )
    gb.configure_grid_options(
        domLayout='normal', rowHeight=34, headerHeight=38,
        enableCellTextSelection=True, suppressRowClickSelection=True,
        tooltipShowDelay=200, tooltipHideDelay=800,
        pagination=True, paginationPageSize=50, paginationPageSizeSelector=[25, 50, 100],
    )
    # Bloomberg-style zebra striping + hover
    gb.configure_grid_options(getRowStyle=_BLOOMBERG_ROW_STYLE)

    # Column tooltips (mimics the old st.dataframe column_config help)
    _tooltips = {
        'Code': 'Stock ticker code',
        'Name': 'Company name',
        'Price': 'Latest close price',
        'T': 'Trend: ↑ above EMA50, ↓ below',
        'Div%': 'EMA divergence percentage',
        'Vol MA': '20-day volume moving average',
        'ROE%': 'Return on Equity (higher = more profitable)',
        'Score': 'Total score (max 11)',
        '>200': 'Close > EMA200 (trend up)',
        'Align': 'EMA50 > EMA100 > EMA200 (perfect bullish alignment)',
        'Tight': 'EMA divergence below threshold (compression)',
        'BB': 'Bollinger Band width at 20-bar low (max squeeze)',
        'KDJ': 'Daily J > K (bullish daily KDJ)',
        'WKDJ': 'Weekly KDJ golden cross / near-cross (bullish weekly KDJ)',
        'Vol%': '60-day annualized volatility > threshold',
        'Spike': 'Today vol > 2x 20d avg (ignition)',
        'Vol↑': 'Vol MA20 > Vol MA60 (volume expanding)',
        'VolMA': 'Vol MA5 > threshold (liquid)',
        'Signal': 'KDJ signal: crossed / above',
    }

    # Column-specific: narrow columns, conditional formatting
    for col in df.columns:
        tip = _tooltips.get(col, '')
        if col in ('T', 'Trend', '>200', 'Align', 'Tight', 'BB', 'KDJ', 'WKDJ', 'Vol%', 'Spike', 'Vol↑', 'VolMA', 'Signal'):
            gb.configure_column(col, minWidth=44, headerTooltip=tip)
        elif col in ('Code',):
            gb.configure_column(col, minWidth=58, headerTooltip=tip)
        elif col in ('Score',):
            gb.configure_column(col, minWidth=48, headerTooltip=tip, cellStyle=_SCORE_CONDITION)
        elif col in ('Name',):
            gb.configure_column(col, minWidth=120, headerTooltip=tip)
        elif col in ('Price',):
            gb.configure_column(col, minWidth=58, headerTooltip=tip, cellStyle=_PRICE_CONDITION)
        elif col in ('Div%',):
            gb.configure_column(col, minWidth=48, headerTooltip=tip)
        elif col in ('ROE%',):
            gb.configure_column(col, minWidth=52, headerTooltip=tip, cellStyle=_ROE_CONDITION)
        else:
            gb.configure_column(col, headerTooltip=tip)

    # Conditional formatting for ROE (applied above in loop)
    # Conditional formatting for Score (applied above in loop)

    grid_options = gb.build()

    AgGrid(
        df, gridOptions=grid_options,
        height=height, width='100%',
        theme='streamlit',
        update_on=[],
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=True,
    )

    # Post-render: JS safety net to force dark background on grid containers
    st.components.v1.html("""
    <script>
    setTimeout(function() {
        var grids = document.querySelectorAll('.ag-theme-streamlit');
        grids.forEach(function(g) {
            g.style.setProperty('background', '#0d1117', 'important');
            g.querySelectorAll('.ag-root-wrapper, .ag-root, .ag-body-viewport, .ag-center-cols-viewport').forEach(function(el) {
                el.style.setProperty('background', '#0d1117', 'important');
            });
        });
    }, 400);
    </script>
    """, height=0)


# ── Data loader (@st.cache_data persists across refreshes, 1hr TTL) ────────
@st.cache_data(ttl=3600, show_spinner="Downloading market data from Yahoo Finance... (1-2 min)")
def _cached_download(_tickers_json, _timezone="Asia/Kuala_Lumpur", _market="my", _v=3):
    """Download data (cached on server, survives page refresh).
    _tickers_json is a JSON string used as cache key — change it to invalidate."""
    import json
    tickers = json.loads(_tickers_json)
    return download_data(tickers, progress_cb=None, timezone=_timezone, market_code=_market)

def get_data():
    if st.session_state.pop("_clear_download_cache", False):
        _cached_download.clear()
    """Return data (from cache if fresh, otherwise download)."""
    code = st.session_state.get("_market_code", "my")
    m = get_market(code)
    tz = m.timezone
    suffix = m.yahoo_suffix
    tickers_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), m.tickers_csv)
    tickers = load_tickers(tickers_path, suffix=suffix)
    st.toast(f"📡 Loading {code.upper()} market...", icon="🔄")
    # load_tickers already returns keys with the correct suffix — use as-is
    ticker_names = dict(tickers)
    import json
    tickers_json = json.dumps(dict(sorted(tickers.items())))
    data = _cached_download(tickers_json, tz, code)
    return data, ticker_names


# ── Run screeners (auto if cached data exists) ──────────────────────────────
import screener as scr

# Override volume thresholds
scr.VOL_MIN = vol_daily
scr.VOL_MIN_HOURLY = vol_hourly
scr.WEEKLY_VOL_MIN = vol_weekly

# Stage 1: Download (cached — survives refresh, force when button clicked)
if refresh_clicked:
    _cached_download.clear()

try:
    data, ticker_names = get_data()
except Exception as e:
    st.error(f"Data download failed: {e}")
    data, ticker_names = {}, {}

if not data:
    st.warning("No data loaded. Market may be rate-limited. Try again or switch market.")
    st.stop()

# Stage 2: Run screeners — cached by param fingerprint, skip on unrelated changes
screener_progress = st.empty()
screener_progress.progress(0, text="Running screeners...")

# Screener 1: Daily EMA — params: periods, divergence, compression, vol_daily
fp1 = (str(ema_periods), divergence_pct, compression_bars, vol_daily)
if st.session_state.get("_fp1") != fp1:
    screener_progress.progress(30, text="Daily EMA...")
    results1 = list(run_ema_screener(
        data, ticker_names, periods=ema_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))
    st.session_state.results_ema_daily = results1
    st.session_state._fp1 = fp1
else:
    results1 = st.session_state.results_ema_daily

# Screener 2: Hourly EMA — params: periods, divergence, compression, vol_hourly
fp2 = (str(ema_periods), divergence_pct, compression_bars, vol_hourly)
if st.session_state.get("_fp2") != fp2:
    screener_progress.progress(60, text="Hourly EMA...")
    results2 = list(run_ema_hourly_screener(
        data, ticker_names, periods=ema_periods,
        threshold=divergence_pct, min_compression=compression_bars,
    ))
    st.session_state.results_ema_hourly = results2
    st.session_state._fp2 = fp2
else:
    results2 = st.session_state.results_ema_hourly

# Screener 3: KDJ Divergence — params: div_lookback, vol_daily, kdj_period, kdj_signal
fp3 = (div_lookback, vol_daily, kdj_period, kdj_signal)
if st.session_state.get("_fp3") != fp3:
    screener_progress.progress(75, text="KDJ Divergence...")
    results3 = list(run_divergence_screener(data, ticker_names, lookback=div_lookback))
    st.session_state.results_div = results3
    st.session_state._fp3 = fp3
else:
    results3 = st.session_state.results_div

# Screener 4: Weekly KDJ — params: kdj_period, kdj_signal, vol_weekly
fp4 = (kdj_period, kdj_signal, vol_weekly)
if st.session_state.get("_fp4") != fp4:
    screener_progress.progress(83, text="Weekly KDJ Cross...")
    results4 = list(run_weekly_kdj_screener(data, ticker_names))
    st.session_state.results_weekly = results4
    st.session_state._fp4 = fp4
else:
    results4 = st.session_state.results_weekly

# Screener 5: Daily KDJ — params: kdj_period, kdj_signal, vol_daily, daily_vol_ratio
fp_daily = (kdj_period, kdj_signal, vol_daily, daily_vol_ratio)
_cached_daily = st.session_state.get("results_daily_kdj")
# Invalidate stale cache that lacks kdj_signal field (from older code version)
if _cached_daily and len(_cached_daily) > 0 and "kdj_signal" not in _cached_daily[0]:
    st.session_state._fp_daily = None   # force re-run

if st.session_state.get("_fp_daily") != fp_daily:
    screener_progress.progress(86, text="Daily KDJ Cross...")
    results_daily = list(run_daily_kdj_screener(data, ticker_names, vol_min=vol_daily, vol_ratio=daily_vol_ratio))
    st.session_state.results_daily_kdj = results_daily
    st.session_state._fp_daily = fp_daily
else:
    results_daily = st.session_state.results_daily_kdj

# Screener 6: Scoring — always compute (no fingerprint caching, avoids stale results)
stp = sorted(score_trend_periods_sel) or [10, 20, 50, 100, 200]
screener_progress.progress(88, text="Scoring all stocks...")
results5 = run_scoring_screener(
    data, ticker_names,
    trend_periods=stp, trend_threshold=score_trend_div,
    ema200_slope_bars=score_slope_bars,
    vol_period=score_vol_p, vol_threshold=score_vol_t,
    vol_ma_bars=score_vol_ma_b, vol_ma_threshold=score_vol_ma_t,
    top_n=score_top_n,
)
st.info(f"📊 Scoring: {len(results5)} ranked / {len(data)} total")

# Fallback: ensure all result variables exist even if screeners didn't run
if "results1" not in dir() or results1 is None:
    results1 = st.session_state.get("results_ema_daily", [])
if "results2" not in dir() or results2 is None:
    results2 = st.session_state.get("results_ema_hourly", [])
if "results3" not in dir() or results3 is None:
    results3 = st.session_state.get("results_div", [])
if "results4" not in dir() or results4 is None:
    results4 = st.session_state.get("results_weekly", [])
if "results_daily" not in dir() or results_daily is None:
    results_daily = st.session_state.get("results_daily_kdj", [])
if not isinstance(results5, list):
    results5 = st.session_state.get("results_scoring", [])

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
_attach_roe(results_daily, roe_map)
_attach_roe(results5, roe_map)

screener_progress.progress(100, text="Done")
screener_progress.empty()

st.session_state.run_done = True

# ── Show results ───────────────────────────────────────────────────────────
if st.session_state.run_done:
    results1 = st.session_state.results_ema_daily or []
    results2 = st.session_state.results_ema_hourly or []
    results3 = st.session_state.results_div or []
    results4 = st.session_state.results_weekly or []
    results_daily = st.session_state.results_daily_kdj or []
    results5 = st.session_state.get("results_scoring", []) or []

    # Summary bar — 5 columns
    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    with tc1:
        st.markdown(f"""
        <div class="metric-card metric-accent-daily">
            <div class="metric-value">{len(results1)}</div>
            <div class="metric-label"><span class="tag-daily section-tag">Daily EMA</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc2:
        st.markdown(f"""
        <div class="metric-card metric-accent-hourly">
            <div class="metric-value">{len(results2)}</div>
            <div class="metric-label"><span class="tag-hourly section-tag">Hourly EMA</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc3:
        st.markdown(f"""
        <div class="metric-card metric-accent-kdj">
            <div class="metric-value">{len(results3)}</div>
            <div class="metric-label"><span class="tag-div section-tag">KDJ Divergence</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc4:
        st.markdown(f"""
        <div class="metric-card metric-accent-weekly">
            <div class="metric-value">{len(results4)}</div>
            <div class="metric-label"><span class="tag-div section-tag">Weekly KDJ Cross</span></div>
        </div>
        """, unsafe_allow_html=True)
    with tc5:
        st.markdown(f"""
        <div class="metric-card metric-accent-score">
            <div class="metric-value">{len(results5)}</div>
            <div class="metric-label"><span class="tag-score section-tag">Scoring Top</span></div>
        </div>
        """, unsafe_allow_html=True)

    # Second row — Daily KDJ
    td1, td2, td3, td4, td5 = st.columns(5)
    with td3:
        st.markdown(f"""
        <div class="metric-card metric-accent-weekly">
            <div class="metric-value">{len(results_daily)}</div>
            <div class="metric-label"><span class="tag-div section-tag">Daily KDJ Cross</span></div>
        </div>
        """, unsafe_allow_html=True)

    # Detail tables
    tab1, tab2, tab3, tab4, tab_daily, tab5 = st.tabs([
        f"📅 Daily EMA ({len(results1)})",
        f"⏱ Hourly EMA ({len(results2)})",
        f"📉 KDJ Divergence ({len(results3)})",
        f"📆 Weekly KDJ ({len(results4)})",
        f"📊 Daily KDJ ({len(results_daily)})",
        f"⭐ Scoring ({len(results5)})",
    ])

    with tab1:
        if results1:
            df = pd.DataFrame(results1)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "trend": "T", "divergence_pct": "Div%",
                "vol_ma": "Vol MA", "ROE": "ROE%",
            })[["Code", "Name", "Price", "T", "EMA50", "Div%", "Vol MA", "ROE%"]]
            _render_aggrid(df, roe_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks passed the EMA daily filter</div></div>', unsafe_allow_html=True)

    with tab2:
        if results2:
            df = pd.DataFrame(results2)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "trend": "T", "divergence_pct": "Div%",
                "vol_ma": "Vol MA", "ROE": "ROE%",
            })[["Code", "Name", "Price", "T", "EMA50", "Div%", "Vol MA", "ROE%"]]
            _render_aggrid(df, roe_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks passed the EMA hourly filter</div></div>', unsafe_allow_html=True)

    with tab3:
        if results3:
            df = pd.DataFrame(results3)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "vol_ma": "Vol MA", "ROE": "ROE%",
            })[["Code", "Name", "Price", "kdj_k", "kdj_d", "Vol MA", "ROE%"]]
            _render_aggrid(df, roe_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks passed the KDJ divergence filter</div></div>', unsafe_allow_html=True)

    with tab4:
        if results4:
            df = pd.DataFrame(results4)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            if "kdj_signal" not in df.columns:
                df["kdj_signal"] = ""
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "kdj_signal": "Signal", "vol_ma": "Vol MA", "ROE": "ROE%",
            })[["Code", "Name", "Price", "kdj_k", "kdj_d", "kdj_j", "Signal", "Vol MA", "ROE%"]]
            _render_aggrid(df, roe_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks passed the weekly KDJ filter</div></div>', unsafe_allow_html=True)

    with tab_daily:
        if results_daily:
            df = pd.DataFrame(results_daily)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            if "vol_ratio" not in df.columns:
                df["vol_ratio"] = 0
            df["Vol Ratio"] = df["vol_ratio"].apply(lambda x: f"{x:.1f}x" if x else "—")
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "kdj_signal": "Signal", "vol_ma": "Vol MA", "ROE": "ROE%",
            })
            show_cols = [c for c in ["Code", "Name", "Price", "kdj_k", "kdj_d", "kdj_j", "Signal", "Vol Ratio", "Vol MA", "ROE%"] if c in df.columns]
            df = df[show_cols]
            _render_aggrid(df, roe_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks passed the daily KDJ filter</div></div>', unsafe_allow_html=True)

    with tab5:
        if results5:
            df = pd.DataFrame(results5)
            df["ticker"] = df["ticker"].apply(_strip_kl)
            df = df.rename(columns={
                "ticker": "Code", "name": "Name", "close": "Price",
                "score": "Score",
                "above_200": ">200", "aligned": "Align", "trend_tight": "Tight",
                "bb_squeeze": "BB", "kdj_sig": "KDJ", "wkdj_sig": "WKDJ", "vol_ok": "Vol%",
                "vol_spike": "Spike", "vol_expand": "Vol↑", "vol_ma_ok": "VolMA",
                "ROE": "ROE%",
            })[["Code", "Name", "Price", "Score",
                ">200", "Align", "Tight", "BB",
                "KDJ", "WKDJ", "Vol%", "Spike", "Vol↑", "VolMA", "ROE%"]]
            _render_aggrid(df, height=440, roe_col=True, score_col=True)
        else:
            st.markdown('<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No stocks scored yet</div></div>', unsafe_allow_html=True)

        # Backtest
        st.markdown('<hr class="backtest-divider">', unsafe_allow_html=True)
        st.markdown("#### 🔬 Backtest Scoring System")
        st.markdown('<div class="backtest-card">', unsafe_allow_html=True)

        col_bt1, col_bt2, col_bt3 = st.columns([1, 1, 0.8])
        with col_bt1:
            bt_top_n = st.number_input("Top N", 5, 30, 20, 5, key="bt_top_n")
        with col_bt2:
            bt_interval = st.slider("Interval (weeks)", 1, 4, 2, key="bt_interval")
        with col_bt3:
            st.markdown('<div style="height:1.45rem"></div>', unsafe_allow_html=True)
            bt_run = st.button("⚡ Run Backtest", type="secondary", use_container_width=True)

        if bt_run:
            with st.spinner(f"Backtesting over historical dates..."):
                bt_results = backtest_scoring(
                    data, ticker_names,
                    trend_periods=stp, trend_threshold=score_trend_div,
                    ema200_slope_bars=score_slope_bars,
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
                _render_aggrid(df_bt, height=300)
            else:
                st.warning("Not enough historical data for backtest.")

        st.markdown('</div>', unsafe_allow_html=True)

else:
    # Idle state
    st.markdown("""
    <div class="idle-container">
        <div class="idle-icon">📊</div>
        <div class="idle-title">
            Tap <b>🔄 Refresh Data</b> in the sidebar to start
        </div>
        <div class="idle-hint">
            First run downloads market data (~1-2 min) • Then param tweaks are instant
        </div>
    </div>
    """, unsafe_allow_html=True)
