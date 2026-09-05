"""Background worker for running all screeners on loaded data."""

import logging

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

from screener import (
    DIVERGENCE_LOOKBACK,
    SCORE_EMA200_SLOPE_BARS,
    SCORE_MIN,
    SCORE_TOP_N,
    SCORE_TREND_PERIODS,
    SCORE_TREND_THRESHOLD,
    SCORE_VOL_MA_BARS,
    SCORE_VOL_MA_THRESHOLD,
    SCORE_VOL_PERIOD,
    SCORE_VOL_THRESHOLD,
    run_daily_kdj_screener,
    run_divergence_screener,
    run_ema_hourly_screener,
    run_ema_screener,
    run_ema_weekly_screener,
    run_scoring_screener,
    run_weekly_kdj_screener,
)
from screener_setup import LIQ_HARD_FLOOR


class ScreenerWorker(QThread):
    """Runs all screeners in a background thread and emits results as DataFrames."""

    progress = pyqtSignal(int, str)
    result = pyqtSignal(str, object)    # (tab_key, pd.DataFrame)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, data, ticker_names, params, parent=None,
                 bench_close=None, sector_map=None, market_code="my"):
        super().__init__(parent)
        self.data = data
        self.ticker_names = ticker_names
        self.params = params
        self.bench_close = bench_close      # KLCI close series (RS reference)
        self.sector_map = sector_map or {}  # {ticker: sector} for sector strength
        self.market_code = market_code

    def cancel(self):
        """Request cancellation; checked between screeners."""
        self.requestInterruption()

    def _check_cancel(self) -> bool:
        """Return True when the run should stop (already emitted cancelled)."""
        if self.isInterruptionRequested():
            self.cancelled.emit()
            return True
        return False

    def run(self):
        try:
            p = self.params
            # Screen 1: Daily EMA
            self.progress.emit(20, "Daily EMA screener...")
            r1 = list(run_ema_screener(
                self.data, self.ticker_names,
                periods=p.get("ema_periods", [20, 50, 100, 200]),
                threshold=p.get("ema_threshold", 5.0),
                min_compression=p.get("compress_bars", 8),
                min_vol=p.get("vol_daily", 200_000),
            ))
            self.result.emit("daily_ema", self._to_df(r1))
            if self._check_cancel():
                return

            # Screen 2: Hourly EMA
            self.progress.emit(40, "Hourly EMA screener...")
            r2 = list(run_ema_hourly_screener(
                self.data, self.ticker_names,
                periods=p.get("ema_periods", [20, 50, 100, 200]),
                threshold=p.get("ema_threshold", 5.0),
                min_compression=p.get("compress_bars", 8),
                min_vol=p.get("vol_hourly", 20_000),
            ))
            self.result.emit("hourly_ema", self._to_df(r2))
            if self._check_cancel():
                return


            # Screen 3: Weekly EMA
            self.progress.emit(50, "Weekly EMA screener...")
            r_weekly_ema = list(run_ema_weekly_screener(
                self.data, self.ticker_names,
                periods=p.get("ema_periods", [20, 50, 100, 200]),
                threshold=p.get("ema_threshold", 5.0),
                min_compression=p.get("compress_bars", 8),
                min_vol=p.get("vol_weekly_ema", 500_000),
            ))
            self.result.emit("weekly_ema", self._to_df(r_weekly_ema))
            if self._check_cancel():
                return

            # Screen 4: KDJ Divergence
            self.progress.emit(60, "KDJ Divergence screener...")
            r3 = list(run_divergence_screener(
                self.data, self.ticker_names,
                lookback=p.get("div_lookback", DIVERGENCE_LOOKBACK),
                min_vol=p.get("vol_daily", 200_000),
            ))
            self.result.emit("kdj_div", self._to_df(r3))
            if self._check_cancel():
                return

            # Screen 5: Weekly KDJ
            self.progress.emit(70, "Weekly KDJ screener...")
            r4 = list(run_weekly_kdj_screener(
                self.data, self.ticker_names,
                vol_min=p.get("vol_weekly", 500_000),
            ))
            self.result.emit("weekly_kdj", self._to_df(r4))
            if self._check_cancel():
                return

            # Screen 6: Daily KDJ
            self.progress.emit(80, "Daily KDJ screener...")
            r_daily = list(run_daily_kdj_screener(
                self.data, self.ticker_names,
                vol_min=p.get("vol_daily", 200_000),
                vol_ratio=p.get("daily_vol_ratio", 1.5),
            ))
            self.result.emit("daily_kdj", self._to_df(r_daily))
            if self._check_cancel():
                return

            # Screen 7: Scoring
            self.progress.emit(90, "Scoring screener...")
            r5 = list(run_scoring_screener(
                self.data, self.ticker_names,
                trend_periods=p.get("score_trend_periods", SCORE_TREND_PERIODS),
                trend_threshold=p.get("score_trend_div", SCORE_TREND_THRESHOLD),
                ema200_slope_bars=p.get("score_slope_bars", SCORE_EMA200_SLOPE_BARS),
                vol_period=p.get("score_vol_p", SCORE_VOL_PERIOD),
                vol_threshold=p.get("score_vol_t", SCORE_VOL_THRESHOLD),
                vol_ma_bars=p.get("score_vol_ma_b", SCORE_VOL_MA_BARS),
                vol_ma_threshold=p.get("score_vol_ma_t", SCORE_VOL_MA_THRESHOLD),
                top_n=p.get("score_top_n", SCORE_TOP_N),
                min_score=p.get("score_min", SCORE_MIN),
            ))
            self.result.emit("scoring", self._to_df(r5))
            if self._check_cancel():
                return

            # Screen 8: Phase-1 pulse detector (RS / Sector / Setup / CLV)
            self.progress.emit(95, "Phase-1 pulse detector...")
            try:
                from screener_phase1 import run_phase1_screener, set_lang as p1_set_lang
                try:
                    import i18n
                    p1_set_lang(i18n.current())
                except Exception:
                    p1_set_lang("en")

                def _p1_progress(done, total):
                    # 95%→99% window for the Phase-1 step
                    self.progress.emit(95 + int(4 * done / max(1, total)),
                                       f"Ignition: {done}/{total}")

                # Session-aware screening: an UNCLOSED trading day must not
                # hard-filter on today's unstable CLV (the 09:30 CLV=0 trap).
                # eod → EOD mode (final CLV/volume, filter applies);
                # intraday → CLV filter skipped, yesterday_clv referenced.
                from market_session import session_mode
                from datetime import datetime
                from zoneinfo import ZoneInfo
                try:
                    _tz_name = "Asia/Kuala_Lumpur" if self.market_code == "my" else "America/New_York"
                    _tz = ZoneInfo(_tz_name)
                    _now = datetime.now(tz=_tz)
                    _session = session_mode(self.market_code, _now, _tz_name)
                except Exception:
                    _session = "eod"  # fallback: be conservative (final data)

                r6 = run_phase1_screener(
                    self.data,
                    getattr(self, "bench_close", None),
                    getattr(self, "sector_map", None) or {},
                    ticker_names=self.ticker_names,
                    top_n=p.get("score_top_n", SCORE_TOP_N),
                    min_score_tech=p.get("score_min", SCORE_MIN),
                    clv_min=p.get("clv_min", 0.8),
                    min_adtv=p.get("min_adtv", LIQ_HARD_FLOOR),
                    ema60_slope_up_only=bool(p.get("ema60_slope_up_only", False)),
                    progress_cb=_p1_progress,
                    session=_session,
                )
                self.progress.emit(99, f"Ignition done ({_session} mode)")
                _p1df = self._to_df(r6)
                # Top N is an UPPER bound, not a guarantee: the Min Closing
                # Strength filter (clv_min) runs first and can leave fewer rows
                # than requested. Attach a hint so the Ignition tab can explain
                # "I asked for 300 but only 200 fit the 0.8 close-strength rule".
                if 0 < len(_p1df) < p.get("score_top_n", SCORE_TOP_N) and p.get("clv_min", 0.8) > 0:
                    _p1df.attrs["filter_note"] = (
                        f"Showing {len(_p1df)} of top {p.get('score_top_n', SCORE_TOP_N)}"
                        f" — only {len(_p1df)} pass the {p.get('clv_min', 0.8):.2f}"
                        " closing-strength filter. Lower Min Closing Strength to see more."
                    )
                self.result.emit("phase1", _p1df)
                try:
                    self._write_journal(r6)
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Phase-1 detector skipped: %s", e)
                self.result.emit("phase1", pd.DataFrame())
            if self._check_cancel():
                return

            self.progress.emit(100, "All screeners complete")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def _write_journal(self, phase1_rows):
        """Append Ignition signals to the signal journal so win rates accumulate."""
        try:
            from tools.signal_journal import SignalJournal
            j = SignalJournal()
            try:
                j.backfill(self.data)
            except Exception:
                pass
            asof = None
            for d in self.data.values():
                if not isinstance(d, dict):
                    continue
                c = d.get("close")
                if c is not None and len(c):
                    t = c.index[-1]
                    if asof is None or t > asof:
                        asof = t
            if asof is not None:
                j.record(phase1_rows, getattr(self, "market_code", ""), asof)
        except Exception as e:
            logger.debug("signal journal skip: %s", e)

    def _to_df(self, results: list) -> pd.DataFrame:
        if not results:
            return pd.DataFrame()
        df = pd.DataFrame(results)
        # Keep original ticker for internal lookup, add stripped Code for display
        if "ticker" in df.columns:
            df["Code"] = df["ticker"].apply(_strip_kl)
        # Reason lists (explainability) → semicolon string for the table cell
        if "reasons" in df.columns:
            df["reasons"] = df["reasons"].apply(
                lambda v: (" · ".join(str(x) for x in v)) if isinstance(v, (list, tuple)) else str(v))
        # Compact the de-redundant 11-factor cluster breakdown for the table cell
        if "tech_components" in df.columns:
            df["tech_components"] = df["tech_components"].apply(
                lambda v: ("T:%d C:%d M:%d V:%d A:%d" % (
                    v.get("trend", 0), v.get("compression", 0), v.get("momentum", 0),
                    v.get("volume", 0), v.get("activity", 0)))
                if isinstance(v, dict) else "")
        # Rename other columns for display
        rename = {
            "name": "Name", "close": "Price",
            "kdj_signal": "Signal", "vol_ma": "Vol MA", "vol_ratio": "Vol Ratio",
            "ROE": "ROE%",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        # Ignition (phase1): friendly names + importance ordering so the most
        # decision-relevant components (Value -> Strength -> Setup -> Trigger ->
        # Breakout) sit leftmost, matching the 30/25/25/20 weighting.
        if "master_rr" in df.columns:
            p1_rename = {
                "classification": "Setup Type",
                "master_rr": "Value",
                "master_score": "Master",
                "strength_score": "Strength",
                "setup_score": "Setup",
                "trigger_score": "Trigger",
                "breakout_score": "Breakout",
                "rs_rank": "RS Rank",
                "clv": "CLV",
                "rr": "R:R",
                "score": "Score",
                "sector": "Sector",
                "liquidity_status": "Liq",
                "adtv60": "ADTV60",
                "adtv20": "ADTV20",
                "volume_ratio": "Vol Ratio",
                "participation": "Part.",
                "trend_status": "Trend",
                "ema200_dist_pct": "EMA200%",
                "ema200_slope": "EMA200 slope",
            }
            df = df.rename(columns={k: v for k, v in p1_rename.items() if k in df.columns})
            # Human-readable trend status (kept as a separate column so Setup
            # Type stays a pure structure label; Trend reports long-term context).
            if "Trend" in df.columns:
                df["Trend"] = df["Trend"].map({
                    "above_ema200": "Above EMA200",
                    "below_ema200_rising": "Below EMA200 · rising",
                    "below_ema200_weak": "Below EMA200 · weak",
                }).fillna("—")
            preferred = ["Code", "Name", "Setup Type", "Liq", "Value", "Master",
                         "Strength", "Setup", "Trigger", "Breakout", "RS Rank",
                         "CLV", "Vol Ratio", "ADTV60", "Part.", "R:R",
                         "Score", "Sector", "Price"]
            remaining = [c for c in df.columns if c not in preferred]
            df = df[preferred + remaining]
        # Price right after the stock name in EVERY result table — the single
        # most useful quick-scan field. Kept as its own numeric column (so it
        # sorts/formats/colours correctly) rather than baked into the name.
        if "Name" in df.columns and "Price" in df.columns:
            cols = list(df.columns)
            if cols.count("Price") == 1:
                cols.remove("Price")
                cols.insert(cols.index("Name") + 1, "Price")
                df = df[cols]
        return df


def _strip_kl(tkr):
    """Strip .KL suffix for display."""
    if isinstance(tkr, str) and tkr.endswith(".KL"):
        return tkr[:-3]
    return tkr

