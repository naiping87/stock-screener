"""Background worker for running all screeners on loaded data."""

from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd

from screener import (
    run_ema_screener, run_ema_hourly_screener, run_ema_weekly_screener,
    run_divergence_screener,
    run_weekly_kdj_screener, run_daily_kdj_screener,
    run_scoring_screener,
    KDJ_PERIOD, KDJ_SIGNAL, DIVERGENCE_LOOKBACK,
    VOL_MIN, VOL_MIN_HOURLY, WEEKLY_VOL_MIN, VOL_MIN_WEEKLY_EMA, DAILY_VOL_MIN,
    EMA_PERIODS, DIVERGENCE_THRESHOLD, MIN_COMPRESSION_BARS,
    DAILY_VOL_RATIO, SCORE_TOP_N,
    SCORE_TREND_PERIODS, SCORE_TREND_THRESHOLD,
    SCORE_EMA200_SLOPE_BARS, SCORE_VOL_PERIOD, SCORE_VOL_THRESHOLD,
    SCORE_VOL_MA_BARS, SCORE_VOL_MA_THRESHOLD,
)


class ScreenerWorker(QThread):
    """Runs all screeners in a background thread and emits results as DataFrames."""

    progress = pyqtSignal(int, str)
    result = pyqtSignal(str, object)    # (tab_key, pd.DataFrame)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data, ticker_names, params, parent=None):
        super().__init__(parent)
        self.data = data
        self.ticker_names = ticker_names
        self.params = params

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

            # Screen 4: KDJ Divergence
            self.progress.emit(60, "KDJ Divergence screener...")
            r3 = list(run_divergence_screener(
                self.data, self.ticker_names,
                lookback=p.get("div_lookback", DIVERGENCE_LOOKBACK),
                min_vol=p.get("vol_daily", 200_000),
            ))
            self.result.emit("kdj_div", self._to_df(r3))

            # Screen 5: Weekly KDJ
            self.progress.emit(70, "Weekly KDJ screener...")
            r4 = list(run_weekly_kdj_screener(
                self.data, self.ticker_names,
                vol_min=p.get("vol_weekly", 500_000),
            ))
            self.result.emit("weekly_kdj", self._to_df(r4))

            # Screen 6: Daily KDJ
            self.progress.emit(80, "Daily KDJ screener...")
            r_daily = list(run_daily_kdj_screener(
                self.data, self.ticker_names,
                vol_min=p.get("vol_daily", 200_000),
                vol_ratio=p.get("daily_vol_ratio", 1.5),
            ))
            self.result.emit("daily_kdj", self._to_df(r_daily))

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
            ))
            self.result.emit("scoring", self._to_df(r5))

            self.progress.emit(100, "All screeners complete")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def _to_df(self, results: list) -> pd.DataFrame:
        if not results:
            return pd.DataFrame()
        df = pd.DataFrame(results)
        # Keep original ticker for internal lookup, add stripped Code for display
        if "ticker" in df.columns:
            df["Code"] = df["ticker"].apply(_strip_kl)
        # Rename other columns for display
        rename = {
            "name": "Name", "close": "Price",
            "kdj_signal": "Signal", "vol_ma": "Vol MA", "vol_ratio": "Vol Ratio",
            "ROE": "ROE%",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        return df


def _strip_kl(tkr):
    """Strip .KL suffix for display."""
    if isinstance(tkr, str) and tkr.endswith(".KL"):
        return tkr[:-3]
    return tkr

