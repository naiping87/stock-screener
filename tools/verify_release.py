"""
Release consistency check — run AFTER every publish/update.

Verifies the THREE places a buyer can download from all point at the SAME,
latest installer:
  1) Landing page (index.html) and download page (download.html) link version
  2) GitHub release asset for that version (size must match)
  3) Local installer file size (must match the release asset)

Exit code 0 = consistent. Any mismatch exits 1 with a clear message, so a
release that forgets to bump the pages fails loudly instead of shipping an
old download link.

Run:  python tools/verify_release.py [--version v1.2.2]
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_PAGES = [
    os.path.join(ROOT, "..", "vercel-license-generator", "index.html"),
    os.path.join(ROOT, "..", "vercel-license-generator", "download.html"),
]
LOCAL_INSTALLER = os.path.join(ROOT, "installer", "StockScreenerPro_Setup.exe")
REPO = "naiping87/stock-screener"
URL_RE = re.compile(
    r"https://github\.com/" + REPO + r"/releases/download/(v[\d.]+)/"
    r"StockScreenerPro_Setup\.exe")


def find_web_versions() -> list[str]:
    versions: list[str] = []
    for p in WEB_PAGES:
        if not os.path.exists(p):
            print(f"  !! missing page: {p}")
            continue
        with open(p, encoding="utf-8") as f:
            hits = URL_RE.findall(f.read())
        versions.extend(hits)
        print(f"  {os.path.basename(p)}: {hits}")
    return versions


def remote_asset_size(version: str) -> int | None:
    url = f"https://github.com/{REPO}/releases/download/{version}/StockScreenerPro_Setup.exe"
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as r:
            size = r.headers.get("Content-Length")
            return int(size) if size else None
    except Exception as e:
        print(f"  !! HEAD {url}: {e}")
        return None


def main() -> int:
    version_arg = None
    if len(sys.argv) > 2 and sys.argv[1] == "--version":
        version_arg = sys.argv[2]

    print("== 1) Web page download links ==")
    web_versions = find_web_versions()
    if not web_versions:
        print("  FAIL: no download link found on the web pages")
        return 1
    # All pages must agree on ONE version
    if len(set(web_versions)) != 1:
        print(f"  FAIL: pages disagree: {sorted(set(web_versions))}")
        return 1
    target = version_arg or web_versions[0]
    print(f"  -> pages agree on {target}")

    print("== 2) Remote release asset ==")
    remote_size = remote_asset_size(target)
    if remote_size is None:
        print(f"  FAIL: cannot fetch release asset for {target}")
        return 1
    print(f"  -> {target}: remote asset {remote_size:,} bytes")

    print("== 3) Local installer file ==")
    if not os.path.exists(LOCAL_INSTALLER):
        print(f"  FAIL: no local installer at {LOCAL_INSTALLER}")
        return 1
    local_size = os.path.getsize(LOCAL_INSTALLER)
    print(f"  -> local installer {local_size:,} bytes")

    if local_size != remote_size:
        print(f"  FAIL: local ({local_size:,}) != remote ({remote_size:,}) — "
              f"the release asset is NOT the installer you just built. "
              f"Run: gh release upload {target} \"installer\\StockScreenerPro_Setup.exe\" --clobber")
        return 1

    print(f"\nOK: web={target}, remote={remote_size:,}B, local={local_size:,}B — "
          f"buyers get the latest build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
