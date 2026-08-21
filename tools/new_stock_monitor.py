#!/usr/bin/env python3
"""
new_stock_monitor.py — 新股票出现自动提示监视器（独立 CLI + 可复用库）

用法（独立运行）:
    python tools/new_stock_monitor.py --source tickers.csv --interval 300
    python tools/new_stock_monitor.py --source https://example.com/list.json --once
    python tools/new_stock_monitor.py --source 列表.xlsx --interval 300 --show-board

被桌面版/网页版复用:
    from tools.new_stock_monitor import normalize_code, AnnouncementBoard, run_once

状态文件:
    seen_state.json      — {market: {"ever_seen": [...], "last_seen": [...]}}
    announcements.json   — {"entries": [{"code", "market", "first_seen", ...}]} 持续累积
"""

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("new_stock_monitor")

# ── 默认配置（命令行参数可覆盖）────────────────────────────────────────────
SUFFIXES_TO_STRIP = (".KL", ".SS", ".HK", ".T", ".L", ".PA", ".DE", ".N", ".O")
PREFIX_RE = re.compile(r"^(SH|SZ|NASDAQ:|NYSE:|AMEX:|XSHG|XSHE|SSE:|BJ:)?", re.IGNORECASE)
ALERT_ON_FIRST_RUN = False   # True=首次运行全部视为新股票; False=首次只建基准不提示
REALERT_ON_REAPPEAR = False  # True=移除后重现再次提示; False=出现过就永不再提示
DEFAULT_INTERVAL = 300       # 秒

STATE_FILE = "seen_state.json"
BOARD_FILE = "announcements.json"


# ── 归一化：统一代码格式 ───────────────────────────────────────────────────
def normalize_code(raw) -> str | None:
    """去空格/转大写/去统一后缀/去交易所前缀。Excel 数字型代码(600000.0)也处理。"""
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    s = str(raw).strip().upper()
    if not s:
        return None
    for suf in SUFFIXES_TO_STRIP:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    s = PREFIX_RE.sub("", s)
    return s or None


# ── 数据源读取：txt / csv / json / url / excel ────────────────────────────
def fetch_stock_list(source: str) -> set[str]:
    """返回归一化后的股票代码集合。"""
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        raw_rows = _parse_text(body)
    elif source.lower().endswith((".xlsx", ".xls")):
        raw_rows = _read_excel(source)
    elif source.lower().endswith(".json"):
        with open(source, encoding="utf-8") as f:
            raw_rows = _extract_json_rows(json.load(f))
    else:  # .csv / .txt
        with open(source, encoding="utf-8", errors="replace") as f:
            raw_rows = _parse_text(f.read())

    codes = {c for c in (normalize_code(r) for r in raw_rows) if c}
    logger.info("fetched %d raw rows -> %d unique codes", len(raw_rows), len(codes))
    return codes


def _parse_text(text: str) -> list:
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return []
    sample = lines[0]
    delim = "," if "," in sample else ("\t" if "\t" in sample else None)
    if delim is None:
        # 纯文本：每行一个代码；若首行是表头（code/symbol/代码…）则跳过
        head_kw = ("code", "ticker", "symbol", "代码", "股票代码", "证券代码")
        if any(k in lines[0].lower() for k in head_kw):
            lines = lines[1:]
        return lines
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    header = [h.strip().lower() for h in rows[0]]
    keywords = ("code", "ticker", "symbol", "代码", "股票代码", "证券代码")
    idx = next((i for i, h in enumerate(header) if any(k in h for k in keywords)), 0)
    start = 1 if any(any(k in h for k in keywords) for h in header) else 0
    return [row[idx] for row in rows[start:] if len(row) > idx]


def _extract_json_rows(data) -> list:
    if isinstance(data, list):
        out = []
        for item in data:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(_pick_code_value(item))
        return out
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and any(t in k.lower() for t in ("code", "ticker", "list")):
                return _extract_json_rows(v)
        for v in data.values():
            if isinstance(v, list):
                return _extract_json_rows(v)
    return []


def _pick_code_value(item: dict) -> str:
    for k, v in item.items():
        kl = k.lower()
        if any(t in kl for t in ("code", "ticker", "symbol", "secid")):
            return v if isinstance(v, str) else str(v)
    return str(next(iter(item.values())))


def _read_excel(path: str) -> list:
    try:
        import pandas as pd
    except ImportError:
        logger.error("读取 Excel 需要 pandas：pip install pandas openpyxl")
        return []
    df = pd.read_excel(path)
    for col in df.columns:
        if any(k in str(col).lower() for k in ("code", "ticker", "symbol", "代码")):
            return df[col].tolist()
    return df.iloc[:, 0].tolist()


# ── 状态持久化（原子写，防中断损坏）───────────────────────────────────────
def load_json(path: str, default: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def save_json(path: str, data: dict) -> None:
    path = os.fspath(path)  # 兼容 Path / str
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── 公告栏：内存 + 文件累积 ───────────────────────────────────────────────
class AnnouncementBoard:
    """持续累积所有新股票；文件保存完整历史，内存只留最近 N 条。"""

    def __init__(self, board_file: str, max_entries: int = 1000):
        self.board_file = Path(board_file)
        self.entries = deque(
            load_json(board_file, {}).get("entries", [])[-max_entries:],
            maxlen=max_entries,
        )

    def publish(self, entries: list[dict]) -> None:
        """entries: [{"code": "...", "market": "...", "first_seen": "...", ...}]"""
        for e in entries:
            if isinstance(e, dict) and e.get("code"):
                self.entries.append(e)
        self._persist()

    def _persist(self) -> None:
        save_json(self.board_file, {"entries": list(self.entries)})

    def as_list(self) -> list[dict]:
        return list(self.entries)

    def render(self, limit: int | None = None) -> str:
        items = list(self.entries)
        if limit:
            items = items[-limit:]
        lines = [f"── 公告栏 · 累计 {len(self.entries)} 只新股票 ──"]
        lines += [f"  [{e['first_seen']}] {e['code']}  (来源: {e.get('market', '-')})" for e in items]
        return "\n".join(lines)


# ── 核心：一轮对比 + 去重（返回新代码，不负责公告栏写入）──────────────────
def run_once(fetcher, state_path: str, *, market: str = "",
             alert_on_first_run: bool = ALERT_ON_FIRST_RUN,
             realert_on_reappear: bool = REALERT_ON_REAPPEAR) -> tuple[list[str], bool]:
    """执行一轮：拉取 → 对比 → 更新状态 → 返回 (新增代码列表, 是否成功)。

    - 首次运行：默认只建基准不提示（alert_on_first_run=True 则全部视为新）
    - 刷新失败/空数据：本轮跳过，状态不动，返回 ([] , False)
    - 已提示过的不可能重复（ever_seen 只增不减）；realert_on_reappear=True
      时改为对比上一轮，移除后重现的股票会再次返回
    """
    state = load_json(state_path, {})
    bucket = state.get(market, {}) if market else state
    ever_seen = set(bucket.get("ever_seen", []))
    last_seen = set(bucket.get("last_seen", []))

    try:
        current = fetcher()
    except Exception as e:
        logger.error("刷新失败，本轮跳过: %s", e)
        return [], False

    if not current:
        logger.warning("数据源返回空列表——本轮跳过，历史保留，等待下轮")
        return [], False

    if not ever_seen and not last_seen:
        # ── 首次运行 ──
        new = sorted(current) if alert_on_first_run else []
        logger.info("首次运行(%s)：%s %d 只",
                    market or "-", "全部视为新股票" if alert_on_first_run else "建立基准不提示", len(current))
    elif realert_on_reappear:
        new = sorted(current - last_seen)   # 只对比上一轮
    else:
        new = sorted(current - ever_seen)   # 对比全部历史（默认，永不复述）

    ever_seen |= current
    bucket["ever_seen"] = sorted(ever_seen)
    bucket["last_seen"] = sorted(current)
    if market:
        state[market] = bucket
    else:
        state = bucket
    save_json(state_path, state)
    return new, True


# ── CLI ───────────────────────────────────────────────────────────────────
def build_parser():
    p = argparse.ArgumentParser(description="新股票自动提示监视器")
    p.add_argument("--source", required=True, help="数据源：CSV/TXT/JSON/Excel 路径或 http(s) URL")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="刷新间隔（秒），默认 300")
    p.add_argument("--state-file", default=STATE_FILE)
    p.add_argument("--board-file", default=BOARD_FILE)
    p.add_argument("--board-limit", type=int, default=50, help="公告栏显示条数上限")
    p.add_argument("--market", default="", help="市场标识（用于多市场状态隔离），如 my/us/sh")
    p.add_argument("--once", action="store_true", help="只跑一轮后退出（适合计划任务）")
    p.add_argument("--show-board", action="store_true", help="每轮刷新后打印公告栏全量")
    p.add_argument("--alert-on-first-run", action="store_true",
                   help="首次运行把全部股票视为新股票（默认只建基准）")
    p.add_argument("--realert-on-reappear", action="store_true",
                   help="移除后重现的股票会再次提示（默认不重复）")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main():
    # Windows 默认 cp1252 控制台打不出 emoji/制表符 → 统一按 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    board = AnnouncementBoard(args.board_file)
    fetcher = lambda: fetch_stock_list(args.source)   # noqa: E731

    def _cycle():
        new, ok = run_once(
            fetcher, args.state_file,
            market=args.market,
            alert_on_first_run=args.alert_on_first_run,
            realert_on_reappear=args.realert_on_reappear,
        )
        if not ok:
            return
        if new:
            run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            board.publish([
                {"code": c, "market": args.market or args.source, "first_seen": run_at}
                for c in new
            ])
            print("\n".join(f"🆕 {c}" for c in new))
        if args.show_board:
            print(board.render(args.board_limit))

    if args.once:
        _cycle()
        return
    logger.info("监视器启动：每 %ds 刷新一次（%s）", args.interval, args.source)
    while True:
        _cycle()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
