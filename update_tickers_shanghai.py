"""Scrape Shanghai A-share tickers via AkShare — writes tickers/shanghai.csv."""
import csv
import os
import sys

try:
    import akshare as ak
except ImportError:
    print("Please install akshare: pip install akshare")
    sys.exit(1)

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickers", "shanghai.csv")

print("[INFO] Fetching Shanghai A-share stock list from AkShare ...")
try:
    df = ak.stock_info_sh_name_code()
except Exception:
    # Fallback: try another API
    df = ak.stock_sh_a_spot_em()
    df = df[["代码", "名称"]].rename(columns={"代码": "stock_code", "名称": "stock_name"})

codes = df.get("stock_code", df.iloc[:, 0])
names = df.get("stock_name", df.iloc[:, 1])

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
written = 0
with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    for code, name in zip(codes, names):
        c = str(code).strip()
        n = str(name).strip()
        if not c or not n:
            continue
        # Filter out non-standard codes (B-shares, indices)
        if not c.startswith("6") and not c.startswith("68"):
            continue
        w.writerow([c, n])
        written += 1

print(f"[INFO] Wrote {written} Shanghai A-share tickers to {OUT_PATH}")
