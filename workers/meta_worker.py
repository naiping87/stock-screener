"""Background worker for fetching ROE + Sector + Industry from Yahoo Finance."""

from PyQt6.QtCore import QThread, pyqtSignal
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


YAHOO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MODULES = "financialData,assetProfile"


def _fetch_one(tkr, crumb, cookies):
    """Fetch ROE + sector + industry for one ticker using shared crumb."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": YAHOO_UA})
    for name, value in (cookies or {}).items():
        sess.cookies.set(name, value)

    try:
        r = sess.get(
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{tkr}",
            params={"modules": MODULES, "crumb": crumb},
            timeout=10,
        )
        if r.status_code == 200:
            j = r.json()
            result = j.get("quoteSummary", {}).get("result", [{}])[0]

            # ROE
            fd = result.get("financialData", {})
            roe_raw = fd.get("returnOnEquity", {})
            roe = round(roe_raw["raw"] * 100, 2) if isinstance(roe_raw, dict) and roe_raw.get("raw") is not None else None

            # Sector + Industry
            ap = result.get("assetProfile", {})
            sector = ap.get("sector") if isinstance(ap.get("sector"), str) else ""
            industry = ap.get("industry") if isinstance(ap.get("industry"), str) else ""

            return {"roe": roe, "sector": sector, "industry": industry}
    except Exception:
        pass
    return None


def _fetch_one_fallback(tkr):
    """Fallback: own session + crumb for one ticker."""
    sess = requests.Session()
    sess.headers.update({"User-Agent": YAHOO_UA})
    try:
        sess.get("https://fc.yahoo.com/", timeout=10)
        cr = sess.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if cr.status_code != 200:
            return None
        crumb = cr.text.strip()
        return _fetch_one(tkr, crumb, sess.cookies.get_dict())
    except Exception:
        return None


def fetch_meta_batch(tickers, workers=6):
    """Fetch ROE + sector + industry for a set of tickers. Returns {tkr: {roe, sector, industry}}."""
    if not tickers:
        return {}

    # Get shared crumb
    master = requests.Session()
    master.headers.update({"User-Agent": YAHOO_UA})
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

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        if crumb:
            futs = {pool.submit(_fetch_one, tkr, crumb, cookies): tkr for tkr in tickers}
        else:
            futs = {pool.submit(_fetch_one_fallback, tkr): tkr for tkr in tickers}

        for f in as_completed(futs):
            tkr = futs[f]
            try:
                meta = f.result()
                if meta is not None:
                    results[tkr] = meta
            except Exception:
                pass

    return results


class MetaWorker(QThread):
    """QThread wrapper for fetch_meta_batch."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, tickers, parent=None):
        super().__init__(parent)
        self.tickers = list(tickers)

    def run(self):
        try:
            self.progress.emit(90, f"Fetching ROE + sector for {len(self.tickers)} stocks...")
            meta = fetch_meta_batch(self.tickers)
            self.progress.emit(100, f"Loaded meta for {len(meta)} stocks")
            self.finished.emit(meta)
        except Exception as e:
            self.error.emit(str(e))
