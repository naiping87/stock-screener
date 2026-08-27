"""Persistent signal journal + forward-return engine (P2).

Every Phase-1 (Ignition) run records its signals with the date and the full
feature vector. As later market data arrives, backfill the forward returns
(1/3/5/10/20d) plus MFE/MAE, then `report()` aggregates per classification
bucket (and per RS / CLV band) so a score becomes a measured win-rate, not a
guess.

Storage is a plain CSV (append-only, deduped on date+ticker) so the owner can
open and audit it. Keep it under version control if you want reproducibility.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


COLUMNS = [
    "date", "market", "ticker", "name", "sector",
    "classification", "master_rr", "master_score",
    "strength_score", "setup_score", "trigger_score", "breakout_score",
    "rs_rank", "rs_rank_chg20", "clv", "rr", "score",
    "kdj_state", "kdj_k_d_golden", "market_regime",
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "mfe_5d", "mae_5d", "mfe_10d", "mae_10d",
]

HORIZONS = (1, 3, 5, 10, 20)
MFE_MAE_HORIZONS = (5, 10)


def default_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "StockScreenerPro", "signal_journal.csv")


def _naive_series(s: pd.Series) -> pd.Series:
    """Strip timezone from a Series index so naive signal dates can locate bars."""
    out = s.copy()
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    return out


class SignalJournal:
    """Append-only signal journal with forward-return backfill + edge report."""

    def __init__(self, path: str | None = None):
        self.path = path or default_path()
        if os.path.exists(self.path):
            self.df = pd.read_csv(self.path, dtype={"ticker": str})
            # tolerate older files that lack the newest columns
            for c in COLUMNS:
                if c not in self.df.columns:
                    self.df[c] = None
            self.df = self.df[COLUMNS]
        else:
            self.df = pd.DataFrame(columns=COLUMNS)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.df.to_csv(self.path, index=False)

    def record(self, rows: list[dict[str, Any]], market: str, asof) -> int:
        """Insert new signals. `asof` is the signal date (Timestamp or str)."""
        d = str(asof.date()) if hasattr(asof, "date") else str(asof)
        existing = set(zip(self.df["date"], self.df["ticker"])) if not self.df.empty else set()
        new_rows: list[dict[str, Any]] = []
        for r in rows:
            tkr = str(r.get("ticker", ""))
            if not tkr or (d, tkr) in existing:
                continue
            new_rows.append({
                "date": d, "market": market, "ticker": tkr,
                "name": r.get("name", ""), "sector": r.get("sector", ""),
                "classification": r.get("classification", ""),
                "master_rr": r.get("master_rr"),
                "master_score": r.get("master_score"),
                "strength_score": r.get("strength_score"),
                "setup_score": r.get("setup_score"),
                "trigger_score": r.get("trigger_score"),
                "breakout_score": r.get("breakout_score"),
                "rs_rank": r.get("rs_rank"), "rs_rank_chg20": r.get("rs_rank_chg20"),
                "clv": r.get("clv"), "rr": r.get("rr"), "score": r.get("score"),
                "kdj_state": r.get("kdj_state", ""),
                "kdj_k_d_golden": r.get("kdj_k_d_golden"),
                "market_regime": r.get("market_regime", ""),
                "ret_1d": None, "ret_3d": None, "ret_5d": None,
                "ret_10d": None, "ret_20d": None,
                "mfe_5d": None, "mae_5d": None, "mfe_10d": None, "mae_10d": None,
            })
        if new_rows:
            self.df = pd.concat(
                [self.df, pd.DataFrame(new_rows, columns=COLUMNS)],
                ignore_index=True,
            )
            self._save()
        return len(new_rows)

    def backfill(self, data: dict[str, dict[str, Any]]) -> int:
        """Fill forward returns for journal entries from full price data.

        `data` is {ticker: {"close": Series}} (the same shape the screener uses).
        Returns the number of rows whose forward returns were updated.
        """
        if self.df.empty:
            return 0
        filled = 0
        for i, row in self.df.iterrows():
            d = data.get(row["ticker"])
            if not isinstance(d, dict):
                continue
            s = d.get("close")
            if s is None or len(s) < 2:
                continue
            s = _naive_series(s)
            try:
                loc = s.index.searchsorted(pd.Timestamp(row["date"]), side="right") - 1
                if loc < 0 or loc >= len(s) - 1:
                    continue
            except Exception:
                continue
            base = float(s.iloc[loc])
            if not np.isfinite(base) or base <= 0:
                continue
            updates: dict[str, Any] = {}
            for h in HORIZONS:
                j = loc + h
                if j < len(s) and np.isfinite(float(s.iloc[j])):
                    updates[f"ret_{h}d"] = round((float(s.iloc[j]) / base - 1.0) * 100, 2)
            for h in MFE_MAE_HORIZONS:
                seg = s.iloc[loc + 1: loc + 1 + h].astype(float)
                if len(seg):
                    rets = seg / base - 1.0
                    updates[f"mfe_{h}d"] = round(float(rets.max()) * 100, 2)
                    updates[f"mae_{h}d"] = round(float(rets.min()) * 100, 2)
            for k, v in updates.items():
                self.df.at[i, k] = v
            filled += 1
        self._save()
        return filled

    def report(self, group_by: str = "classification", min_n: int = 1) -> pd.DataFrame:
        """Aggregate closed (forward-return-known) signals by a bucket column."""
        df = self.df[self.df["ret_5d"].notna()].copy()
        if df.empty or group_by not in df.columns:
            return pd.DataFrame()
        out = (
            df.groupby(group_by)
            .agg(
                n=("ret_5d", "size"),
                win_rate_5d=("ret_5d", lambda s: (s > 0).mean() * 100),
                avg_ret_5d=("ret_5d", "mean"),
                avg_ret_20d=("ret_20d", "mean"),
                avg_master_rr=("master_rr", "mean"),
            )
            .reset_index()
        )
        out = out[out["n"] >= min_n].sort_values("win_rate_5d", ascending=False)
        for c in ("win_rate_5d", "avg_ret_5d", "avg_ret_20d", "avg_master_rr"):
            out[c] = out[c].round(1)
        return out.reset_index(drop=True)

    def report_bands(self, min_n: int = 1) -> pd.DataFrame:
        """Concatenated edge report across classification / RS / CLV bands."""
        parts = []
        parts.append(self.report("classification", min_n))

        d = self.df[self.df["ret_5d"].notna()].copy()
        if not d.empty:
            d["rs_band"] = pd.cut(d["rs_rank"], [0, 40, 60, 80, 101],
                                  labels=["<40", "40-60", "60-80", "80+"])
            d["clv_band"] = pd.cut(d["clv"], [-0.01, 0.6, 0.8, 1.01],
                                   labels=["<0.6", "0.6-0.8", "0.8+"])
            for band in ("rs_band", "clv_band"):
                b = (
                    d.groupby(band)
                    .agg(n=("ret_5d", "size"),
                         win_rate_5d=("ret_5d", lambda s: (s > 0).mean() * 100),
                         avg_ret_5d=("ret_5d", "mean"))
                    .reset_index()
                    .rename(columns={band: "bucket"})
                )
                b["bucket"] = band + " " + b["bucket"].astype(str)
                b["win_rate_5d"] = b["win_rate_5d"].round(1)
                b["avg_ret_5d"] = b["avg_ret_5d"].round(2)
                b = b[b["n"] >= min_n]
                parts.append(b[["bucket", "n", "win_rate_5d", "avg_ret_5d"]])
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
