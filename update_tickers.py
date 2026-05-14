"""
Fetch the latest Bursa Malaysia stock list from bestar-my.com
and write tickers.csv. Run this periodically to keep the list fresh.
"""
import csv
import os
import re
import sys

import requests

URL = "https://www.bestar-my.com/post/list-of-public-listed-companies-bursa-malaysia"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TICKERS_FILE = os.path.join(SCRIPT_DIR, "tickers.csv")

# Patterns for extracting stock entries.
# Format in the page text:  INDEX  COMPANY_NAME  STOCK_CODE  TEAM_DIGIT
_STOCK_RE = re.compile(
    r"\b(\d+)\s+"
    r"([A-Z][A-Z\s&.,\-()\/'0-9]+?)\s+"
    r"(\d{4,5})\s+"
    r"(\d)\b"
)

# Known false positives to exclude (non-stock entries that match the pattern).
_SKIP_CODES = {
    "0000", "9999",  # sentinel / test codes
}


def _extract_stocks(html):
    """Return {code: name} dict parsed from the page HTML."""
    # Strip tags, collapse whitespace
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)

    stocks = {}
    for _, name, code, _ in _STOCK_RE.findall(text):
        code = code.strip()
        name = name.strip()
        if code in _SKIP_CODES:
            continue
        if not code.isdigit():
            continue
        if len(name) < 5:
            continue
        # Deduplicate — keep first occurrence
        if code not in stocks:
            stocks[code] = name
    return stocks


def main():
    print(f"[FETCH] {URL}")
    resp = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=60,
    )
    resp.raise_for_status()

    stocks = _extract_stocks(resp.text)
    if len(stocks) < 800:
        print(f"[ERROR] Only extracted {len(stocks)} stocks — something went wrong.")
        print("        The source page may have changed format.")
        sys.exit(1)

    # Write tickers.csv  (code, name)
    with open(TICKERS_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for code in sorted(stocks.keys()):
            w.writerow([code, stocks[code]])

    print(f"[OK] Wrote {len(stocks)} tickers to {TICKERS_FILE}")


if __name__ == "__main__":
    main()
