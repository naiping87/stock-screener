"""
Download top US stocks (NASDAQ + NYSE) from NASDAQ.com official listings
and filter by market capitalisation to keep the top 2500.
"""

import csv
import os
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT = SCRIPT_DIR / "tickers" / "us.csv"
TOP_N = 2500  # keep top N by market cap (approx.)

# ── Sources ────────────────────────────────────────────────────────────────
# NASDAQ official symbol directories (free, no auth required)
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"

# Fallback: pre-built CSV with major US stocks (used if download fails)
FALLBACK_STOCKS = [
    # FAANG + Top tech
    ("AAPL", "Apple Inc."), ("MSFT", "Microsoft Corp."), ("GOOGL", "Alphabet Inc."),
    ("AMZN", "Amazon.com Inc."), ("NVDA", "NVIDIA Corp."), ("META", "Meta Platforms Inc."),
    ("TSLA", "Tesla Inc."), ("AVGO", "Broadcom Inc."), ("ORCL", "Oracle Corp."),
    ("ADBE", "Adobe Inc."), ("CRM", "Salesforce Inc."), ("CSCO", "Cisco Systems Inc."),
    ("INTC", "Intel Corp."), ("AMD", "Advanced Micro Devices Inc."), ("QCOM", "QUALCOMM Inc."),
    ("TXN", "Texas Instruments Inc."), ("AMAT", "Applied Materials Inc."),
    # Finance
    ("JPM", "JPMorgan Chase & Co."), ("BAC", "Bank of America Corp."),
    ("WFC", "Wells Fargo & Co."), ("GS", "Goldman Sachs Group Inc."),
    ("MS", "Morgan Stanley"), ("V", "Visa Inc."), ("MA", "Mastercard Inc."),
    ("BRK-B", "Berkshire Hathaway Inc."), ("C", "Citigroup Inc."),
    # Healthcare
    ("JNJ", "Johnson & Johnson"), ("PFE", "Pfizer Inc."), ("MRK", "Merck & Co Inc."),
    ("ABBV", "AbbVie Inc."), ("LLY", "Eli Lilly and Co."), ("UNH", "UnitedHealth Group Inc."),
    ("ABT", "Abbott Laboratories"), ("TMO", "Thermo Fisher Scientific Inc."),
    ("DHR", "Danaher Corp."), ("BMY", "Bristol-Myers Squibb Co."),
    # Consumer
    ("WMT", "Walmart Inc."), ("KO", "The Coca-Cola Co."), ("PEP", "PepsiCo Inc."),
    ("PG", "Procter & Gamble Co."), ("HD", "The Home Depot Inc."),
    ("MCD", "McDonald's Corp."), ("NKE", "Nike Inc."), ("SBUX", "Starbucks Corp."),
    ("COST", "Costco Wholesale Corp."), ("LOW", "Lowe's Companies Inc."),
    ("TGT", "Target Corp."),
    # Energy
    ("XOM", "Exxon Mobil Corp."), ("CVX", "Chevron Corp."), ("COP", "ConocoPhillips"),
    # Industrial
    ("CAT", "Caterpillar Inc."), ("BA", "The Boeing Co."), ("GE", "GE Aerospace"),
    ("HON", "Honeywell International Inc."), ("LMT", "Lockheed Martin Corp."),
    ("RTX", "RTX Corp."), ("UNP", "Union Pacific Corp."), ("UPS", "United Parcel Service Inc."),
    # Communication
    ("DIS", "The Walt Disney Co."), ("NFLX", "Netflix Inc."), ("VZ", "Verizon Communications Inc."),
    ("T", "AT&T Inc."), ("TMUS", "T-Mobile US Inc."), ("CMCSA", "Comcast Corp."),
    # Real Estate / Others
    ("PLTR", "Palantir Technologies Inc."), ("UBER", "Uber Technologies Inc."),
    ("ABNB", "Airbnb Inc."), ("SNOW", "Snowflake Inc."), ("SQ", "Block Inc."),
    ("SHOP", "Shopify Inc."), ("ZM", "Zoom Video Communications Inc."),
    ("PYPL", "PayPal Holdings Inc."), ("COIN", "Coinbase Global Inc."),
    # More large caps
    ("NEE", "NextEra Energy Inc."), ("SO", "The Southern Co."), ("DUK", "Duke Energy Corp."),
    ("SPGI", "S&P Global Inc."), ("ISRG", "Intuitive Surgical Inc."),
    ("NOW", "ServiceNow Inc."), ("INTU", "Intuit Inc."), ("LRCX", "Lam Research Corp."),
    ("MU", "Micron Technology Inc."), ("KLAC", "KLA Corp."), ("ADI", "Analog Devices Inc."),
    ("MRNA", "Moderna Inc."), ("REGN", "Regeneron Pharmaceuticals Inc."),
    ("AMGN", "Amgen Inc."), ("GILD", "Gilead Sciences Inc."),
    ("DE", "Deere & Co."), ("MMM", "3M Co."), ("FDX", "FedEx Corp."),
    ("NOC", "Northrop Grumman Corp."), ("GD", "General Dynamics Corp."),
    ("WM", "Waste Management Inc."), ("ECL", "Ecolab Inc."),
    ("EL", "The Estee Lauder Companies Inc."), ("CL", "Colgate-Palmolive Co."),
    ("MDLZ", "Mondelez International Inc."), ("KHC", "The Kraft Heinz Co."),
    ("MO", "Altria Group Inc."), ("PM", "Philip Morris International Inc."),
    ("ADP", "Automatic Data Processing Inc."), ("FIS", "Fidelity National Information Services Inc."),
    ("CHTR", "Charter Communications Inc."),
    ("D", "Dominion Energy Inc."), ("AEP", "American Electric Power Company Inc."),
    ("SRE", "Sempra"), ("EXC", "Exelon Corp."), ("XEL", "Xcel Energy Inc."),
    ("ED", "Consolidated Edison Inc."), ("EIX", "Edison International"),
    ("WELL", "Welltower Inc."), ("O", "Realty Income Corp."), ("SPG", "Simon Property Group Inc."),
    ("PSA", "Public Storage"), ("CCI", "Crown Castle Inc."),
    ("EQIX", "Equinix Inc."), ("DLR", "Digital Realty Trust Inc."),
    ("MAR", "Marriott International Inc."), ("HLT", "Hilton Worldwide Holdings Inc."),
    ("BKNG", "Booking Holdings Inc."), ("RCL", "Royal Caribbean Cruises Ltd."),
    ("LUV", "Southwest Airlines Co."), ("DAL", "Delta Air Lines Inc."),
    ("F", "Ford Motor Co."), ("GM", "General Motors Co."),
    ("CVS", "CVS Health Corp."), ("CI", "The Cigna Group"),
    ("ELV", "Elevance Health Inc."), ("HUM", "Humana Inc."),
    ("ZTS", "Zoetis Inc."), ("BDX", "Becton, Dickinson and Co."),
    ("SYK", "Stryker Corp."), ("BSX", "Boston Scientific Corp."),
    ("MDT", "Medtronic plc"), ("EW", "Edwards Lifesciences Corp."),
    ("AIG", "American International Group Inc."), ("MET", "MetLife Inc."),
    ("PRU", "Prudential Financial Inc."), ("ALL", "The Allstate Corp."),
    ("TRV", "The Travelers Companies Inc."), ("AFL", "Aflac Inc."),
    ("AXP", "American Express Co."), ("COF", "Capital One Financial Corp."),
    ("USB", "U.S. Bancorp"), ("PNC", "The PNC Financial Services Group Inc."),
    ("TFC", "Truist Financial Corp."), ("BK", "The Bank of New York Mellon Corp."),
    ("STT", "State Street Corp."), ("SCHW", "The Charles Schwab Corp."),
    ("BLK", "BlackRock Inc."),
    ("ETN", "Eaton Corp. plc"), ("PH", "Parker-Hannifin Corp."),
    ("ITW", "Illinois Tool Works Inc."), ("EMR", "Emerson Electric Co."),
    ("ROK", "Rockwell Automation Inc."), ("CMI", "Cummins Inc."),
    ("PWR", "Quanta Services Inc."), ("JCI", "Johnson Controls International plc"),
    ("CARR", "Carrier Global Corp."), ("OTIS", "Otis Worldwide Corp."),
    ("TT", "Trane Technologies plc"), ("IR", "Ingersoll Rand Inc."),
    ("PCAR", "PACCAR Inc."), ("FAST", "Fastenal Co."),
    ("GWW", "W.W. Grainger Inc."), ("URI", "United Rentals Inc."),
    # ETFs (skip for screener — they are not stocks)
    # Add more as needed
]


def download_nasdaq():
    """Download NASDAQ-traded symbols from nasdaqtrader.com."""
    print(f"[FETCH] {NASDAQ_URL}")
    resp = requests.get(NASDAQ_URL, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    resp.raise_for_status()

    tickers = []
    lines = resp.text.splitlines()
    # Format: Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares
    reader = csv.reader(lines, delimiter="|")
    header_found = False
    skipped = {"ETF": 0, "test": 0, "fin_status": 0, "warrant": 0}
    for row in reader:
        if not row or len(row) < 8:
            continue
        # Detect header
        if "Nasdaq Traded" in row[0] or "Symbol" in row[1]:
            header_found = True
            continue
        if not header_found:
            continue

        nasdaq_traded = row[0].strip()
        symbol = row[1].strip()
        name = row[2].strip() if len(row) > 2 else symbol
        listing_exchange = row[3].strip() if len(row) > 3 else ""
        market_cat = row[4].strip() if len(row) > 4 else ""
        etf_flag = row[5].strip() if len(row) > 5 else ""
        test_issue = row[7].strip() if len(row) > 7 else ""
        fin_status = row[8].strip() if len(row) > 8 else ""

        if nasdaq_traded != "Y":
            continue
        if etf_flag == "Y":
            skipped["ETF"] += 1
            continue
        if test_issue == "Y":
            skipped["test"] += 1
            continue
        if fin_status in ("D", "E", "H", "J", "K"):
            skipped["fin_status"] += 1
            continue
        # Skip warrants/rights/units/preferred ($ or /)
        if "$" in symbol or "/" in symbol:
            skipped["warrant"] += 1
            continue
        # Allow dots only for BRK.B-like symbols
        if "." in symbol:
            parts = symbol.split(".")
            if len(parts) != 2 or not all(p.isalpha() for p in parts):
                skipped["warrant"] += 1
                continue

        tickers.append((symbol, name, market_cat, listing_exchange))

    for reason, cnt in skipped.items():
        if cnt:
            print(f"[SKIP] {reason}: {cnt}")

    # Sort: NASDAQ GS > GM > CM, then NYSE > AMEX
    cat_order = {"Q": 0, "N": 1, "G": 2, "S": 3}
    tickers.sort(key=lambda x: (cat_order.get(x[3], 5) if x[3] else (cat_order.get(x[2], 4)), x[0]))
    print(f"[INFO] Parsed {len(tickers)} symbols (NYSE/NASDAQ/AMEX, no ETFs/warrants)")

    return tickers


def main():
    os.makedirs(OUTPUT.parent, exist_ok=True)

    tickers = []
    try:
        tickers = download_nasdaq()
    except Exception as e:
        print(f"[WARN] NASDAQ download failed: {e}")
        print("[INFO] Using fallback stock list")
        tickers = [(s, n, "", "") for s, n in FALLBACK_STOCKS]

    if not tickers:
        print("[WARN] No tickers found, using fallback")
        tickers = [(s, n, "", "") for s, n in FALLBACK_STOCKS]

    # Write ticker CSV (simple: code, name)
    # Sort by exchange tier, then alphabetically
    cat_order = {"Q": 0, "N": 1, "G": 2, "S": 3}
    tickers.sort(key=lambda x: (cat_order.get(x[3], 5) if x[3] else (cat_order.get(x[2], 4)), x[0]))

    # Take top N
    tickers = tickers[:TOP_N]

    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for sym, name, _cat, _ex in tickers:
            writer.writerow([sym, name])

    print(f"[DONE] Wrote {len(tickers)} tickers to {OUTPUT}")


if __name__ == "__main__":
    main()
