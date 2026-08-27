"""Pine-parity + taxonomy tests for indicators.gm_kdj.

The parity test transcribes the TradingView GM_V2_KDJ formula into a naive
Python loop (ta.highest / ta.lowest / custom_ma(weight=1)) and asserts gm_kdj
matches it bar-by-bar. This is the guard against "Python KDJ != TradingView".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.gm_kdj import gm_kdj, kdj_cross, kdj_divergence, kdj_state


def pine_kdj(high, low, close, period=26, signal=5):
    """Literal transcription of the Pine script (reference implementation)."""
    h = [float(x) for x in high]
    l = [float(x) for x in low]
    c = [float(x) for x in close]
    n = len(c)
    rsv = [0.0] * n
    for i in range(n):
        if i < period - 1:
            rsv[i] = 0.0
        else:
            hh = max(h[i - period + 1: i + 1])
            ll = min(l[i - period + 1: i + 1])
            rsv[i] = 0.0 if hh == ll else 100.0 * (c[i] - ll) / (hh - ll)

    k = [0.0] * n
    d = [0.0] * n
    for i in range(n):
        prev_k = k[i - 1] if i > 0 else rsv[i]
        k[i] = (1.0 * rsv[i] + (signal - 1) * prev_k) / signal
        prev_d = d[i - 1] if i > 0 else k[i]
        d[i] = (1.0 * k[i] + (signal - 1) * prev_d) / signal
    j = [3.0 * k[i] - 2.0 * d[i] for i in range(n)]
    return np.array(k), np.array(d), np.array(j)


def _series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"))


def test_parity_with_pine():
    rng = np.random.default_rng(7)
    n = 220
    close = 20 + np.cumsum(rng.normal(0.05, 0.5, n))
    high = close + rng.uniform(0, 0.8, n)
    low = close - rng.uniform(0, 0.8, n)

    out = gm_kdj(_series(high), _series(low), _series(close), period=26, signal=5)
    pk, pd_, pj = pine_kdj(high, low, close, period=26, signal=5)

    np.testing.assert_allclose(out["k"].to_numpy(), pk, atol=1e-8)
    np.testing.assert_allclose(out["d"].to_numpy(), pd_, atol=1e-8)
    np.testing.assert_allclose(out["j"].to_numpy(), pj, atol=1e-8)


def test_flat_bars_rsv_zero():
    n = 80
    flat = 10.0
    close = pd.Series([flat] * n, index=pd.date_range("2024-01-01", periods=n))
    out = gm_kdj(close, close, close, period=26, signal=5)
    assert (out["rsv"] == 0.0).all()
    assert (out["k"] == 0.0).all()
    assert (out["d"] == 0.0).all()
    assert (out["j"] == 0.0).all()


def test_bounds():
    rng = np.random.default_rng(3)
    n = 200
    close = 30 + np.cumsum(rng.normal(0.02, 0.4, n))
    high = close + rng.uniform(0, 0.5, n)
    low = close - rng.uniform(0, 0.5, n)
    out = gm_kdj(_series(high), _series(low), _series(close), period=26, signal=5)
    assert out["k"].between(-1e-6, 100 + 1e-6).all()
    assert out["d"].between(-1e-6, 100 + 1e-6).all()
    assert out["j"].between(-200, 200).all()  # J = 3K-2D can exceed [0,100]


def test_state_is_single_axis():
    rng = np.random.default_rng(11)
    n = 150
    close = 20 + np.cumsum(rng.normal(0.03, 0.4, n))
    high = close + 0.3
    low = close - 0.3
    out = gm_kdj(_series(high), _series(low), _series(close), period=26, signal=5)
    st = kdj_state(out["k"], out["d"], out["j"])
    # J>K, K>D and J>D are mathematically identical when J = 3K - 2D.
    assert st["j_gt_k"] == st["k_gt_d"] == st["j_gt_d"]


def test_cross_smoke():
    # Simple rising K across D must flip k_d_golden on the crossing bar.
    k = pd.Series([40.0, 45.0, 55.0])
    d = pd.Series([50.0, 50.0, 50.0])
    j = pd.Series([20.0, 35.0, 65.0])
    c = kdj_cross(k, d, j)
    assert c["k_d_golden"] is True
    assert c["k_d_death"] is False


def _run():
    test_parity_with_pine()
    test_flat_bars_rsv_zero()
    test_bounds()
    test_state_is_single_axis()
    test_cross_smoke()
    print("All gm_kdj tests passed")


if __name__ == "__main__":
    _run()
