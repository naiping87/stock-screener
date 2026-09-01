"""Main window — menu, status bar, sidebar + results tab layout."""

import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
)

from tools.new_stock_monitor import AnnouncementBoard, normalize_code, run_once
import i18n
from markets import get as get_market
from licensing.license_manager import LicenseManager
from utils import cache_dir
from workers.alert_worker import AlertWorker
from workers.download_worker import DownloadWorker
from workers.meta_worker import MetaWorker, load_meta_cache, save_meta_cache
from workers.screener_worker import ScreenerWorker

from .results_panel import ResultsPanel
from .sidebar import Sidebar
from .system_tray import SystemTray

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Screener Pro")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)
        self.data = {}
        self.ticker_names = {}
        self._result_dfs = {}
        # Restore previously-fetched ROE/Sector so we don't refetch hundreds
        # of quoteSummary calls on every app launch, and so the Phase-1 sector
        # axis has data available on the first run after a relaunch.
        self._meta_cache = load_meta_cache()
        self._screeners_need_meta_rerun = False
        self._busy = False            # a download / screener run is in flight
        self._chart_open = False      # a modal chart dialog is currently open
        self._pending_finalize = False  # a run finished while a chart was open
        self._last_market_code = None
        self._retry_cb = None         # callback for the status-bar Retry button
        self._really_quit = False     # set by Quit (tray menu / Ctrl+Q); X button still docks to tray

        settings = QSettings("StockScreenerPro", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self._setup_menu()
        self._setup_statusbar()
        self._setup_central()
        self._setup_tray()
        self._refresh_new_picks()

    def _setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu(i18n.t("File"))

        refresh_action = QAction(i18n.t("Refresh Data"), self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self._on_refresh)
        file_menu.addAction(refresh_action)

        export_action = QAction(i18n.t("Export CSV..."), self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()
        quit_action = QAction(i18n.t("Quit"), self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self._quit_app)
        file_menu.addAction(quit_action)

        # ── Language menu（切换界面语言，重启后生效）────────────────
        lang_menu = menubar.addMenu(i18n.t("Language"))
        # QActionGroup(exclusive) — the three languages are mutually
        # exclusive; without it every action is independently checkable and
        # the user can tick two languages at once.
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        for code, label in i18n.SUPPORTED.items():
            act = QAction(label, self)
            act.setCheckable(True)
            act.setActionGroup(lang_group)
            act.setChecked(i18n.lang() == code)
            act.triggered.connect(lambda _=False, c=code: self._on_language_changed(c))
            lang_menu.addAction(act)

        help_menu = menubar.addMenu(i18n.t("Help"))
        license_action = QAction(i18n.t("License Info"), self)
        license_action.triggered.connect(self._on_license_info)
        help_menu.addAction(license_action)
        about_action = QAction(i18n.t("About"), self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _on_language_changed(self, code):
        i18n.set_lang(code)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, i18n.t("Language"),
            "Language saved. Please restart the app to apply it.\n\n"
            "Bahasa disimpan. Sila mulakan semula aplikasi untuk menggunakannya.\n\n"
            "语言已保存，请重启软件以生效。")

    def _on_license_info(self):
        """Show the current license status (trial expiry / perpetual)."""
        from PyQt6.QtWidgets import QMessageBox
        info = LicenseManager().get_license_info()
        if not info.get("activated"):
            QMessageBox.about(
                self, i18n.t("License Info"),
                "<h3>Stock Screener Pro — License</h3>"
                "<p><b>Status:</b> " + i18n.t("Not activated") + "</p>"
                "<p>This installation is not licensed yet. Please enter a valid activation code.</p>")
            return
        body = ("<h3>Stock Screener Pro — License</h3>"
                "<p><b>Status:</b> Activated</p>"
                "<p><b>%s</b> %s</p>"
                "<p>%s</p>" % (i18n.t("Type:"), info["type"], info["detail"]))
        if info.get("name"):
            body += "<p><b>" + i18n.t("Licensed to:") + "</b> %s</p>" % info["name"]
        QMessageBox.about(self, i18n.t("License Info"), body)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel(i18n.t("Ready"))
        self.statusbar.addWidget(self.status_label, 1)
        # Data-freshness indicator: last bar date + fetch time (right side).
        self.asof_label = QLabel("")
        self.asof_label.setStyleSheet("color:#9aa4b5;")
        self.statusbar.addPermanentWidget(self.asof_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.hide()
        self.statusbar.addPermanentWidget(self.progress_bar)

        # Cancel button — visible only while a worker is running
        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #f23645; border: 1px solid #f23645;"
            " border-radius: 6px; padding: 4px 14px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(242,54,69,0.12); }")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.hide()
        self.statusbar.addPermanentWidget(self.cancel_btn)

        # Retry button — visible after a failed download / screener run
        self.retry_btn = QPushButton("↻ Retry")
        self.retry_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #f7c600; border: 1px solid #f7c600;"
            " border-radius: 6px; padding: 4px 14px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(247,198,0,0.12); }")
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.hide()
        self.statusbar.addPermanentWidget(self.retry_btn)

    def _setup_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = Sidebar()
        splitter.addWidget(self.sidebar)

        self.results_panel = ResultsPanel()
        splitter.addWidget(self.results_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 960])
        self.setCentralWidget(splitter)

        self.sidebar.run_clicked.connect(self._on_run_screeners)
        self.sidebar.market_changed.connect(self._on_market_changed)
        self.sidebar.sector_combo.currentIndexChanged.connect(self._on_sector_changed)
        self.results_panel.ticker_activated.connect(self._open_chart)

        # Alert toggle — persisted across launches
        settings = QSettings("StockScreenerPro", "Alerts")
        self.sidebar.alerts_checkbox.setChecked(settings.value("enabled", True, type=bool))
        self.sidebar.alerts_checkbox.stateChanged.connect(self._on_alerts_toggled)

        # Auto-refresh timer
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._on_refresh)
        self.sidebar.auto_refresh.stateChanged.connect(self._on_auto_refresh_toggled)

    def _setup_tray(self):
        self.tray = SystemTray(self)
        self.tray.show_window.connect(self._show_from_tray)
        self.tray.quit_app.connect(self._quit_app)

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    # ── Busy state / feedback ─────────────────────────────────────────────

    def _set_busy(self, busy: bool, text: str = ""):
        """Lock the controls while a worker runs and reflect it on the Run button."""
        self._busy = busy
        self.sidebar.run_btn.setEnabled(not busy)
        self.sidebar.reset_btn.setEnabled(not busy)
        self.sidebar.market_combo.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        if busy:
            self.sidebar.run_btn.setText("⏳ Running…")
            if text:
                self.status_label.setText(text)
        else:
            self.sidebar.run_btn.setText(i18n.t("Run Screeners"))
            self._hide_error()

    def _show_error(self, msg: str, retry_cb=None):
        """Non-modal error: red status text + optional Retry button."""
        logger.error("Operation failed: %s", msg)
        self.status_label.setText("⚠ " + msg)
        self.status_label.setStyleSheet("color:#f23645;")
        self._retry_cb = retry_cb
        self.retry_btn.setVisible(retry_cb is not None)

    def _hide_error(self):
        self.status_label.setStyleSheet("")
        self._retry_cb = None
        self.retry_btn.hide()

    def _on_cancel(self):
        for w in (getattr(self, "worker", None),
                  getattr(self, "screener_worker", None),
                  getattr(self, "meta_worker", None)):
            if w is not None and w.isRunning():
                w.cancel()
                self.status_label.setText("Cancelling…")
                return
        self._set_busy(False)

    def _on_retry(self):
        cb = self._retry_cb
        self._hide_error()
        if cb:
            cb()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_run_screeners(self):
        if self._busy or self._chart_open:
            return
        if not self.data:
            params = self.sidebar.get_params()
            self._start_download(params["market_code"])
        else:
            self._start_screeners()

    def _start_download(self, market_code, force_refresh=False):
        if self._busy:
            return
        self._last_market_code = market_code
        self._set_busy(True, "Downloading " + market_code.upper() + " market data...")
        self.results_panel.set_all_empty()
        self.worker = DownloadWorker(market_code, force_refresh=force_refresh)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self._on_data_loaded)
        self.worker.error.connect(self._on_download_error)
        self.worker.cancelled.connect(self._on_worker_cancelled)
        self.worker.start()

    def _on_data_loaded(self, data, ticker_names):
        self.data = data
        self.ticker_names = ticker_names
        self._refresh_asof()
        self._populate_top_movers()
        self.status_label.setText("Loaded " + str(len(data)) + " tickers - running screeners...")
        # Internal chain: busy flag stays set, so bypass the guard.
        self._start_screeners()

    def _refresh_asof(self):
        """Show the latest bar date across the loaded universe + fetch time."""
        latest = None
        for d in self.data.values():
            if not isinstance(d, dict):
                continue
            c = d.get("close")
            if c is not None and len(c) and hasattr(c, "index"):
                t = c.index[-1]
                if latest is None or t > latest:
                    latest = t
        now = datetime.now()
        if latest is not None:
            self.asof_label.setText(
                "Data as of " + latest.strftime("%Y-%m-%d")
                + " · updated " + now.strftime("%H:%M")
            )
        else:
            self.asof_label.setText("")

    def _populate_top_movers(self):
        """Show the market's top gainers / losers / actives for the day.

        Computed instantly from the already-downloaded data (no extra network
        call), so the 🏆 Top Movers tab appears as soon as data loads.
        """
        if not self.data:
            self.results_panel.set_results("top_movers", pd.DataFrame())
            return
        market = self._last_market_code or ""
        m = get_market(market) if market else None
        rows = []
        for tkr, data in self.data.items():
            try:
                if data is None:
                    continue
                close = data["close"].dropna()
                if close.empty or len(close) < 2:
                    continue
                last = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                if prev <= 0:
                    continue
                chg = (last - prev) / prev * 100.0
                vol = 0.0
                if "volume" in data and data["volume"] is not None:
                    vol_series = data["volume"].dropna()
                    if not vol_series.empty:
                        vol = float(vol_series.iloc[-1])
                rows.append({
                    "ticker": tkr,
                    "Code": m.display_ticker(tkr) if m else tkr,
                    "Name": self.ticker_names.get(tkr, ""),
                    "Price": last,
                    "Chg%": chg,
                    "Volume": vol,
                })
            except Exception:
                continue
        if not rows:
            self.results_panel.set_results("top_movers", pd.DataFrame())
            return
        df = pd.DataFrame(rows)
        df = df.sort_values("Chg%", ascending=False).head(40).reset_index(drop=True)
        self.results_panel.set_results("top_movers", df)

    def _start_screeners(self):
        """Start the screener pipeline (busy is already set by the caller)."""
        params = self.sidebar.get_params()
        self._result_dfs = {}
        self._set_busy(True, "Running screeners...")
        self.screener_worker = ScreenerWorker(
            self.data, self.ticker_names, params,
            bench_close=self._get_benchmark(),
            sector_map=self._sector_map(),
            market_code=self._last_market_code or params.get("market_code", "my"),
        )
        self.screener_worker.progress.connect(self.update_progress)
        self.screener_worker.result.connect(self._store_result)
        self.screener_worker.finished.connect(self._on_screeners_done)
        self.screener_worker.error.connect(self._on_screener_error)
        self.screener_worker.cancelled.connect(self._on_worker_cancelled)
        self.screener_worker.start()

    def _get_benchmark(self):
        """KLCI (or market index) close series for RS calculations — cached
        per market? Fetched once per run; never throws (None degrades RS)."""
        import threading
        import time
        try:
            from screener import _build_session, _fetch_chart
            m = get_market(self._last_market_code or "") if self._last_market_code else None
            if m is None:
                return None
            if self._last_market_code == "my":
                symbol = "^KLSE"
            elif self._last_market_code == "us":
                symbol = "^GSPC"
            elif self._last_market_code == "cn":
                symbol = "000001.SS"
            else:
                return None
            sess = _build_session()
            end = int(time.time())
            start = end - 2400 * 86400
            d, _ = _fetch_chart(sess, symbol, start, end, "1d", 30)
            return d["close"].dropna() if d else None
        except Exception:
            return None

    def _sector_map(self):
        """{ticker: sector} from the meta cache (already fetched per run)."""
        out = {}
        for t, meta in self._meta_cache.items():
            if isinstance(meta, dict):
                s = meta.get("sector")
                if s:
                    out[t] = s
        # Optional Bursa-native sector override (tickers/sector_map.csv) wins
        # over Yahoo's broad GICS sector so the Ignition sector axis is aligned.
        try:
            from screener_rs import apply_sector_override
            out = apply_sector_override(out)
        except Exception:
            pass
        return out

    def _store_result(self, tab_key, df):
        self._result_dfs[tab_key] = df

    def _on_screeners_done(self):
        # Collect all unique tickers from results
        all_tickers = set()
        for df in self._result_dfs.values():
            if df is None or df.empty:
                continue
            # Need original ticker with suffix for Yahoo lookup
            col = "ticker" if "ticker" in df.columns else "Code"
            if col not in df.columns:
                continue
            for tkr in df[col]:
                all_tickers.add(tkr)

        # Filter to tickers not already cached
        new_tickers = all_tickers - set(self._meta_cache.keys())
        # Show results IMMEDIATELY — the screeners (incl. Phase-1) are done,
        # so sticking Ignition behind a meta data fetch makes the user stare
        # at an empty tab. meta fills ROE/Sector columns afterwards without
        # re-running the whole pipeline (see _on_meta_loaded).
        self._finalize_results()
        if new_tickers:
            self.meta_worker = MetaWorker(new_tickers)
            self.meta_worker.progress.connect(self.update_progress)
            self.meta_worker.finished.connect(self._on_meta_loaded)
            self.meta_worker.error.connect(
                lambda e: self._show_error("Meta data failed: " + e, self._start_screeners))
            self.meta_worker.cancelled.connect(self._on_worker_cancelled)
            self.meta_worker.start()
            self.status_label.setText(
                f"Results ready — fetching ROE/Sector for {len(new_tickers)} stocks…")

    def _on_meta_loaded(self, meta):
        self._meta_cache.update(meta)
        save_meta_cache(self._meta_cache)
        # Results are already on screen; only re-attach ROE/Sector columns.
        # Guard: if a NEW run replaced the results while meta was fetching,
        # don't stomp them — just flag the status (the next run re-attaches).
        if self._busy:
            self.status_label.setText("Meta ready (re-attached next run)")
            return
        self._finalize_results()
        self.status_label.setText("Ready")

    def _finalize_results(self):
        if getattr(self, "_chart_open", False):
            # A modal chart is up: deferring the table rebuild here stops the
            # app harness from stealing frame time from the chart (the exact
            # stutter we are fixing). Re-run on chart close (see _open_chart).
            self._pending_finalize = True
            return
        # Attach ROE + sector to each result DataFrame (in-place, fast)
        # Use the Bursa-native override (tickers/sector_map.csv) first, so
        # sectors like "Plantation" show instead of Yahoo's broad GICS label.
        try:
            from screener_rs import load_sector_override
            sector_override = load_sector_override()
        except Exception:
            sector_override = {}

        def _sec_for(t):
            raw = str(t).split(".")[0].upper()
            s = sector_override.get(raw)
            if s:
                return s
            return self._meta_cache.get(t, {}).get("sector", "")

        all_sectors = set()
        for _tab_key, df in self._result_dfs.items():
            if df is None or df.empty:
                continue
            if "ticker" in df.columns:
                tkrs = df["ticker"].values
                df["ROE"] = [self._meta_cache.get(t, {}).get("roe") for t in tkrs]
                df["ROE%"] = [f"{v:.1f}%" if v is not None else "" for v in df["ROE"]]
                df["Sector"] = [_sec_for(t) for t in tkrs]
                for s in df["Sector"]:
                    if s:
                        all_sectors.add(s)
        self.sidebar.set_sectors(list(all_sectors))
        # Show all tabs
        self._apply_sector_filter()
        # Edge Report: signal-journal win rates (accumulates as you run it)
        try:
            from tools.signal_journal import SignalJournal
            rep = SignalJournal().report_bands()
            self.results_panel.set_results("edge", rep)
        except Exception:
            self.results_panel.set_results("edge", pd.DataFrame())
        self.status_label.setText("Ready")
        self.update_progress(100, "Ready")
        self._set_busy(False)
        self._maybe_run_alerts()
        self._check_new_picks()

    def _apply_sector_filter(self):
        """Re-render the result tables under the current sector filter.

        Pure filtering — must NOT touch busy/status state, because it is also
        invoked live from the sector combo while a run is in flight.
        """
        sector = self.sidebar.sector_combo.currentData()
        for tab_key, df in self._result_dfs.items():
            if df is None or df.empty:
                self.results_panel.set_results(tab_key, df)
                continue
            if sector and "Sector" in df.columns:
                filtered = df[df["Sector"] == sector]
                self.results_panel.set_results(tab_key, filtered)
            else:
                self.results_panel.set_results(tab_key, df)

    def _on_sector_changed(self):
        self._apply_sector_filter()

    # ── Weekly KDJ alerts ─────────────────────────────────────────────────

    def _on_alerts_toggled(self, state):
        QSettings("StockScreenerPro", "Alerts").setValue("enabled", bool(state))

    def _maybe_run_alerts(self):
        """After a completed run, check for fresh weekly KDJ crosses in the
        background and notify via the system tray (never blocks the UI)."""
        if not self.sidebar.alerts_checkbox.isChecked():
            return
        if not self.data:
            return
        if getattr(self, "alert_worker", None) is not None and self.alert_worker.isRunning():
            return
        vol_min = self.sidebar.vol_weekly.row_widget.value()
        self.alert_worker = AlertWorker(self.data, self.ticker_names, vol_min=vol_min)
        self.alert_worker.finished.connect(self._on_alerts_ready)
        self.alert_worker.error.connect(self._on_alerts_error)
        self.alert_worker.start()

    def _on_alerts_ready(self, alerts):
        n = len(alerts)
        if n == 0:
            return
        logger.info("New weekly KDJ alerts: %d", n)
        if n <= 3:
            for r in alerts:
                name = r.get("name", "")
                tkr = r.get("ticker", "")
                price = r.get("close", "?")
                k, d, j = r.get("kdj_k", "?"), r.get("kdj_d", "?"), r.get("kdj_j", "?")
                self.tray.notify(f"KDJ Cross: {name}",
                                 f"{tkr} | Price: {price} | J={j} K={k} D={d} | Weekly KDJ crossed")
        else:
            self.tray.notify("🔔 Stock Screener Alerts",
                             f"{n} stocks with new weekly KDJ golden cross detected")
        self.tray.set_alert_count(n)
        self.status_label.setText(f"🔔 {n} new weekly KDJ alert{'s' if n > 1 else ''}")

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)

    def _on_alerts_error(self, msg):
        logger.warning("Alerts check failed: %s", msg)
        self.status_label.setText("⚠ Alerts check failed")

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)

    # ── New picks (🆕 第一次被选股条件选出的股票) ─────────────────────────

    def _new_picks_paths(self):
        """State + board files live next to the day-cache (APPDATA when bundled)."""
        base = cache_dir()
        return (os.path.join(base, "picks_state.json"),
                os.path.join(base, "picks_board.json"))

    def _refresh_new_picks(self):
        """Re-render the 🆕 New Picks tab from the picks board file."""
        try:
            _state_file, board_file = self._new_picks_paths()
            entries = AnnouncementBoard(board_file).as_list()
        except Exception as e:
            logger.warning("New picks board read failed: %s", e)
            entries = []
        # 只显示当前所选市场的发现板（board 是跨市场累积的，必须按市场过滤）
        market = self._last_market_code
        if not market:
            market = self.sidebar.get_params().get("market_code")
        if market:
            entries = [e for e in entries if e.get("market") == market]
        if not entries:
            self.results_panel.set_new_picks(pd.DataFrame())
            return
        # Daily summary hook: on launch, gently remind the user how many new
        # picks are on the board (once per session).
        if not getattr(self, "_daily_summary_shown", False):
            self._daily_summary_shown = True
            try:
                self.tray.notify("📌 Stock Screener Pro",
                                 f"Welcome back — {len(entries)} new pick(s) on the board today.")
            except Exception:
                pass
        rows = [{
            "ticker": e.get("ticker", ""),
            "Code": e.get("code", ""),
            "Name": e.get("name", "") or self.ticker_names.get(e.get("ticker", ""), ""),
            "Market": e.get("market", ""),
            "Matched": e.get("matched", ""),
            "First Seen": e.get("first_seen", ""),
        } for e in entries]
        self.results_panel.set_new_picks(pd.DataFrame(rows))

    def _check_new_picks(self):
        """Detect stocks that pass the current screener conditions for the
        FIRST time, and append them to the 🆕 New Picks board.

        Runs after every completed data pipeline (including the 5-minute
        auto-refresh): the "current list" is the union of this run's screener
        results, so a stock only counts when it first gets selected.
        """
        # Collect every ticker that passed any screener this run
        tab_tickers: dict[str, set[str]] = {}
        for key, df in self._result_dfs.items():
            if df is None or df.empty or "ticker" not in df.columns:
                continue
            for t in df["ticker"]:
                tab_tickers.setdefault(str(t), set()).add(key)
        if not tab_tickers:
            return
        market = self._last_market_code or self.sidebar.get_params()["market_code"]
        ticker_map = {normalize_code(t): t for t in tab_tickers
                      if normalize_code(t) is not None}
        if not ticker_map:
            return
        state_file, board_file = self._new_picks_paths()
        try:
            new, ok = run_once(lambda: set(ticker_map.keys()),
                               state_file, market=market)
        except Exception as e:
            logger.warning("New picks check failed: %s", e)
            return
        if not ok or not new:
            return
        run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entries = []
        for c in new:
            full = ticker_map.get(c, "")
            matched = ", ".join(sorted(tab_tickers.get(full, ())))
            entries.append({
                "code": c,
                "ticker": full,
                "name": self.ticker_names.get(full, ""),
                "market": market,
                "matched": matched,
                "first_seen": run_at,
            })
        AnnouncementBoard(board_file).publish(entries)
        preview = ", ".join(new[:6]) + ("…" if len(new) > 6 else "")
        self.tray.notify("🆕 New picks",
                         f"{len(new)} stock(s) selected for the first time: {preview}")
        self.status_label.setText(f"🆕 {len(new)} new pick(s)")
        logger.info("New picks for %s: %s", market, preview)

        def _reset_status():
            if not self._busy:
                self.status_label.setText("Ready")
        QTimer.singleShot(6000, _reset_status)
        self._refresh_new_picks()

    # ── Chart drill-down ──────────────────────────────────────────────────

    def _open_chart(self, ticker):
        d = self.data.get(ticker)
        name = self.ticker_names.get(ticker, "")
        if d is None:
            self.status_label.setText(f"⚠ No chart data for {ticker}")
            return
        try:
            from ui.chart_view import ChartDialog
            self._chart_open = True
            # A modal chart runs a nested event loop, so the app's background
            # harness (auto-refresh timer + any in-flight download/screener
            # finishing) would keep churning the shared GUI thread and make the
            # chart stutter / freeze. Pause auto-refresh and block new runs
            # while the chart is open; restore on close.
            timer_running = self._refresh_timer.isActive()
            if timer_running:
                self._refresh_timer.stop()
            dlg = ChartDialog(ticker, name, d, self)
            try:
                dlg.exec()
            finally:
                self._chart_open = False
                if timer_running and self.sidebar.auto_refresh.isChecked():
                    self._refresh_timer.start(300000)
                # A run finished while the chart was open; we deferred the
                # table rebuild so it didn't stutter the chart. Do it now.
                if self._pending_finalize:
                    self._pending_finalize = False
                    self._finalize_results()
        except Exception as e:
            logger.exception("Chart dialog failed for %s", ticker)
            self._chart_open = False
            self._show_error("Chart failed: " + str(e))
            if self._pending_finalize:
                self._pending_finalize = False
                self._finalize_results()

    def _on_worker_cancelled(self):
        self.status_label.setText("Cancelled")
        self.update_progress(100, "Cancelled")
        self._set_busy(False)

    def _on_screener_error(self, msg):
        self._show_error("Screener failed: " + msg, self._start_screeners)

    def _on_download_error(self, msg):
        def _retry_download():
            code = self._last_market_code or self.sidebar.get_params()["market_code"]
            self._start_download(code, force_refresh=False)
        self._show_error("Download failed: " + msg, _retry_download)

    def _on_market_changed(self, market_code):
        if self._busy or self._chart_open:
            return
        self.status_label.setText(
            "Market changed to " + market_code + " - re-downloading...")
        self.results_panel.set_all_empty()
        self._last_market_code = market_code
        self._refresh_new_picks()   # New Picks board filters to the chosen market
        self._start_download(market_code)

    def _on_refresh(self):
        if self._busy or self._chart_open:
            return
        params = self.sidebar.get_params()
        # Refresh Data / F5 / auto-refresh must always fetch fresh data,
        # never serve the day-cache.
        self._start_download(params["market_code"], force_refresh=True)

    def _on_export(self):
        key = self.results_panel.current_tab_key()
        if key and key in self.results_panel.tables:
            table = self.results_panel.tables[key]
            table._export_csv()

    def _on_auto_refresh_toggled(self, state):
        if state:
            self._refresh_timer.start(300000)  # 5 min
        else:
            self._refresh_timer.stop()

    def _on_about(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, "About Stock Screener Pro",
            "<h3>Stock Screener Pro v1.2.4</h3>"
            "<p>Multi-market stock screening terminal.</p>"
            "<p><b>Markets:</b> Bursa MY, NYSE, NASDAQ, AMEX, SSE</p>"
            "<p><b>Screeners:</b> EMA Compression (Daily/Hourly/Weekly), KDJ Cross, "
            "KDJ Divergence, Scoring</p>"
        )

    def _quit_app(self):
        """Real quit (tray Quit / File > Quit / Ctrl+Q) — not hide-to-tray."""
        self._really_quit = True
        self.tray.hide_icon()
        self.close()

    def closeEvent(self, event):
        settings = QSettings("StockScreenerPro", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        if self._really_quit:
            # Quit was explicitly requested → actually close the app
            event.accept()
            QApplication.quit()
            return
        # X button / window close → minimize to tray instead of closing
        event.ignore()
        self.hide()

    def update_progress(self, value, text=""):
        if value >= 100:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setValue(value)
        if text:
            self.status_label.setText(text)
