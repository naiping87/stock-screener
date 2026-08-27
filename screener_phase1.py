"""
Phase 1 pulse-detector screener: relative strength + sector strength +
setup/structure + closing strength + breakout quality + risk/reward,
integrated on TOP of the existing 11-factor technical score WITHOUT touching
`run_scoring_screener` — that function keeps its exact behavior (tests that
depend on it stay green).

Every result row is EXPLAINABLE: it carries `reasons` (a list of human-
readable strings) so the UI can show not just "score 88" but WHY.

Views:
  - strength_score  0-100 : is it strong? (RS level + sector + trend alignment)
  - setup_score     0-100 : is it SET UP? (base quality + volume dry-up + ATR)
  - trigger_score   0-100 : is it FIRING? (close strength, breakout, reclaim)
  - breakout_score  0-100 : pivot-break quality (volume, CLV, RS confirmation)
  - master_score    0-100 : weighted combination (see weights below)
  - classification  one of the 12 setup labels (see classify()).

The benchmark (KLCI) close series must be supplied — fetched once per run by
the caller and passed in, so no lookahead and no per-stock network calls.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from screener import run_scoring_screener  # existing 11-factor scorer (UNCHANGED)
from screener_rs import (
    compute_rs_momentum,
    rs_momentum_batch,
    rs_rank_history,
    sector_rank,
    stock_rs,
    stock_rs_batch,
)
from screener_setup import (
    base_quality,
    breakout_quality,
    closing_strength,
    ema_pullback_reclaim,
    effort_vs_result,
    failed_breakdown,
    failed_breakout,
    intraday_position,
    nearest_pivot,
    nearest_support,
    next_resistance,
    price_extension,
    risk_reward,
    shakeout_check,
    yesterday_clv,
)
from screener_rs import stock_vs_sector_rs  # stock vs own-sector RS axis
try:
    from market_regime import market_regime as _market_regime
except Exception:  # optional module — regime degrades to a safe NEUTRAL default
    _market_regime = None

# Master-score weights (fixed, simple, explainable — NOT tuned against the
# backtest; per the audit: no parameter optimization).
W_STRENGTH = 0.30
W_SETUP = 0.25
W_TRIGGER = 0.25
W_BREAKOUT = 0.20

# ── Language support for the explainability strings ─────────────────────────
# The engine returns human-readable `reasons` in the requested language.
# Templates are ENGLISH (canonical); zh/ms override via the dictionaries.
_L = "en"


def set_lang(code: str) -> None:
    """Set the language used for reason strings (called by the UI layer)."""
    global _L
    _L = code if code in ("en", "ms", "zh") else "en"


# English template text → zh / ms. English is the fallback for everything.
_T_ZH = {
    "RS rank #{rank}/100": "RS 排名 #{rank}/100",
    "RS rank +{chg} in 20d": "RS 排名 20 日上升 +{chg}",
    "RS rank falling {chg} in 20d": "⚠ RS 排名回落 {chg}",
    "RS beats market ({chg}%)": "RS 跑赢大盘 (+{chg}%)",
    "RS accelerating (+{chg})": "RS 加速 (+{chg})",
    "Strong sector ({sector} #{rank})": "板块强 ({sector} #{rank})",
    "Technical score {score}/11": "技术分 {score}/11",
    "Base tight ({pct}% range)": "Base 紧凑 ({pct}% 区间)",
    "Higher Low": "Higher Low",
    "Volume Dry-up": "缩量蓄势 (Volume Dry-up)",
    "Volatility contraction": "波动收敛",
    "Only {pct}% off EMA20": "距 EMA20 仅 {pct}%",
    "Beats sector ({chg}%)": "跑赢板块 (+{chg}%)",
    "Failed breakdown {bars}d": "假跌破/洗盘 (Failed Breakdown {bars}天)",
    "Failed breakout {bars}d": "⚠ 假突破 (Failed Breakout {bars}天)",
    "EMA reclaim near EMA{slow} ({pct}%)": "EMA{slow} 回踩+收复 ({pct}%)",
    "Strong close CLV={clv}": "收盘强势 CLV={clv}",
    "Shakeout {bars}d": "洗盘回踩 (Shakeout {bars}天)",
    "Near Pivot ({pct}%)": "逼近 Pivot ({pct}%)",
    "Volume expansion": "放量收涨",
    "Potential Supply (high vol, no gain)": "⚠ 放量滞涨 (Potential Supply)",
    "R:R low ({rr})": "R:R 偏低 ({rr})",
}
_T_MS = {
    # Bahasa Melayu (best-effort; falls back to English when a string is new)
    "RS rank #{rank}/100": "Kedudukan RS #{rank}/100",
    "Volume Dry-up": "Kering Volum",
    "Near Pivot ({pct}%)": "Hampir Pivot ({pct}%)",
}


def _t(template: str, **kwargs: Any) -> str:
    """Format `template` with kwargs in the active language.

    1. Look up the template in the active language table (zh/ms).
    2. Missing → use the English template itself.
    3. Apply kwargs. Unknown language → English.
    """
    if _L == "zh":
        out = _T_ZH.get(template, template)
    elif _L == "ms":
        out = _T_MS.get(template, template)
    else:
        out = template
    return out.format(**kwargs)

# Classification thresholds (generous defaults; avoid overfitting).
EXTENDED_PCT = 15.0          # % above EMA20 → "strong but extended"
NEAR_PIVOT_PCT = 5.0         # % below pivot → "trigger watch"
BASE_MAX_RANGE = 12.0        # max base range_pct to call it a base


def classify(strength: float, setup: float, trigger: float,
             breakout: dict[str, Any], extension: float | None,
             pivot_distance: float | None, base: dict[str, Any],
             rs_momentum: float | None, rr: float | None = None,
             rs_rank: float | None = None,
             rs_rank_chg20: float | None = None,
             ema_reclaim: dict[str, Any] | None = None) -> str:
    """Map sub-scores to one of the 12 setup labels.

    Priority order matters: breakout > trigger-watch > setup > extended >
    emerging-leader > leader > weakening > laggard.
    Risk/reward gate: a TRIGGER WATCH without acceptable R:R is downgraded to
    SETUP (the setup is there, the trade risk is not) — "good stock ≠ good
    trade" (#spec). R:R < 1.0 always caps the classification below trigger.

    LEADERSHIP axis (rs_rank / rs_rank_chg20) is the cross-sectional RS
    percentile and its 20-day change, both computed against the WHOLE market
    at the same date. That is the ONLY thing that decides Leader /
    Emerging Leader / Weakening — technical score and setup never override it.
      LEADER           — rank >= 80 AND holding (chg20 > -5)
      EMERGING LEADER  — rank in [55, 85) AND climbing (chg20 >= +10)
      WEAKENING        — any rank AND rolling over (chg20 <= -10)
    """
    if breakout.get("attempt") and breakout.get("score", 0) >= 60:
        return "BREAKOUT" if breakout["score"] >= 75 else "EXPANSION"
    # An EMA-reclaim at the dynamic support is a high-value LOW-risk setup:
    # rank it just under a genuine breakout, above a plain trigger-watch.
    if ema_reclaim is not None and ema_reclaim.get("detected") and strength >= 40:
        return "EMA RECLAIM"
    rr_ok = rr is None or rr >= 1.0
    if trigger >= 80 and setup >= 50 and pivot_distance is not None \
            and pivot_distance <= NEAR_PIVOT_PCT:
        if rr_ok:
            return "TRIGGER WATCH"
        # R:R unacceptable — the trigger is firing but the trade is not;
        # downgrade so the user sees "setup present, risk unconfirmed".
        return "SETUP"
    if setup >= 60 and strength >= 50:
        return "SETUP"
    if extension is not None and extension >= EXTENDED_PCT and strength >= 70:
        return "STRONG BUT EXTENDED"
    # ── Leadership axis: rs_rank only ────────────────────────────────────
    if rs_rank is not None:
        if rs_rank_chg20 is not None and rs_rank_chg20 <= -10:
            return "WEAKENING"          # was strong, now rolling over (A: 95→90)
        if rs_rank >= 80 and (rs_rank_chg20 is None or rs_rank_chg20 > -5):
            return "LEADER"             # high rank AND holding
        if 55 <= rs_rank < 85 and rs_rank_chg20 is not None and rs_rank_chg20 >= 10:
            return "EMERGING LEADER"    # mid-high rank AND climbing fast (B)
    # fall through to structure-based labels (no RS info or inconclusive)
    if rs_momentum is not None and rs_momentum > 0 and strength >= 70:
        return "EMERGING LEADER"
    if strength >= 80:
        return "LEADER"
    if strength >= 45:
        return "BASE"
    if strength >= 30:
        return "WEAKENING"
    return "LAGGARD"


def run_phase1_screener(
    data: dict[str, dict[str, Any]],
    bench_close: pd.Series | None,
    sector_map: dict[str, str],
    ticker_names: dict[str, str] | None = None,
    rs_periods: tuple[int, ...] = (5, 20, 60, 120),
    top_n: int = 200,
    min_score_tech: int = 0,
    clv_min: float = 0.0,
    ext_pct: float = EXTENDED_PCT,
    base_max_range: float = BASE_MAX_RANGE,
    pivot_window: int = 5,
    include_reasons: bool = True,
    progress_cb: Any | None = None,
    session: str = "eod",
) -> list[dict[str, Any]]:
    """Run the full Phase-1 pulse detector over the loaded market.

    Args:
      data        — {ticker: {close, high, low, volume, name, ...}} (as-loaded).
      bench_close — KLCI (or any index) close series. When None, RS/sector
                    vs-market numbers degrade to None (still returns structure).
      sector_map  — {ticker: sector} from the meta worker; may be empty.
      clv_min     — Closing-Strength filter: only keep rows with CLV >= this.
                    Pass 0.0 to disable (show all).
                    IGNORED in intraday mode (see `session`) — an unfinished
                    bar's close strength is not a reliable filter.
      min_score_tech — existing 11-factor score floor (0 = any).
      progress_cb — optional callable(done:int, total:int) invoked every 50
                    stocks so the UI can show stepwise progress (no-op when
                    None; never affects results).
      session     — "eod" (market closed → CLV/volume FINAL, clv_min applies)
                    or "intraday" (market open → CLV unstable, yesterday_clv
                    is the reference, volume is time-of-day normalized).
                    Passed by the caller (market_session.session_mode).
    """
    ticker_names = ticker_names or {}
    # Optional hand-authored sector map (Bursa taxonomy) — overrides Yahoo meta
    # by raw ticker code. Missing file => no-op, so this is safe everywhere.
    try:
        from screener_rs import apply_sector_override
        _primed = {tkr: sector_map.get(tkr, "") for tkr in data}
        sector_map = apply_sector_override(_primed)
    except Exception:
        pass

    # ── Build the close matrix for cross-sectional RS / sector ranks ─────
    closes: dict[str, pd.Series] = {}
    for tkr, d in data.items():
        s = d.get("close")
        if s is not None and len(s) >= 30:
            closes[tkr] = s
    close_matrix = pd.DataFrame(closes)

    # Sector strength table (per-sector, vs benchmark) — computed once.
    strength_table = None
    if bench_close is not None and not close_matrix.empty:
        try:
            strength_table = sector_rank(close_matrix, sector_map, bench_close)
        except Exception:
            strength_table = None
    sector_strength: dict[str, float] = {}
    if strength_table is not None and not strength_table.empty:
        for _, row in strength_table.iterrows():
            sector_strength[row["sector"]] = float(row["strength"])

    # ── Market regime (whole-market health): RISK_ON / NEUTRAL / RISK_OFF ──
    market_regime_now: dict[str, Any] | None = None
    if _market_regime is not None and not close_matrix.empty:
        try:
            market_regime_now = _market_regime(close_matrix, bench_close)
        except Exception:
            market_regime_now = None

    # ── Stock vs its own sector RS (the "stock vs sector" axis) — once. ──
    sector_rs_table: pd.DataFrame | None = None
    if sector_map and not close_matrix.empty:
        try:
            sector_rs_table = stock_vs_sector_rs(close_matrix, sector_map)
        except Exception:
            sector_rs_table = None

    results: list[dict[str, Any]] = []
    bench_clean = bench_close.dropna() if bench_close is not None else None

    # ── Cross-sectional RS RANKING (the Leader axis): percentile of every
    # stock vs every OTHER stock (not vs the index only), at the last date and
    # 20/40/60 days before it. This is what separates "Leader" (high rank,
    # holding) from "Emerging Leader" (rank climbing fast) from "Weakening"
    # (rank rolling over). Computed ONCE for the whole universe — no per-ticker
    # lookahead, pure snapshots under each date.
    rs_rank_table = None
    if bench_clean is not None and not close_matrix.empty:
        try:
            rs_rank_table = rs_rank_history(close_matrix, bench_clean, lookback=20)
        except Exception:
            rs_rank_table = None

    # ── Pre-compute the 11-factor technical score for the WHOLE universe in
    # ONE call (not once per stock). run_scoring_screener is vectorized-ish
    # (its per-stock cost is the same), but invoking it 950+ times pays
    # function-call + dict-construction overhead each round. One call →
    # 951 rows → dict lookup. Same numbers, ~3x faster.
    tech_map: dict[str, int] = {}
    tech_detail: dict[str, dict[str, Any]] = {}
    try:
        _all = run_scoring_screener(data, ticker_names, top_n=10_000, min_score=0,
                                    components=True)
        for _r in _all:
            tech_map[_r["ticker"]] = int(_r["score"])
            tech_detail[_r["ticker"]] = {
                "weighted": _r.get("score_weighted"),
                "components": _r.get("score_components"),
            }
    except Exception:
        tech_map = {}

    # ── Pre-compute per-ticker RS + momentum for the WHOLE universe in one
    # vectorized pass (was a per-stock loop: stock_rs + compute_rs_momentum
    # called 950+ times). Golden test asserts bit-identical output.
    rs_batch: pd.DataFrame = pd.DataFrame()
    rs_mom_batch: pd.Series = pd.Series(dtype=float)
    if bench_clean is not None and not close_matrix.empty:
        try:
            rs_batch = stock_rs_batch(close_matrix, bench_clean, lookbacks=rs_periods)
            rs_mom_batch = rs_momentum_batch(close_matrix, bench_clean, lookback=5)
        except Exception:
            rs_batch = pd.DataFrame()
            rs_mom_batch = pd.Series(dtype=float)

    _total = max(1, len(data))
    _done = 0

    for tkr, d in data.items():
        _done += 1
        if progress_cb is not None and _done % 50 == 0:
            try:
                progress_cb(_done, _total)
            except Exception:
                progress_cb = None  # progress is cosmetic; never break a run
        close = d.get("close")
        high = d.get("high")
        low = d.get("low")
        vol = d.get("volume")
        if close is None or len(close) < 30:
            continue

        # ── Data robustness: Bursa/Yahoo series commonly end with a NaN bar
        # (unclosed session or a data hole). Truncate to the LAST VALID bar
        # for every series BEFORE any detector runs, so "today" means the
        # last day with real data — never NaN-poisoned.
        close = close.dropna()
        if len(close) < 30:
            continue
        last_ts = close.index[-1]
        if high is not None:
            high = high.loc[:last_ts].dropna()
        if low is not None:
            low = low.loc[:last_ts].dropna()
        if vol is not None:
            vol = vol.loc[:last_ts].fillna(0)
        d = {**d, "close": close, "high": high, "low": low, "volume": vol}
        if high is None or low is None or high.empty or low.empty:
            continue

        # ── Existing 11-factor technical score (UNCHANGED function, but
        # computed once for the whole universe above — lookup here).
        tech_score = tech_map.get(tkr, 0)

        # ── Penny-stock guard (#8923): below RM 0.20 the technical score is
        # untrustworthy — a 0.005 tick IS one "surge", volume numbers are
        # inflated by low prices, and BB width is trivially squeezed. Cap the
        # score contribution so a RM0.05 stock can never outrank a RM5 one.
        last_px = float(close.iloc[-1]) if len(close) else 0.0
        penny_penalty = 0.0
        penny_note = None
        if 0 < last_px < 0.20:
            # score implies 11 factors; penny stocks get at most 60% of it
            tech_score_effective = int(round(tech_score * 0.6))
            penny_penalty = tech_score - tech_score_effective
            tech_score = tech_score_effective
            penny_note = f"penny stock (RM{last_px:.3f}) — tech score discounted"

        # ── RS vs benchmark + momentum (vectorized batch, lookup) ─────────
        rs_vals: dict[str, float | None] = {}
        rs_mom = None
        if bench_clean is not None and tkr in rs_batch.index:
            _rb = rs_batch.loc[tkr]
            rs_vals = {f"rs_{d}d": _rb.get(f"rs_{d}d") for d in rs_periods}
            if tkr in rs_mom_batch.index and pd.notna(rs_mom_batch.get(tkr)):
                rs_mom = float(rs_mom_batch[tkr])

        # ── Sector context ───────────────────────────────────────────────
        sector = sector_map.get(tkr, "")
        sec_str = sector_strength.get(sector)
        # stock vs its OWN sector RS (relative strength axis)
        sector_rs_20d = None
        sector_rs_60d = None
        if sector_rs_table is not None and tkr in sector_rs_table.index:
            _sr = sector_rs_table.loc[tkr]
            sector_rs_20d = float(_sr.get("rel_20d")) if pd.notna(_sr.get("rel_20d")) else None
            sector_rs_60d = float(_sr.get("rel_60d")) if pd.notna(_sr.get("rel_60d")) else None

        # ── Cross-sectional RS rank (Leader axis) for this stock ─────────
        rs_rank = None
        rs_rank_chg20 = None
        rs_rank_chg60 = None
        if rs_rank_table is not None and tkr in rs_rank_table.index:
            _r = rs_rank_table.loc[tkr]
            rs_rank = float(_r["rs_rank"]) if pd.notna(_r.get("rs_rank")) else None
            rs_rank_chg20 = float(_r["rs_rank_chg20"]) if pd.notna(_r.get("rs_rank_chg20")) else None
            rs_rank_chg60 = float(_r["rs_rank_chg60"]) if pd.notna(_r.get("rs_rank_chg60")) else None

        # ── Closing strength / extension / effort ────────────────────────
        # In EOD mode, `clv` is the completed day's close strength (final).
        # In intraday mode the current bar is UNFINISHED — `clv` is still
        # computed and shown (labeled intraday) but NEVER hard-filters;
        # `yesterday_clv` is the reliable completed-day reference and feeds
        # the trigger score instead.
        clv = closing_strength(high, low, close)
        y_clv = yesterday_clv(high, low, close)
        ipos = intraday_position(high, low, close)
        ext = price_extension(close, window=20)
        effort = effort_vs_result(high, low, close, vol)
        intraday = session == "intraday"
        if intraday:
            # Volume is partial (only a fraction of the day has traded);
            # effort_vs_result compares today's partial volume against a
            # 20-day AVERAGE OF FULL DAYS — under-reporting spikes and
            # over-reporting dry-ups. For intraday we neutralize the verdict
            # (still report the raw ratio, no supply/accumulation call).
            if effort.get("verdict") is not None:
                effort = {**effort, "verdict": None}

        # ── Structure: base + pivot/support + shakeout ───────────────────
        base = base_quality(high, low, close, vol, lookback=40)
        pv = nearest_pivot(high, low, close, window=pivot_window)
        sup = nearest_support(low, high, close, window=pivot_window)
        payout_support = sup["price"] if sup else None
        shake = shakeout_check(high, low, close, vol, payout_support)
        # ── EMA pullback + reclaim / failed breakdown / failed breakout ──
        ema_reclaim = ema_pullback_reclaim(close, high, low, vol)
        fbd = failed_breakdown(high, low, close, vol, payout_support)
        fbo = failed_breakout(high, low, close, vol, pv["price"] if pv else None)

        # ── Breakout quality (vs nearest pivot) ──────────────────────────
        bq = breakout_quality(
            high, low, close, vol,
            pivot_price=pv["price"] if pv else None,
            clv=clv,
            rs_20d=rs_vals.get("rs_20d"),
            sector_rel_20d=None,  # filled below when sector table available
        )
        if strength_table is not None and not strength_table.empty and sector:
            row = strength_table[strength_table["sector"] == sector]
            if not row.empty:
                bq_20 = float(row.iloc[0].get("rel_20d") or 0)
                bq["score"] = min(100.0, bq["score"] + max(0.0, min(10.0, bq_20 * 0.2)))
                bq["sector_rel"] = round(bq_20, 2)

        # ── Sub-scores (0-100, each explainable) ─────────────────────────
        # STRENGTH = the LEADERSHIP axis: dominated by the cross-sectional
        # RS percentile (vs the whole market at the same date), with the
        # 20-day rank CHANGE as the "getting stronger" signal. Technical
        # score and sector are secondary (small weight) so the score speaks
        # the same language as the Leader / Emerging Leader classification.
        strength_score = 0.0
        parts_s: list[str] = []
        rs_avg = np.nanmean([rs_vals.get(f"rs_{d}d") for d in rs_periods])
        rs_avg_f = float(rs_avg) if np.isfinite(rs_avg) else 0.0
        if rs_rank is not None and np.isfinite(rs_rank):
            # rank percentile → 0-50 points (rank 50 ≈ 25 pts)
            strength_score += rs_rank * 0.5
            parts_s.append(_t("RS rank #{rank}/100", rank=round(rs_rank)))
        else:
            strength_score += min(35.0, max(0.0, 35 + rs_avg_f))       # fallback
        if rs_rank_chg20 is not None and np.isfinite(rs_rank_chg20):
            if rs_rank_chg20 > 0:
                strength_score += min(20.0, 10 + rs_rank_chg20 * 0.4)
                parts_s.append(_t("RS rank +{chg} in 20d", chg=round(rs_rank_chg20)))
            elif rs_rank_chg20 < -5:
                parts_s.append(_t("RS rank falling {chg} in 20d", chg=round(rs_rank_chg20)))
        elif rs_mom is not None and rs_mom > 0:
            strength_score += min(15.0, 5 + rs_mom)
            parts_s.append(_t("RS accelerating (+{chg})", chg=f"{rs_mom:.2f}"))
        if rs_avg_f > 0 and rs_rank is None and not penny_penalty:
            # only credit "beats market" when the stock actually has a valid
            # rank — a penny stock whose rank was excluded by the tick guard
            # must not fall back to a tick-inflated return either (#8923)
            parts_s.append(_t("RS beats market ({chg}%)", chg=f"{rs_avg_f:.1f}"))
        if sec_str is not None and sec_str > 55:
            strength_score += min(15.0, (sec_str - 50) * 0.5)
            parts_s.append(_t("Strong sector ({sector} #{rank})", sector=sector, rank=round(sec_str)))
        if sector_rs_20d is not None and sector_rs_20d > 0:
            # stock is outperforming its OWN sector — the "stock vs sector" RS axis
            strength_score += min(10.0, sector_rs_20d * 0.4)
            parts_s.append(_t("Beats sector ({chg}%)", chg=f"{sector_rs_20d:.1f}"))
        if tech_score >= 6:
            strength_score += min(10.0, tech_score * 1.2)
            parts_s.append(_t("Technical score {score}/11", score=tech_score))
        strength_score = min(100.0, strength_score)

        setup_score = 0.0
        parts_u: list[str] = []
        base_tight = False
        if base.get("valid"):
            base_tight = base["range_pct"] <= base_max_range
            if base_tight:
                setup_score += 30.0
                parts_u.append(_t("Base tight ({pct}% range)", pct=f"{base['range_pct']:.1f}"))
            # Higher Low only counts inside a TIGHT base: a penny stock moving
            # 0.005 (its whole tick) can print "higher low" while the range is
            # 54% — that is noise, not accumulation. Gate it on base_tight.
            if base.get("higher_low") and base_tight:
                setup_score += 20.0
                parts_u.append(_t("Higher Low"))
            if base.get("vol_dryup") and base_tight:
                setup_score += 20.0
                parts_u.append(_t("Volume Dry-up"))
            if base.get("atr_slope", 0) <= 0 and base_tight:
                setup_score += 10.0
                parts_u.append(_t("Volatility contraction"))
        if ext is not None and 0 < ext <= ext_pct:
            setup_score += 10.0
            parts_u.append(_t("Only {pct}% off EMA20", pct=f"{ext:.1f}"))
        setup_score = min(100.0, setup_score)

        trigger_score = 0.0
        parts_t: list[str] = []
        # EOD: today's completed close strength. Intraday: the only reliable
        # completed-day reference is YESTERDAY's CLV — today's is unfinished
        # and can swing -1→+1 minute-to-minute (#sunway case).
        clv_ref = y_clv if intraday else clv
        if clv_ref is not None and clv_ref >= 0.8:
            trigger_score += 30.0
            parts_t.append(_t("Strong close CLV={clv}", clv=f"{clv_ref:.2f}"))
        elif clv_ref is not None and clv_ref >= 0.6:
            trigger_score += 15.0
        if shake.get("detected"):
            trigger_score += 25.0
            parts_t.append(_t("Shakeout {bars}d", bars=shake["bars_ago"]))
        if fbd.get("detected"):
            # potential failed breakdown / shakeout / absorption — bullish setup
            trigger_score += 20.0
            parts_t.append(_t("Failed breakdown {bars}d", bars=fbd["bars_ago"]))
        if ema_reclaim.get("detected"):
            trigger_score += 15.0
            parts_t.append(_t(
                "EMA reclaim near EMA{slow} ({pct}%)",
                slow=60, pct=ema_reclaim.get("pullback_pct", 0.0),
            ))
        if pv is not None and pv["distance_pct"] is not None and pv["distance_pct"] <= NEAR_PIVOT_PCT:
            trigger_score += 25.0
            parts_t.append(_t("Near Pivot ({pct}%)", pct=f"{pv['distance_pct']:.1f}"))
        if effort.get("verdict") == "accumulation":
            trigger_score += 15.0
            parts_t.append(_t("Volume expansion"))
        if effort.get("verdict") == "potential_supply":
            trigger_score -= 20.0
            parts_t.append(_t("Potential Supply (high vol, no gain)"))
        if fbo.get("failed"):
            # broke above the pivot on volume but closed back below it
            trigger_score -= 20.0
            parts_t.append(_t("Failed breakout {bars}d", bars=fbo["bars_ago"]))
        trigger_score = float(np.clip(trigger_score, 0, 100))

        # ── Risk/reward from structure ───────────────────────────────────
        # ENTRY    = last close
        # STOP     = 1.5% below nearest support (invalidation)
        # TARGET   = the resistance AFTER a breakout (next confirmed pivot
        #            above the nearest pivot, or a measured-move projection).
        #            NOT the pivot itself — the pivot is the trigger, not the
        #            goal, so using it as target produced R:R ≈ 0 (the bug).
        entry = float(close.iloc[-1]) if np.isfinite(float(close.iloc[-1])) else None
        target = None
        target_kind = None
        base_low = None
        if low is not None and len(low) >= 40:
            base_low = float(low.iloc[-40:].min())
        # base-target width (measured move: how tall the base under the pivot
        # is = the projected move above it). Fallback 3% of pivot.
        base_target = None
        if base_low is not None and pv is not None:
            base_target = max(pv["price"] - base_low, pv["price"] * 0.03)
        nr = next_resistance(high, low, close, base_target=base_target,
                             max_pivots=12)
        if nr is not None:
            target = nr["price"]
            target_kind = nr.get("kind")
        stop = None
        if sup is not None:
            # conservative: 1.5% below support as invalidation
            stop = sup["price"] * 0.985
        rr = risk_reward(entry, stop, target)
        if rr.get("valid") and rr["rr"] < 1.5:
            parts_t.append(_t("R:R low ({rr})", rr=f"{rr['rr']:.1f}"))

        master = (strength_score * W_STRENGTH + setup_score * W_SETUP
                  + trigger_score * W_TRIGGER + bq["score"] * W_BREAKOUT)

        # ── R:R-aware master: "strong but bad R:R" is not a high-value buy ──
        rr_val = rr.get("rr") if rr.get("valid") else None
        rr_mult = 1.0
        if rr_val is not None:
            if rr_val < 1.0:
                rr_mult = 0.6      # risk > reward → heavily discounted
            elif rr_val < 1.5:
                rr_mult = 0.9      # borderline → lightly discounted
        master_rr = round(master * rr_mult, 1)

        reasons: list[str] = []
        if include_reasons:
            reasons = parts_s + parts_u + parts_t

        failure_type = ("failed_breakout" if fbo.get("failed")
                        else ("failed_breakdown" if fbd.get("detected") else ""))
        row: dict[str, Any] = {
            "ticker": tkr,
            "name": d.get("name", "") or ticker_names.get(tkr, ""),
            "close": round(float(close.iloc[-1]), 4),
            # legacy technical
            "score": tech_score,
            "tech_weighted": (tech_detail.get(tkr) or {}).get("weighted"),
            "tech_components": (tech_detail.get(tkr) or {}).get("components"),
            # RS block
            "rs_5d": rs_vals.get("rs_5d"),
            "rs_20d": rs_vals.get("rs_20d"),
            "rs_60d": rs_vals.get("rs_60d"),
            "rs_120d": rs_vals.get("rs_120d"),
            "rs_momentum": rs_mom,
            # RS cross-sectional rank (Leader axis)
            "rs_rank": round(rs_rank, 1) if rs_rank is not None else None,
            "rs_rank_chg20": round(rs_rank_chg20, 1) if rs_rank_chg20 is not None else None,
            "rs_rank_chg60": round(rs_rank_chg60, 1) if rs_rank_chg60 is not None else None,
            # sector
            "sector": sector,
            "sector_strength": round(sec_str, 1) if sec_str is not None else None,
            "sector_rs_20d": round(sector_rs_20d, 2) if sector_rs_20d is not None else None,
            "sector_rs_60d": round(sector_rs_60d, 2) if sector_rs_60d is not None else None,
            # closing strength + extension (intraday adds the two references)
            "clv": clv,
            "yesterday_clv": y_clv,
            "intraday_position": ipos,
            "session": session,
            "extension_pct": ext,
            # structure
            "pivot_price": pv["price"] if pv else None,
            "pivot_distance_pct": pv["distance_pct"] if pv else None,
            "support_price": sup["price"] if sup else None,
            "base_range_pct": base.get("range_pct"),
            "base_vol_dryup": base.get("vol_dryup"),
            "shakeout": shake.get("detected") or False,
            "effort_verdict": effort.get("verdict"),
            # new detectors
            "ema_reclaim": bool(ema_reclaim.get("detected")),
            "ema_pullback_pct": ema_reclaim.get("pullback_pct"),
            "failed_breakdown": bool(fbd.get("detected")),
            "failed_breakout": bool(fbo.get("failed")),
            "failure_type": failure_type,
            "market_regime": (market_regime_now or {}).get("regime"),
            # scores
            "strength_score": round(strength_score, 1),
            "setup_score": round(setup_score, 1),
            "trigger_score": round(trigger_score, 1),
            "breakout_score": bq["score"],
            "master_score": round(master, 1),
            "master_rr": master_rr,
            "rr": rr_val,
            "target_price": target,
            "target_kind": target_kind,
            # penny-stock guard annotation
            "penny_flag": penny_note,
            "tech_score_raw": tech_score + penny_penalty,
            # explainability + classification
            "classification": classify(
                strength_score, setup_score, trigger_score,
                bq, ext, pv["distance_pct"] if pv else None, base, rs_mom,
                rr=rr_val,
                rs_rank=rs_rank,
                rs_rank_chg20=rs_rank_chg20,
                ema_reclaim=ema_reclaim,
            ),
            "reasons": reasons,
        }
        if penny_note:
            reasons.append("⚠ " + penny_note)

        # Closing-Strength filter (user-adjustable; 0 = disabled).
        # INTRADAY MODE: the current bar is unfinished — a strong stock can
        # read CLV=0 at 09:30 (one print at the low) and CLV=1 at 09:45, so
        # the filter NEVER applies intraday. The filter's job is done by the
        # trigger score via yesterday_clv instead (see above).
        if intraday:
            pass  # no CLV hard filter while the market is open
        elif clv_min > 0 and (clv is None or clv < clv_min):
            continue
        if tech_score < min_score_tech:
            continue

        results.append(row)

    # Value-first: the most actionable (highest R:R-adjusted master) surfaces
    # first in the Ignition table. master_rr is always present.
    results.sort(key=lambda r: (-r["master_rr"], -r["master_score"]))
    return results[:top_n]
