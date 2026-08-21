"""Unit tests for the new-stock monitor (tools/new_stock_monitor.py)."""

import json

from tools.new_stock_monitor import (
    AnnouncementBoard,
    fetch_stock_list,
    normalize_code,
    run_once,
)

# ── normalization ──────────────────────────────────────────────────────────

def test_normalize_code():
    assert normalize_code("600000.SS") == "600000"
    assert normalize_code(" sh600000 ") == "600000"
    assert normalize_code("NASDAQ:AAPL") == "AAPL"
    assert normalize_code("00700.HK") == "00700"
    assert normalize_code(600000.0) == "600000"      # Excel numeric code
    assert normalize_code("") is None
    assert normalize_code(None) is None


def test_normalize_code_is_idempotent():
    assert normalize_code(normalize_code(" SH600000.SS ")) == "600000"


# ── first run behaviour ───────────────────────────────────────────────────

def test_first_run_baseline_no_alerts(tmp_path):
    state = tmp_path / "s.json"
    new, ok = run_once(lambda: {"AAA", "BBB"}, str(state))
    assert ok and new == []
    assert json.loads(state.read_text())["ever_seen"] == ["AAA", "BBB"]


def test_first_run_alert_all(tmp_path):
    state = tmp_path / "s.json"
    new, ok = run_once(lambda: {"AAA", "BBB"}, str(state), alert_on_first_run=True)
    assert new == ["AAA", "BBB"]


# ── dedup / never repeat ──────────────────────────────────────────────────

def test_never_repeat(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA", "BBB"}, str(state))
    new, ok = run_once(lambda: {"AAA", "BBB", "CCC"}, str(state))
    assert new == ["CCC"]                              # AAA/BBB already seen
    new2, _ = run_once(lambda: {"AAA", "CCC"}, str(state))
    assert new2 == []                                  # nothing new


# ── reappear ──────────────────────────────────────────────────────────────

def test_reappear_not_alerted_by_default(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA", "BBB"}, str(state))
    run_once(lambda: {"AAA"}, str(state))              # BBB disappears
    new, _ = run_once(lambda: {"AAA", "BBB"}, str(state))  # BBB returns
    assert new == []                                   # ever_seen keeps BBB


def test_reappear_alerted_when_enabled(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA", "BBB"}, str(state))
    run_once(lambda: {"AAA"}, str(state))
    new, _ = run_once(lambda: {"AAA", "BBB"}, str(state), realert_on_reappear=True)
    assert new == ["BBB"]


# ── failure / empty handling ──────────────────────────────────────────────

def test_fetcher_error_skips_round(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA"}, str(state))

    def boom():
        raise RuntimeError("network down")

    new, ok = run_once(boom, str(state))
    assert ok is False and new == []
    # state untouched
    assert json.loads(state.read_text())["ever_seen"] == ["AAA"]


def test_empty_list_skips_round(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA"}, str(state))
    new, ok = run_once(lambda: set(), str(state))
    assert ok is False and new == []
    assert json.loads(state.read_text())["ever_seen"] == ["AAA"]


# ── multi-market isolation ────────────────────────────────────────────────

def test_market_scoped_state(tmp_path):
    state = tmp_path / "s.json"
    run_once(lambda: {"AAA"}, str(state), market="my")
    run_once(lambda: {"AAA"}, str(state), market="us")   # us 首轮建立基准
    new, _ = run_once(lambda: {"AAA", "BBB"}, str(state), market="us")
    assert new == ["BBB"]                                # us 桶独立演进


# ── board accumulation ────────────────────────────────────────────────────

def test_board_accumulates_and_persists(tmp_path):
    board_file = tmp_path / "b.json"
    board = AnnouncementBoard(str(board_file))
    board.publish([{"code": "AAA", "market": "my", "first_seen": "2026-01-01 00:00:00"}])
    board.publish([{"code": "BBB", "market": "us", "first_seen": "2026-01-01 00:05:00"}])
    assert [e["code"] for e in board.as_list()] == ["AAA", "BBB"]

    board2 = AnnouncementBoard(str(board_file))        # reload from disk
    assert [e["code"] for e in board2.as_list()] == ["AAA", "BBB"]


def test_board_ignores_empty_entries(tmp_path):
    board = AnnouncementBoard(str(tmp_path / "b.json"))
    board.publish([{"code": ""}, {"market": "x"}, {"code": "CCC"}])
    assert [e["code"] for e in board.as_list()] == ["CCC"]


# ── CSV parsing ───────────────────────────────────────────────────────────

def test_fetch_csv_with_code_column(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("name,code\nAlpha,AAA\nBeta,BBB\n", encoding="utf-8")
    assert fetch_stock_list(str(p)) == {"AAA", "BBB"}


def test_fetch_csv_plain_codes(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("600000\n600004\n# comment line\n", encoding="utf-8")
    assert fetch_stock_list(str(p)) == {"600000", "600004"}


def test_fetch_csv_normalizes(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("symbol\n sh600000 \n7001.KL\n", encoding="utf-8")
    assert fetch_stock_list(str(p)) == {"600000", "7001"}
