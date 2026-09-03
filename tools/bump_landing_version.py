"""Bump landing-page version refs v1.2.5 -> v1.2.6 and refresh 'What's new' copy."""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "..", "vercel-license-generator")
OLD = "v1.2.5"
NEW = "v1.2.6"


def replace(path):
    with io.open(path, encoding="utf-8") as f:
        txt = f.read()
    n = txt.count(OLD)
    txt = txt.replace(OLD, NEW)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    return n


for name in ("index.html", "download.html"):
    p = os.path.join(WEB, name)
    if os.path.exists(p):
        print(f"{name}: bumped {replace(p)} refs")


# Replace the three single-line a4 "What's new" bodies.
idx = os.path.join(WEB, "index.html")
if os.path.exists(idx):
    with io.open(idx, encoding="utf-8") as f:
        txt = f.read()

    en_a4 = (
        'a4:"Full Bursa official sector map (plantations fixed), a Price column '
        'right after the stock Name in every result table, EOD close backfill, '
        'and the ADTV liquidity layer.",'
    )
    ms_a4 = (
        'a4:"Peta sektor rasmi Bursa yang lengkap (sawit dibetulkan), lajur Harga '
        'selepas Nama saham dalam setiap jadual, isian semula tutup EOD, dan '
        'lapisan kecairan ADTV.",'
    )
    zh_a4 = (
        'a4:"完整的 Bursa 官方板块地图（种植股已修正）、每张结果表中股票名称后的价格列、'
        'EOD 收盘价回填，以及 ADTV 流动性层。",'
    )

    pairs = [
        (
            'a4:"Phase-1 Ignition v2 (Bursa sector map + session-aware CLV), '
            'a Signal Journal with an Edge Report tab, KDJ 26/5 standardisation, '
            'chart crosshair with D/W hotkeys, and column explanations on hover.",',
            en_a4,
        ),
        (
            'a4:"Ignition v2 Fasa-1 (peta sektor Bursa + CLV sedar-sesi), '
            'Jurnal Isyarat dengan tab Edge Report, standard KDJ 26/5, '
            'crosshair carta dengan pintasan D/W, dan penjelasan lajur pada hover.",',
            ms_a4,
        ),
        (
            'a4:"Phase-1 Ignition v2（Bursa 板块地图 + 时段感知 CLV）、带 Edge Report '
            '标签页的信号日志、KDJ 26/5 标准化、带 D/W 快捷键的图表十字光标、悬停列说明。",',
            zh_a4,
        ),
    ]

    replaced = 0
    for old, new in pairs:
        if old in txt:
            txt = txt.replace(old, new)
            replaced += 1

    with io.open(idx, "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    print(f"index.html: replaced {replaced}/3 'What's new' copy blocks")

    if replaced < 3:
        # Fallback: show context so we can inspect.
        for i, line in enumerate(txt.split("\n")):
            if 'a4:"' in line:
                print(f"   L{i}: {line[:200]}")
