"""Unit tests for screener.py core logic (no network, deterministic)."""

import os

import numpy as np
import pandas as pd
import pytest

import screener

# ── Helpers ───────────────────────────────────────────────────────────────

def make_ohlcv(n=260, seed=0, drift=0.001, vol=3_000_000):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="Asia/Kuala_Lumpur")
    close = 10 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = pd.Series(rng.integers(vol, vol * 2, n).astype(float), index=idx)
    return {
        "close": pd.Series(close, index=idx),
        "open": pd.Series(open_, index=idx),
        "high": pd.Series(high, index=idx),
        "low": pd.Series(low, index=idx),
        "volume": volume,
        "name": "Test",
    }


def make_flat(n=260, price=10.0, vol=3_000_000):
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="Asia/Kuala_Lumpur")
    close = pd.Series(np.full(n, price), index=idx)
    return {
        "close": close,
        "open": close.copy(),
        "high": close * 1.01,
        "low": close * 0.99,
        "volume": pd.Series(np.full(n, float(vol)), index=idx),
        "name": "Flat",
    }


# ── load_tickers / encoding ───────────────────────────────────────────────

def test_load_tickers_utf8(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("7001,Company A\n7002,Company B\n", encoding="utf-8")
    t = screener.load_tickers(str(p), suffix=".KL")
    assert t == {"7001.KL": "Company A", "7002.KL": "Company B"}


def test_load_tickers_gb18030_fallback(tmp_path):
    p = tmp_path / "sh.csv"
    p.write_bytes("600000,浦发银行\n600004,白云机场\n".encode("gbk"))
    t = screener.load_tickers(str(p), suffix=".SS")
    assert t["600000.SS"] == "浦发银行"
    assert t["600004.SS"] == "白云机场"


def test_real_shanghai_csv_decodes():
    path = os.path.join(screener.SCRIPT_DIR, "tickers", "shanghai.csv")
    if not os.path.exists(path):
        pytest.skip("tickers/shanghai.csv not present")
    t = screener.load_tickers(path, suffix=".SS")
    assert "600000.SS" in t
    assert any("\u4e00" <= ch <= "\u9fff" for ch in "".join(t.values()))


# ── download_data (empty = no network) ────────────────────────────────────

def test_download_data_empty_no_network():
    assert screener.download_data({}) == {}


# ── indicators ────────────────────────────────────────────────────────────

def test_calc_divergence_flat_is_zero():
    d = make_flat()
    div, ema = screener._calc_divergence(d["close"], [20, 50])
    assert div is not None and div < 0.01
    assert set(ema) == {20, 50}


def test_calc_divergence_trend_is_large():
    idx = pd.date_range("2024-01-01", periods=260, freq="D", tz="UTC")
    close = pd.Series(10 * 1.005 ** np.arange(260), index=idx)
    div, _ = screener._calc_divergence(close, [20, 200])
    assert div is not None and div > 3.0


def test_compression_flat_true_trend_false():
    flat = make_flat()
    assert screener._check_compression_duration(flat["close"], [20, 50], 3.0, 10) is True

    idx = pd.date_range("2024-01-01", periods=260, freq="D", tz="UTC")
    trend = pd.Series(10 * 1.005 ** np.arange(260), index=idx)
    assert screener._check_compression_duration(trend, [20, 50], 3.0, 10) is False


def test_calc_kdj_bounds():
    d = make_ohlcv()
    k, dd, j = screener._calc_kdj(d["high"], d["low"], d["close"], period=9, signal=3)
    assert k is not None
    assert len(k) == len(d["close"])
    assert k.dropna().between(-0.01, 100.01).all()
    assert dd.dropna().between(-0.01, 100.01).all()
    assert j is not None


def test_run_ema_screener_flat_passes_trend_fails():
    data = {
        "FLAT.KL": make_flat(),
        "TRND.KL": make_ohlcv(seed=3, drift=0.004),
    }
    names = {"FLAT.KL": "Flat Co", "TRND.KL": "Trend Co"}
    results = list(screener.run_ema_screener(
        data, names, periods=[20, 50], threshold=3.0,
        min_compression=10, min_vol=100_000,
    ))
    tickers = {r["ticker"] for r in results}
    assert "FLAT.KL" in tickers
    assert "TRND.KL" not in tickers
