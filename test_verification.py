"""Automated verification of the 7 scenarios from the implementation plan."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import batch
import cli
import clipboard
import console_input
import database as db
from batch import (
    InboundFailure,
    InboundPending,
    InboundReady,
    OutboundFailure,
    OutboundReady,
    classify_inbound_line,
    classify_outbound_line,
)
from parser import extract_valid_account_lines, format_account, parse_account_line


def _use_temp_db() -> tempfile.TemporaryDirectory[str]:
    tmp = tempfile.TemporaryDirectory()
    data_dir = Path(tmp.name) / "data"
    data_dir.mkdir()
    db._DATA_DIR = data_dir  # type: ignore[attr-defined]
    db.init_db()
    return tmp


def _reset_inventory() -> None:
    with db._connect() as conn:
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM outbound_records")
        conn.execute("DELETE FROM inbound_records")
        conn.execute("DELETE FROM account_notes")


def test_scenario_1_initial_inventory_zero() -> None:
    assert db.count_inventory() == 0


def test_scenario_2_inventory_duplicate_blocked() -> None:
    u, p, e, ep, url = parse_account_line("a----b")
    db.insert_account(u, p, e, ep, url)
    assert db.count_inventory() == 1
    assert db.exists_in_inventory("a")
    try:
        db.insert_account("a", "b2")
        raise AssertionError("expected IntegrityError / ValueError")
    except ValueError:
        pass
    assert db.count_inventory() == 1


def test_scenario_3_full_format_inbound() -> None:
    u, p, e, ep, url = parse_account_line("a2----b2----e@x.com----ep")
    db.insert_account(u, p, e, ep, url)
    assert db.count_inventory() == 2


def test_scenario_4_fifo_first_outbound() -> None:
    record = db.outbound_oldest()
    assert record is not None
    text = format_account(
        record["username"],
        record["password"],
        record["email"],
        record["email_password"],
        record["url"],
    )
    assert text == "a----b"
    assert db.count_inventory() == 1


def test_scenario_5_second_outbound_and_history() -> None:
    record = db.outbound_oldest()
    assert record is not None
    text = format_account(
        record["username"],
        record["password"],
        record["email"],
        record["email_password"],
        record["url"],
    )
    assert text == "a2----b2----e@x.com----ep"
    assert db.count_inventory() == 0
    assert db.count_outbound_records() == 2


def test_scenario_6_outbound_history_confirm_logic() -> None:
    assert db.exists_in_outbound("a")
    assert not db.exists_in_inventory("a")
    latest = db.get_latest_outbound_time("a")
    assert latest is not None

    # Simulate N: do not insert
    if db.exists_in_outbound("a") and not db.exists_in_inventory("a"):
        confirm = "n"
        if confirm.lower() != "y":
            assert db.count_inventory() == 0

    # Simulate y: insert succeeds
    db.insert_account("a", "b")
    assert db.count_inventory() == 1


def test_scenario_7_empty_outbound() -> None:
    _reset_inventory()
    assert db.outbound_oldest() is None


def test_parser_errors() -> None:
    for bad in ("", "only", "a----", "----b", "a----b----c----d----e----f"):
        try:
            parse_account_line(bad)
            raise AssertionError(f"expected error for: {bad!r}")
        except ValueError:
            pass


def test_parser_five_segments() -> None:
    u, p, e, ep, url = parse_account_line(
        "user----pass----mail@x.com----mailpass----https://example.com"
    )
    assert u == "user"
    assert p == "pass"
    assert e == "mail@x.com"
    assert ep == "mailpass"
    assert url == "https://example.com"

    u2, p2, e2, ep2, url2 = parse_account_line(
        "user----pass--------https://example.com"
    )
    assert u2 == "user"
    assert p2 == "pass"
    assert e2 is None
    assert ep2 is None
    assert url2 == "https://example.com"


def test_format_account() -> None:
    assert format_account("u", "p") == "u----p"
    assert format_account("u", "p", "e", "ep") == "u----p----e----ep"
    assert (
        format_account("u", "p", None, None, "https://x.com")
        == "u----p--------https://x.com"
    )
    assert (
        format_account("u", "p", "e", "ep", "https://x.com")
        == "u----p----e----ep----https://x.com"
    )


def test_batch_inbound_mixed_lines() -> None:
    _reset_inventory()
    seen: set[str] = set()
    lines = [
        "user1----pass1",
        "bad-line",
        "user2----pass2",
    ]
    ready = 0
    failed = 0
    for line in lines:
        result = classify_inbound_line(
            line,
            seen,
            exists_in_inventory=db.exists_in_inventory,
            exists_in_outbound=db.exists_in_outbound,
        )
        if isinstance(result, InboundReady):
            db.insert_account(
                result.username,
                result.password,
                result.email,
                result.email_password,
                result.url,
            )
            seen.add(result.username)
            ready += 1
        elif isinstance(result, InboundFailure):
            failed += 1

    assert ready == 2
    assert failed == 1
    assert db.count_inventory() == 2


def test_batch_inbound_duplicate_in_batch() -> None:
    _reset_inventory()
    seen: set[str] = set()
    lines = ["dup----p1", "dup----p2"]

    first = classify_inbound_line(
        lines[0],
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(first, InboundReady)
    db.insert_account(
        first.username,
        first.password,
        first.email,
        first.email_password,
        first.url,
    )
    seen.add(first.username)

    second = classify_inbound_line(
        lines[1],
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(second, InboundFailure)
    assert second.reason == "账号 dup 已在库存中"
    assert db.count_inventory() == 1


def test_batch_inbound_seen_username_duplicate() -> None:
    _reset_inventory()
    seen: set[str] = {"dup"}
    result = classify_inbound_line(
        "dup----p2",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, InboundFailure)
    assert result.reason == "本批次内账号重复"


def test_batch_outbound_default_one() -> None:
    _reset_inventory()
    for i in range(3):
        db.insert_account(f"u{i}", f"p{i}")
    assert db.count_inventory() == 3

    records = db.outbound_oldest_many(1)
    assert len(records) == 1
    assert records[0]["username"] == "u0"
    assert db.count_inventory() == 2


def test_batch_outbound_fifo_two() -> None:
    _reset_inventory()
    db.insert_account("first", "p1")
    db.insert_account("second", "p2")
    db.insert_account("third", "p3")

    records = db.outbound_oldest_many(2)
    assert len(records) == 2
    assert records[0]["username"] == "first"
    assert records[1]["username"] == "second"
    assert db.count_inventory() == 1
    assert db.count_outbound_records() == 2


def test_batch_outbound_exceeds_inventory() -> None:
    _reset_inventory()
    db.insert_account("a", "b")
    db.insert_account("c", "d")

    records = db.outbound_oldest_many(10)
    assert len(records) == 2
    assert db.count_inventory() == 0


def test_outbound_oldest_many_zero() -> None:
    _reset_inventory()
    db.insert_account("x", "y")
    assert db.outbound_oldest_many(0) == []
    assert db.count_inventory() == 1


def _make_pending(username: str, password: str = "newpass") -> InboundPending:
    return InboundPending(
        line=f"{username}----{password}",
        username=username,
        password=password,
    )


def test_get_latest_outbound_times_batch() -> None:
    _reset_inventory()
    db.insert_account("u1", "p1")
    db.insert_account("u2", "p2")
    db.outbound_oldest_many(2)

    times = db.get_latest_outbound_times(["u1", "u2", "missing"])
    assert set(times.keys()) == {"u1", "u2"}
    assert times["u1"] is not None
    assert times["u2"] is not None
    assert "missing" not in times
    assert db.get_latest_outbound_time("u1") == times["u1"]


def test_exists_many_batch() -> None:
    _reset_inventory()
    db.insert_account("was_out", "p")
    db.outbound_oldest()
    db.insert_account("in_stock", "p")

    inventory = db.exists_in_inventory_many(["in_stock", "was_out", "none"])
    outbound = db.exists_in_outbound_many(["in_stock", "was_out", "none"])
    assert inventory == {"in_stock"}
    assert outbound == {"was_out"}


def test_clipboard_copy_text() -> None:
    import pyperclip

    with mock.patch("pyperclip.copy") as copy_mock:
        copy_mock.return_value = None
        assert clipboard.copy_text("hello") is True
        copy_mock.assert_called_once_with("hello")

    with mock.patch("pyperclip.copy") as copy_mock, mock.patch("clipboard.time.sleep"):
        copy_mock.side_effect = [pyperclip.PyperclipException(), None]
        assert clipboard.copy_text("retry") is True
        assert copy_mock.call_count == 2

    with mock.patch("pyperclip.copy") as copy_mock, mock.patch("clipboard.time.sleep"):
        copy_mock.side_effect = pyperclip.PyperclipException()
        assert clipboard.copy_text("fail") is False
        assert copy_mock.call_count == 5


def test_clipboard_read_text() -> None:
    import pyperclip

    with mock.patch("pyperclip.paste", return_value="pasted"):
        assert clipboard.read_text() == "pasted"

    with mock.patch("pyperclip.paste") as paste_mock, mock.patch("clipboard.time.sleep"):
        paste_mock.side_effect = [pyperclip.PyperclipException(), "ok"]
        assert clipboard.read_text() == "ok"
        assert paste_mock.call_count == 2

    with mock.patch("pyperclip.paste") as paste_mock, mock.patch("clipboard.time.sleep"):
        paste_mock.side_effect = pyperclip.PyperclipException()
        assert clipboard.read_text() is None
        assert paste_mock.call_count == 5


def test_extract_valid_account_lines() -> None:
    text = "\n".join(
        [
            "表头说明",
            "",
            "user----pass",
            "bad-line",
            "  u2----p2  ",
            "----only",
        ]
    )
    valid, rejected = extract_valid_account_lines(text)
    assert valid == ["user----pass", "u2----p2"]
    assert rejected == 4


def test_read_batch_clipboard_import() -> None:
    _reset_inventory()
    cli._last_app_clipboard = None
    clip_text = "header\n\nuser1----pass1\nbad\nuser2----pass2"
    read_iter = iter(["", None])

    def fake_read_with_idle(idle_tick=None, prompt=""):
        if idle_tick is not None:
            idle_tick()
        return next(read_iter)

    with mock.patch(
        "console_input.read_line_or_exit_with_idle", side_effect=fake_read_with_idle
    ), mock.patch("clipboard.read_text", return_value=clip_text):
        lines = cli._read_batch_lines_or_exit("prompt")
    assert lines == ["user1----pass1", "user2----pass2"]
    cli._process_inbound_batch(lines)
    assert db.count_inventory() == 2


def test_ignore_app_clipboard() -> None:
    cli._last_app_clipboard = None
    _reset_inventory()
    failure_text = "bad----line\ndup----p2"
    cli._last_app_clipboard = failure_text
    read_iter = iter(["", None])

    def fake_read_with_idle(idle_tick=None, prompt=""):
        if idle_tick is not None:
            idle_tick()
        return next(read_iter)

    with mock.patch(
        "console_input.read_line_or_exit_with_idle", side_effect=fake_read_with_idle
    ), mock.patch("clipboard.read_text", return_value=failure_text):
        lines = cli._read_batch_lines_or_exit("prompt")
    assert lines == []


def test_batch_inbound_pending_approve() -> None:
    _reset_inventory()
    db.insert_account("hist", "old")
    db.outbound_oldest()
    assert db.exists_in_outbound("hist")

    seen: set[str] = set()
    result = classify_inbound_line(
        "hist----newpass",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, InboundPending)

    pending = [result]
    with mock.patch("console_input.keyboard_supported", return_value=True), mock.patch(
        "console_input.read_key", return_value=":"
    ), mock.patch("console_input.read_command_line", return_value="a 1"):
        approved, failures = cli._review_pending(pending)
    assert approved == 1
    assert failures == []
    assert db.exists_in_inventory("hist")
    assert db.count_inventory() == 1


def test_batch_inbound_pending_cancel() -> None:
    _reset_inventory()
    db.insert_account("hist2", "old")
    db.outbound_oldest()

    seen: set[str] = set()
    result = classify_inbound_line(
        "hist2----newpass",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, InboundPending)

    pending = [result]
    with mock.patch("console_input.keyboard_supported", return_value=True), mock.patch(
        "console_input.read_key", return_value=":"
    ), mock.patch("console_input.read_command_line", return_value="c 1"):
        approved, failures = cli._review_pending(pending)
    assert approved == 0
    assert len(failures) == 1
    assert failures[0].reason == "用户取消录入（曾出现在出库记录）"
    assert not db.exists_in_inventory("hist2")


def test_review_pending_keyboard_toggle_and_approve() -> None:
    _reset_inventory()
    pending = [_make_pending("kb1")]

    with mock.patch("console_input.enable_vt_mode", return_value=False), mock.patch(
        "console_input.keyboard_supported", return_value=True
    ), mock.patch("console_input.read_key", side_effect=["space", "y"]):
        approved, failures = cli._review_pending(pending)

    assert approved == 1
    assert failures == []
    assert db.count_inventory() == 1
    assert db.exists_in_inventory("kb1")


def test_review_pending_keyboard_move_cursor() -> None:
    _reset_inventory()
    pending = [_make_pending("move1"), _make_pending("move2")]

    with mock.patch("console_input.enable_vt_mode", return_value=False), mock.patch(
        "console_input.keyboard_supported", return_value=True
    ), mock.patch("console_input.read_key", side_effect=["down", "esc"]):
        cli._review_pending(pending)

    assert pending == []


def test_review_pending_keyboard_cancel_selected() -> None:
    _reset_inventory()
    pending = [_make_pending("nc1")]

    with mock.patch("console_input.enable_vt_mode", return_value=False), mock.patch(
        "console_input.keyboard_supported", return_value=True
    ), mock.patch("console_input.read_key", side_effect=["space", "n"]):
        approved, failures = cli._review_pending(pending)

    assert approved == 0
    assert len(failures) == 1
    assert failures[0].reason == "用户取消录入（曾出现在出库记录）"


def test_review_pending_keyboard_esc_exits() -> None:
    _reset_inventory()
    pending = [_make_pending("esc1"), _make_pending("esc2")]

    with mock.patch("console_input.enable_vt_mode", return_value=False), mock.patch(
        "console_input.keyboard_supported", return_value=True
    ), mock.patch("console_input.read_key", return_value="esc"):
        approved, failures = cli._review_pending(pending)

    assert approved == 0
    assert len(failures) == 2


def test_review_pending_keyboard_y_without_selection() -> None:
    _reset_inventory()
    pending = [_make_pending("warn1")]

    with mock.patch("console_input.enable_vt_mode", return_value=False), mock.patch(
        "console_input.keyboard_supported", return_value=True
    ), mock.patch("console_input.read_key", side_effect=["y", "esc"]):
        approved, failures = cli._review_pending(pending)

    assert approved == 0
    assert len(failures) == 1


def test_batch_inbound_url_passthrough() -> None:
    _reset_inventory()
    seen: set[str] = set()
    line = "u----p----e@x.com----ep----https://site.com"
    result = classify_inbound_line(
        line,
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, InboundReady)
    assert result.url == "https://site.com"
    db.insert_account(
        result.username,
        result.password,
        result.email,
        result.email_password,
        result.url,
    )
    hits = db.search_inventory("site.com")
    assert len(hits) == 1
    assert hits[0]["url"] == "https://site.com"


def test_search_inventory_and_history() -> None:
    _reset_inventory()
    db.insert_account("findme", "p1", url="https://inv.example")
    db.insert_account("other", "p2")
    db.outbound_oldest()

    inv_hits = db.search_inventory("inv.example")
    assert len(inv_hits) == 0

    hist_hits = db.search_outbound_history("inv.example")
    assert len(hist_hits) == 1
    assert hist_hits[0]["username"] == "findme"

    db.insert_account("stock", "pw", email="unique@mail.test")
    assert len(db.search_inventory("unique@mail")) == 1
    assert len(db.search_outbound_history("unique@mail")) == 0


def test_search_like_escape() -> None:
    _reset_inventory()
    db.insert_account("100%off", "p")
    db.insert_account("normal", "p")

    assert len(db.search_inventory("100%off")) == 1
    assert len(db.search_inventory("100%")) == 1
    assert len(db.search_inventory("_")) == 0


def test_failure_lines_for_clipboard() -> None:
    failures = [
        InboundFailure(line="bad----line", reason="格式错误"),
        InboundFailure(line="dup----p2", reason="重复"),
    ]
    text = cli.failure_lines_for_clipboard(failures)
    assert text == "bad----line\ndup----p2"
    assert "格式错误" not in text
    assert "重复" not in text


def test_console_input_read_key_arrows() -> None:
    if sys.platform != "win32":
        assert console_input.kbhit() is False
        return

    with mock.patch("msvcrt.getch", side_effect=[b"\xe0", b"H"]):
        assert console_input.read_key() == "up"
    with mock.patch("msvcrt.getch", side_effect=[b"\x00", b"P"]):
        assert console_input.read_key() == "down"


def test_read_line_or_exit_esc() -> None:
    with mock.patch.object(console_input, "_IS_WINDOWS", True), mock.patch(
        "console_input.read_key", return_value="esc"
    ):
        assert console_input.read_line_or_exit("prompt: ") is None


def test_read_line_or_exit_q_is_normal_input() -> None:
    with mock.patch.object(console_input, "_IS_WINDOWS", True), mock.patch(
        "console_input.read_key", side_effect=["q", "enter"]
    ):
        assert console_input.read_line_or_exit("") == "q"

    with mock.patch.object(console_input, "_IS_WINDOWS", False), mock.patch(
        "console_input._read_line_unix", return_value="q"
    ):
        assert console_input.read_line_or_exit("> ") == "q"


def test_read_line_or_exit_unix_esc() -> None:
    fake_termios = mock.MagicMock()
    fake_tty = mock.MagicMock()
    with mock.patch.object(console_input, "_IS_WINDOWS", False), mock.patch.dict(
        "sys.modules", {"termios": fake_termios, "tty": fake_tty}
    ), mock.patch("sys.stdin.read", return_value="\x1b"):
        fake_termios.tcgetattr.return_value = []
        assert console_input.read_line_or_exit("") is None
        fake_termios.tcsetattr.assert_called()
        fake_tty.setraw.assert_called()


def test_inbound_mode_stays_after_batch() -> None:
    _reset_inventory()
    side_effect = ["user1----pass1", "", "user2----pass2", "", None]
    with mock.patch("console_input.read_line_or_exit_with_idle", side_effect=side_effect):
        cli.handle_inbound()
    assert db.count_inventory() == 2


def test_outbound_mode_invalid_then_retry() -> None:
    _reset_inventory()
    db.insert_account("u1", "p1")
    with mock.patch(
        "console_input.read_line_or_exit", side_effect=["abc", "1", None]
    ), mock.patch("cli.copy_to_clipboard", return_value=True):
        cli.handle_outbound()
    assert db.count_inventory() == 0


def test_search_mode_empty_query_retries() -> None:
    _reset_inventory()
    db.insert_account("findme", "p")
    with mock.patch(
        "console_input.read_line_or_exit", side_effect=["", "findme", None]
    ):
        cli.handle_search()


def test_outbound_by_username() -> None:
    _reset_inventory()
    db.insert_account("first", "p1")
    db.insert_account("second", "p2", email="target@mail.test")

    record = db.outbound_by_username("second")
    assert record is not None
    assert record["username"] == "second"
    assert record["password"] == "p2"
    assert record["email"] == "target@mail.test"
    assert record["email_password"] is None
    assert record["url"] is None
    assert record["created_at"] is not None

    assert not db.exists_in_inventory("second")
    assert db.exists_in_inventory("first")
    assert db.exists_in_outbound("second")
    assert db.count_inventory() == 1
    assert db.count_outbound_records() == 1


def test_search_single_inventory_offers_outbound() -> None:
    _reset_inventory()
    db.insert_account("stock", "pw", email="unique@mail.test")

    with mock.patch(
        "console_input.read_line_or_exit",
        side_effect=["unique@mail", "Y", None],
    ), mock.patch("cli.copy_to_clipboard", return_value=True):
        cli.handle_search()

    assert db.count_inventory() == 0
    assert db.count_outbound_records() == 1
    assert db.exists_in_outbound("stock")

    _reset_inventory()
    db.insert_account("stock", "pw", email="unique@mail.test")

    with mock.patch(
        "console_input.read_line_or_exit",
        side_effect=["unique@mail", "", None],
    ):
        cli.handle_search()

    assert db.count_inventory() == 1
    assert db.count_outbound_records() == 0

    _reset_inventory()
    db.insert_account("stock", "pw", email="unique@mail.test")

    with mock.patch(
        "console_input.read_line_or_exit",
        side_effect=["unique@mail", "n", None],
    ):
        cli.handle_search()

    assert db.count_inventory() == 1
    assert db.count_outbound_records() == 0


def test_search_multiple_inventory_no_outbound_prompt() -> None:
    _reset_inventory()
    db.insert_account("user1", "p1")
    db.insert_account("user2", "p2")

    with mock.patch(
        "console_input.read_line_or_exit",
        side_effect=["user", None],
    ), mock.patch("database.outbound_by_username") as outbound_mock:
        cli.handle_search()

    outbound_mock.assert_not_called()
    assert db.count_inventory() == 2


def test_classify_outbound_line_in_inventory() -> None:
    _reset_inventory()
    db.insert_account("stock", "p1")
    seen: set[str] = set()
    result = classify_outbound_line(
        "stock----p1",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, OutboundReady)
    assert result.username == "stock"


def test_classify_outbound_line_not_in_inventory() -> None:
    _reset_inventory()
    seen: set[str] = set()
    result = classify_outbound_line(
        "new----p1",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, OutboundReady)
    assert result.username == "new"


def test_classify_outbound_line_already_outbound() -> None:
    _reset_inventory()
    db.insert_account("gone", "p1")
    db.outbound_oldest()
    seen: set[str] = set()
    result = classify_outbound_line(
        "gone----p1",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, OutboundFailure)
    assert result.reason == "已在出库记录中"


def test_classify_outbound_line_reinbound_ready() -> None:
    _reset_inventory()
    db.insert_account("rein", "old")
    db.outbound_oldest()
    db.insert_account("rein", "new")
    seen: set[str] = set()
    result = classify_outbound_line(
        "rein----new",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, OutboundReady)


def test_classify_outbound_line_batch_duplicate() -> None:
    _reset_inventory()
    seen: set[str] = {"dup"}
    result = classify_outbound_line(
        "dup----p2",
        seen,
        exists_in_inventory=db.exists_in_inventory,
        exists_in_outbound=db.exists_in_outbound,
    )
    assert isinstance(result, OutboundFailure)
    assert result.reason == "本批次内账号重复"


def test_insert_outbound_record() -> None:
    _reset_inventory()
    before = db.count_outbound_records()
    db.insert_outbound_record("direct", "pw", email="e@x.com")
    assert db.count_outbound_records() == before + 1
    assert db.exists_in_outbound("direct")
    assert not db.exists_in_inventory("direct")


def test_database_registry_registers_existing_db() -> None:
    _reset_inventory()
    db.insert_account("legacy", "pw")
    db._registry_path().unlink(missing_ok=True)  # type: ignore[attr-defined]

    db.init_db()
    databases = db.list_database_info()
    assert len(databases) == 1
    assert databases[0]["name"] == "默认数据库"
    assert databases[0]["file_name"] == "accounts.db"
    assert databases[0]["active"]
    assert db.exists_in_inventory("legacy")


def test_database_create_switch_rename_and_delete() -> None:
    _reset_inventory()
    db.insert_account("default_user", "pw")
    default = db.get_active_database_info()

    created = db.create_database("客户 A")
    assert created["name"] == "客户 A"
    assert created["active"]
    assert db.count_inventory() == 0
    db.insert_account("new_user", "pw")

    db.set_active_database(default["id"])
    assert db.exists_in_inventory("default_user")
    assert not db.exists_in_inventory("new_user")

    renamed = db.rename_database(created["id"], "客户 A 重命名")
    assert renamed["name"] == "客户 A 重命名"

    db.delete_database(default["id"])
    databases = db.list_database_info()
    assert len(databases) == 1
    assert databases[0]["id"] == created["id"]
    assert databases[0]["active"]

    replacement = db.delete_database(created["id"])
    assert replacement["name"] == "默认数据库"
    assert replacement["active"]
    assert db.count_inventory() == 0


def test_database_clone_copies_data_and_stays_independent() -> None:
    _reset_inventory()
    db.insert_account("source_user", "pw")
    db.insert_outbound_record("source_history", "old_pw")
    source = db.get_active_database_info()

    try:
        db.clone_database(source["id"], "   ")
        raise AssertionError("expected ValueError for empty clone name")
    except ValueError:
        pass

    try:
        db.clone_database("missing", "缺失库副本")
        raise AssertionError("expected ValueError for missing source")
    except ValueError:
        pass

    cloned = db.clone_database(source["id"], "默认数据库副本")
    assert cloned["name"] == "默认数据库副本"
    assert cloned["active"]
    assert cloned["id"] != source["id"]
    assert cloned["path"] != source["path"]
    assert Path(cloned["path"]).exists()
    assert db.exists_in_inventory("source_user")
    assert db.exists_in_outbound("source_history")

    db.insert_account("clone_only", "pw")
    db.set_active_database(source["id"])
    assert db.exists_in_inventory("source_user")
    assert not db.exists_in_inventory("clone_only")
    db.delete_database(cloned["id"])


def test_separator_rules_default() -> None:
    rules = db.list_separator_rules()
    assert len(rules) >= 1
    default = next(rule for rule in rules if rule["id"] == "builtin-default")
    assert default["name"] == "默认规则"
    assert default["separator"] == "----"
    assert default["enabled"] is True
    assert default["built_in"] is True
    assert db.list_enabled_separators() == ["----"]


def test_separator_rules_crud_validation() -> None:
    try:
        db.create_separator_rule("重复", "----")
        raise AssertionError("expected duplicate separator error")
    except ValueError:
        pass

    try:
        db.create_separator_rule("   ", "::::")
        raise AssertionError("expected empty name error")
    except ValueError:
        pass

    try:
        db.create_separator_rule("换行", "a\nb")
        raise AssertionError("expected newline separator error")
    except ValueError:
        pass

    try:
        db.create_separator_rule("超长", "x" * 21)
        raise AssertionError("expected separator too long error")
    except ValueError:
        pass

    custom = db.create_separator_rule("自定义", "::::")
    assert custom["enabled"] is True
    assert custom["built_in"] is False

    try:
        db.create_separator_rule("重复2", "::::")
        raise AssertionError("expected duplicate separator error")
    except ValueError:
        pass

    try:
        db.delete_separator_rule("builtin-default")
        raise AssertionError("expected cannot delete builtin error")
    except ValueError:
        pass

    db.update_separator_rule(custom["id"], enabled=False)
    try:
        db.update_separator_rule("builtin-default", enabled=False)
        raise AssertionError("expected cannot disable last enabled rule")
    except ValueError:
        pass

    db.update_separator_rule(custom["id"], enabled=True)
    db.update_separator_rule(custom["id"], enabled=False)
    db.delete_separator_rule(custom["id"])

    only_custom = db.create_separator_rule("唯一", "::::")
    db.update_separator_rule("builtin-default", enabled=False)
    try:
        db.delete_separator_rule(only_custom["id"])
        raise AssertionError("expected cannot delete last enabled rule")
    except ValueError:
        pass
    try:
        db.update_separator_rule(only_custom["id"], enabled=False)
        raise AssertionError("expected cannot disable last enabled rule")
    except ValueError:
        pass

    db.update_separator_rule("builtin-default", enabled=True)
    db.update_separator_rule(only_custom["id"], enabled=False)
    db.delete_separator_rule(only_custom["id"])


def test_parse_multi_separator() -> None:
    u, p, _, _, _ = parse_account_line("user::::pass", ["::::"])
    assert u == "user"
    assert p == "pass"

    u2, p2, _, _, _ = parse_account_line("user::::pass", ["----", "::::"])
    assert u2 == "user"
    assert p2 == "pass"

    u3, p3, _, _, _ = parse_account_line("a----b", ["::::", "----"])
    assert u3 == "a"
    assert p3 == "b"

    try:
        parse_account_line("a----b", ["::::"])
        raise AssertionError("expected parse failure without ----")
    except ValueError:
        pass


def test_output_stays_default_separator() -> None:
    _reset_inventory()
    u, p, e, ep, url = parse_account_line("user::::pass", ["::::"])
    db.insert_account(u, p, e, ep, url)
    text = format_account(u, p, e, ep, url)
    assert "::::" not in text
    assert text == "user----pass"

    client = _api_client()
    response = client.post("/api/outbound/fifo/commit", json={"quantity": 1})
    assert response.status_code == 200
    clipboard_text = response.json()["clipboardText"]
    assert "::::" not in clipboard_text
    assert clipboard_text == "user----pass"


def test_clone_copies_separator_rules() -> None:
    _reset_inventory()
    custom = db.create_separator_rule("克隆规则", "::::")
    source = db.get_active_database_info()
    source_rules = db.list_separator_rules()
    source_enabled = db.list_enabled_separators()

    cloned = db.clone_database(source["id"], "规则副本")
    assert cloned["active"]
    cloned_rules = db.list_separator_rules()
    cloned_enabled = db.list_enabled_separators()

    assert len(cloned_rules) == len(source_rules)
    assert cloned_enabled == source_enabled
    assert any(rule["separator"] == "::::" for rule in cloned_rules)

    db.set_active_database(source["id"])
    db.delete_database(cloned["id"])
    db.delete_separator_rule(custom["id"])


def test_process_outbound_batch_mixed() -> None:
    _reset_inventory()
    db.insert_account("in_stock", "p1")
    db.insert_account("gone", "p2")
    db.outbound_by_username("gone")

    lines = [
        "in_stock----p1",
        "direct----pw",
        "gone----p2",
        "bad-line",
    ]
    with mock.patch("cli.copy_to_clipboard", return_value=True):
        cli._process_outbound_batch(lines)

    assert not db.exists_in_inventory("in_stock")
    assert db.exists_in_outbound("in_stock")
    assert db.exists_in_outbound("direct")
    assert db.count_outbound_records() == 3


def test_outbound_paste_mode_stays_after_batch() -> None:
    _reset_inventory()
    db.insert_account("u1", "p1")
    side_effect = ["u1----p1", "", "direct----pw", "", None]
    with mock.patch("console_input.read_line_or_exit_with_idle", side_effect=side_effect), mock.patch(
        "cli.copy_to_clipboard", return_value=True
    ):
        cli.handle_outbound_paste()
    assert db.count_inventory() == 0
    assert db.exists_in_outbound("direct")


def test_handle_entry_outbound_paste() -> None:
    _reset_inventory()
    side_effect = ["2", "new----pw", "", None]
    with mock.patch("console_input.read_line_or_exit", side_effect=["2", None]), mock.patch(
        "console_input.read_line_or_exit_with_idle", side_effect=["new----pw", "", None]
    ), mock.patch("cli.copy_to_clipboard", return_value=True):
        cli.handle_entry()
    assert db.exists_in_outbound("new")


def _api_client():
    from fastapi.testclient import TestClient

    import api

    return TestClient(api.app)


def test_api_separator_rules() -> None:
    _reset_inventory()
    client = _api_client()

    response = client.get("/api/separator-rules")
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert len(rules) >= 1
    default = next(rule for rule in rules if rule["id"] == "builtin-default")
    assert default["separator"] == "----"
    assert default["enabled"] is True

    duplicate = client.post(
        "/api/separator-rules",
        json={"name": "重复", "separator": "----"},
    )
    assert duplicate.status_code == 400

    empty_name = client.post(
        "/api/separator-rules",
        json={"name": "   ", "separator": "::::"},
    )
    assert empty_name.status_code == 400

    empty_separator = client.post(
        "/api/separator-rules",
        json={"name": "空分隔", "separator": "   "},
    )
    assert empty_separator.status_code == 400

    newline_separator = client.post(
        "/api/separator-rules",
        json={"name": "换行", "separator": "a\nb"},
    )
    assert newline_separator.status_code == 400

    created = client.post(
        "/api/separator-rules",
        json={"name": "API 自定义", "separator": "::::"},
    )
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["enabled"] is True
    assert created_payload["builtIn"] is False

    disabled = client.patch(
        f"/api/separator-rules/{created_payload['id']}",
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    reenabled = client.patch(
        f"/api/separator-rules/{created_payload['id']}",
        json={"enabled": True},
    )
    assert reenabled.status_code == 200
    assert reenabled.json()["enabled"] is True

    deleted = client.delete(f"/api/separator-rules/{created_payload['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    delete_builtin = client.delete("/api/separator-rules/builtin-default")
    assert delete_builtin.status_code == 400

    only_custom = client.post(
        "/api/separator-rules",
        json={"name": "唯一", "separator": "::::"},
    )
    assert only_custom.status_code == 200
    custom_id = only_custom.json()["id"]

    disable_builtin = client.patch(
        "/api/separator-rules/builtin-default",
        json={"enabled": False},
    )
    assert disable_builtin.status_code == 200

    disable_last = client.patch(
        f"/api/separator-rules/{custom_id}",
        json={"enabled": False},
    )
    assert disable_last.status_code == 400

    client.patch("/api/separator-rules/builtin-default", json={"enabled": True})
    client.delete(f"/api/separator-rules/{custom_id}")


def test_api_inbound_preview() -> None:
    _reset_inventory()
    db.insert_account("stocked", "p1")
    db.insert_outbound_record("returned", "p2")
    client = _api_client()

    response = client.post(
        "/api/inbound/preview",
        json={
            "text": "\n".join(
                [
                    "fresh----pw",
                    "stocked----p1",
                    "returned----p2",
                    "bad-line",
                    "fresh----again",
                ]
            )
        },
    )
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["category"] for row in rows] == [
        "ready",
        "duplicate",
        "pending",
        "invalid",
        "batchDuplicate",
    ]


def test_api_inbound_commit() -> None:
    _reset_inventory()
    db.insert_outbound_record("returned", "old")
    client = _api_client()
    preview = client.post(
        "/api/inbound/preview",
        json={"text": "fresh----pw\nreturned----pw2\nbad-line"},
    ).json()["rows"]

    response = client.post(
        "/api/inbound/commit",
        json={
            "rows": [
                {"clientId": row["clientId"], "line": row["line"]}
                for row in preview
            ],
            "approvedPendingClientIds": ["line-2"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["successCount"] == 2
    assert payload["errorCount"] == 1
    assert db.exists_in_inventory("fresh")
    assert db.exists_in_inventory("returned")


def test_api_fifo_preview_and_commit() -> None:
    _reset_inventory()
    db.insert_account("first", "p1")
    db.insert_account("second", "p2")
    client = _api_client()

    preview = client.post("/api/outbound/fifo/preview", json={"quantity": 2})
    assert preview.status_code == 200
    assert [row["username"] for row in preview.json()["rows"]] == ["first", "second"]

    committed = client.post("/api/outbound/fifo/commit", json={"quantity": 1})
    assert committed.status_code == 200
    payload = committed.json()
    assert payload["quantity"] == 1
    assert payload["clipboardText"] == "first----p1"
    assert not db.exists_in_inventory("first")
    assert db.exists_in_inventory("second")


def test_account_notes_table_exists() -> None:
    with db._connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'account_notes'"
        ).fetchone()
    assert row is not None


def test_set_account_note_empty_skip() -> None:
    _reset_inventory()
    db.set_account_note("user_a", "keep")
    assert db.set_account_note("user_a", "") == "keep"
    assert db.set_account_note("user_a", None) == "keep"
    assert db.get_account_notes(["user_a"])["user_a"] == "keep"


def test_set_account_note_no_overwrite() -> None:
    _reset_inventory()
    db.set_account_note("user_b", "first")
    assert db.set_account_note("user_b", "second") == "first"
    assert db.get_account_notes(["user_b"])["user_b"] == "first"


def test_set_account_note_overwrite() -> None:
    _reset_inventory()
    db.set_account_note("user_c", "first")
    assert db.set_account_note("user_c", "second", overwrite=True) == "second"
    assert db.set_account_note("user_c", "", overwrite=True) == ""


def test_search_inventory_by_note() -> None:
    _reset_inventory()
    db.insert_account("note_user", "pw")
    db.set_account_note("note_user", "VIP客户")
    rows = db.search_inventory("VIP")
    assert len(rows) == 1
    assert rows[0]["username"] == "note_user"
    assert rows[0]["note"] == "VIP客户"


def test_search_outbound_history_by_note() -> None:
    _reset_inventory()
    db.insert_account("hist_note", "pw")
    db.set_account_note("hist_note", "历史备注")
    db.outbound_by_username("hist_note")
    rows = db.search_outbound_history("历史备注")
    assert len(rows) == 1
    assert rows[0]["username"] == "hist_note"


def test_list_inbound_history_by_note() -> None:
    _reset_inventory()
    db.insert_account("in_note", "pw")
    db.set_account_note("in_note", "入库标签")
    rows = db.list_inbound_history(query="入库标签")
    assert len(rows) == 1
    assert rows[0]["username"] == "in_note"
    assert rows[0]["note"] == "入库标签"


def test_list_outbound_history_by_note() -> None:
    _reset_inventory()
    db.insert_account("out_note", "pw")
    db.set_account_note("out_note", "出库标签")
    db.outbound_by_username("out_note")
    rows = db.list_outbound_history(query="出库标签")
    assert len(rows) == 1
    assert rows[0]["username"] == "out_note"
    assert rows[0]["note"] == "出库标签"


def test_api_inbound_commit_with_note() -> None:
    _reset_inventory()
    client = _api_client()
    response = client.post(
        "/api/inbound/commit",
        json={
            "rows": [
                {
                    "clientId": "line-1",
                    "line": "note_in----pw",
                    "note": "客户A",
                }
            ],
            "approvedPendingClientIds": [],
        },
    )
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["status"] == "success"
    assert row["note"] == "客户A"

    inventory = client.get("/api/inventory").json()["records"]
    assert inventory[0]["note"] == "客户A"

    history = client.get("/api/inbound/history", params={"q": "客户A"}).json()["records"]
    assert len(history) == 1
    assert history[0]["note"] == "客户A"

    search = client.get("/api/search", params={"q": "客户A"}).json()["results"]
    assert len(search) == 1
    assert search[0]["account"]["note"] == "客户A"


def test_api_fifo_commit_with_note() -> None:
    _reset_inventory()
    db.insert_account("fifo_note", "pw")
    db.set_account_note("fifo_note", "FIFO备注")
    client = _api_client()

    committed = client.post(
        "/api/outbound/fifo/commit",
        json={
            "quantity": 1,
            "notes": [
                {
                    "username": "fifo_note",
                    "note": "出库后备注",
                    "overwriteNote": True,
                }
            ],
        },
    )
    assert committed.status_code == 200
    assert not db.exists_in_inventory("fifo_note")

    history = client.get("/api/outbound/history", params={"q": "出库后备注"}).json()[
        "records"
    ]
    assert len(history) == 1
    assert history[0]["note"] == "出库后备注"

    search = client.get("/api/search", params={"q": "出库后备注"}).json()["results"]
    assert len(search) == 1
    assert search[0]["source"] == "history"


def test_api_outbound_paste_with_note() -> None:
    _reset_inventory()
    db.insert_account("paste_note", "pw")
    client = _api_client()
    response = client.post(
        "/api/outbound-paste/commit",
        json={
            "rows": [
                {
                    "clientId": "line-1",
                    "line": "paste_note----pw",
                    "note": "粘贴出库备注",
                }
            ]
        },
    )
    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["status"] == "success"
    assert row["note"] == "粘贴出库备注"
    assert db.get_account_notes(["paste_note"])["paste_note"] == "粘贴出库备注"


def test_api_note_no_overwrite_without_flag() -> None:
    _reset_inventory()
    db.set_account_note("keep_note", "原始备注")
    client = _api_client()
    response = client.post(
        "/api/inbound/commit",
        json={
            "rows": [
                {
                    "clientId": "line-1",
                    "line": "keep_note----pw2",
                    "note": "新备注",
                }
            ],
            "approvedPendingClientIds": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["rows"][0]["note"] == "原始备注"


def test_api_note_overwrite_with_flag() -> None:
    _reset_inventory()
    db.set_account_note("overwrite_note", "旧备注")
    client = _api_client()
    response = client.post(
        "/api/inbound/commit",
        json={
            "rows": [
                {
                    "clientId": "line-1",
                    "line": "overwrite_note----pw2",
                    "note": "新备注",
                    "overwriteNote": True,
                }
            ],
            "approvedPendingClientIds": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["rows"][0]["note"] == "新备注"


def test_api_fifo_preview_new_head_after_commit() -> None:
    _reset_inventory()
    db.insert_account("head_a", "p1")
    db.insert_account("head_b", "p2")
    client = _api_client()

    first_preview = client.post("/api/outbound/fifo/preview", json={"quantity": 1})
    assert first_preview.status_code == 200
    assert first_preview.json()["rows"][0]["username"] == "head_a"

    committed = client.post("/api/outbound/fifo/commit", json={"quantity": 1})
    assert committed.status_code == 200

    second_preview = client.post("/api/outbound/fifo/preview", json={"quantity": 1})
    assert second_preview.status_code == 200
    assert second_preview.json()["rows"][0]["username"] == "head_b"


def test_api_fifo_preview_reflects_database_switch() -> None:
    _reset_inventory()
    db.insert_account("default_head", "pw")
    default = db.get_active_database_info()
    client = _api_client()

    default_preview = client.post("/api/outbound/fifo/preview", json={"quantity": 1})
    assert default_preview.status_code == 200
    assert default_preview.json()["rows"][0]["username"] == "default_head"

    created = client.post("/api/databases", json={"name": "FIFO 切换库"})
    assert created.status_code == 200
    created_id = created.json()["id"]
    db.insert_account("switched_head", "pw2")

    switched_preview = client.post("/api/outbound/fifo/preview", json={"quantity": 1})
    assert switched_preview.status_code == 200
    assert switched_preview.json()["rows"][0]["username"] == "switched_head"

    activated = client.post(f"/api/databases/{default['id']}/activate")
    assert activated.status_code == 200

    restored_preview = client.post("/api/outbound/fifo/preview", json={"quantity": 1})
    assert restored_preview.status_code == 200
    assert restored_preview.json()["rows"][0]["username"] == "default_head"

    with mock.patch.dict("os.environ", {"UPDATE_ADMIN_TOKEN": "secret"}):
        deleted = client.delete(
            f"/api/databases/{created_id}",
            headers={"X-Update-Token": "secret"},
        )
        assert deleted.status_code == 200


def test_api_fifo_commit_multiple_notes() -> None:
    _reset_inventory()
    for index in range(5):
        db.insert_account(f"multi_{index}", f"pw{index}")
    client = _api_client()

    preview = client.post("/api/outbound/fifo/preview", json={"quantity": 5})
    assert preview.status_code == 200
    rows = preview.json()["rows"]
    assert len(rows) == 5

    notes = [
        {
            "username": row["username"],
            "note": f"批量备注-{index}",
            "overwriteNote": True,
        }
        for index, row in enumerate(rows)
    ]
    committed = client.post(
        "/api/outbound/fifo/commit",
        json={"quantity": 5, "notes": notes},
    )
    assert committed.status_code == 200
    assert committed.json()["quantity"] == 5

    history = client.get("/api/outbound/history", params={"q": "批量备注-0"}).json()[
        "records"
    ]
    assert len(history) == 1
    assert history[0]["username"] == "multi_0"
    assert history[0]["note"] == "批量备注-0"

    history_last = client.get(
        "/api/outbound/history", params={"q": "批量备注-4"}
    ).json()["records"]
    assert len(history_last) == 1
    assert history_last[0]["username"] == "multi_4"
    assert history_last[0]["note"] == "批量备注-4"


def test_api_outbound_by_username_with_note_searchable() -> None:
    _reset_inventory()
    db.insert_account("search_out", "pw")
    db.set_account_note("search_out", "原始备注")
    client = _api_client()

    response = client.post(
        "/api/outbound/by-username",
        json={
            "username": "search_out",
            "note": "搜索出库备注",
            "overwriteNote": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["account"]["note"] == "搜索出库备注"

    history = client.get("/api/outbound/history", params={"q": "搜索出库备注"}).json()[
        "records"
    ]
    assert len(history) == 1
    assert history[0]["username"] == "search_out"
    assert history[0]["note"] == "搜索出库备注"

    search = client.get("/api/search", params={"q": "搜索出库备注"}).json()["results"]
    assert len(search) == 1
    assert search[0]["source"] == "history"
    assert search[0]["account"]["note"] == "搜索出库备注"


def test_api_outbound_by_username_note_without_overwrite() -> None:
    _reset_inventory()
    db.insert_account("keep_out", "pw")
    db.set_account_note("keep_out", "保留备注")
    client = _api_client()

    response = client.post(
        "/api/outbound/by-username",
        json={"username": "keep_out", "note": "新备注"},
    )
    assert response.status_code == 200
    assert response.json()["account"]["note"] == "保留备注"

    history = client.get("/api/outbound/history", params={"q": "保留备注"}).json()[
        "records"
    ]
    assert len(history) == 1
    assert history[0]["note"] == "保留备注"


def _normalize_note(value: str | None) -> str:
    return (value or "").strip()


def _notes_differ(existing: str | None, new: str | None) -> bool:
    existing_norm = _normalize_note(existing)
    draft = _normalize_note(new)
    if not existing_norm or not draft:
        return False
    return existing_norm != draft


def _effective_overwrite_for_commit(
    existing: str | None, new: str | None, overwrite: bool
) -> bool:
    if not _notes_differ(existing, new):
        return False
    return overwrite


def _should_reset_topbar_draft(
    prev_query: str,
    prev_hit: str | None,
    next_query: str,
    next_hit: str | None,
) -> bool:
    if not _normalize_note(next_query):
        return True
    if _normalize_note(prev_query) != _normalize_note(next_query):
        return True
    if prev_hit != next_hit:
        return True
    return False


def test_note_overwrite_logic_mirror() -> None:
    assert not _notes_differ(None, "new")
    assert not _notes_differ("same", "same")
    assert _notes_differ("old", "new")
    assert not _effective_overwrite_for_commit("old", "new", False)
    assert _effective_overwrite_for_commit("old", "new", True)
    assert not _effective_overwrite_for_commit("same", "same", True)
    assert _should_reset_topbar_draft("user", "alice", "user", "bob")
    assert not _should_reset_topbar_draft("user", "alice", "user", "alice")
    assert _should_reset_topbar_draft("alice", "alice", "", None)


def test_web_note_overwrite_vitest() -> None:
    web_dir = ROOT / "web"
    if not (web_dir / "package.json").is_file():
        raise AssertionError("web/package.json missing")
    result = subprocess.run(
        ["npm", "run", "test"],
        cwd=web_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "web vitest failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_api_search_inventory_and_history() -> None:
    _reset_inventory()
    db.insert_account(
        "stock_search",
        "p1",
        email="stock@mail.test",
        url="https://stock.example",
    )
    db.insert_account(
        "history_search",
        "p2",
        email="history@mail.test",
        url="https://history.example",
    )
    db.outbound_by_username("history_search")
    client = _api_client()

    stock_response = client.get("/api/search", params={"q": "stock@mail"})
    assert stock_response.status_code == 200
    stock_results = stock_response.json()["results"]
    assert len(stock_results) == 1
    assert stock_results[0]["source"] == "inventory"
    assert stock_results[0]["account"]["username"] == "stock_search"
    assert stock_results[0]["account"]["inboundAt"]

    history_response = client.get("/api/search", params={"q": "history.example"})
    assert history_response.status_code == 200
    history_results = history_response.json()["results"]
    assert len(history_results) == 1
    assert history_results[0]["source"] == "history"
    assert history_results[0]["account"]["username"] == "history_search"
    assert history_results[0]["account"]["inboundAt"]
    assert history_results[0]["account"]["outboundAt"]

    empty_response = client.get("/api/search", params={"q": ""})
    assert empty_response.status_code == 200
    assert empty_response.json()["results"] == []

    db.insert_account("100%api", "p3")
    like_response = client.get("/api/search", params={"q": "%api"})
    assert like_response.status_code == 200
    like_results = like_response.json()["results"]
    assert len(like_results) == 1
    assert like_results[0]["account"]["username"] == "100%api"


def test_api_inventory_empty() -> None:
    _reset_inventory()
    client = _api_client()

    response = client.get("/api/inventory")
    assert response.status_code == 200
    assert response.json()["records"] == []


def test_api_inventory_real_records_ordered() -> None:
    _reset_inventory()
    db.insert_account(
        "first_inventory",
        "pw1",
        email="first@mail.test",
        email_password="mailpw1",
        url="https://first.example",
    )
    db.insert_account("second_inventory", "pw2", email="second@mail.test")
    db.insert_account("third_inventory", "pw3")

    with db._connect() as conn:
        conn.execute(
            "UPDATE accounts SET created_at = ? WHERE username = ?",
            ("2026-01-01 10:00:00", "first_inventory"),
        )
        conn.execute(
            "UPDATE accounts SET created_at = ? WHERE username = ?",
            ("2026-01-02 10:00:00", "second_inventory"),
        )
        conn.execute(
            "UPDATE accounts SET created_at = ? WHERE username = ?",
            ("2026-01-02 10:00:00", "third_inventory"),
        )

    client = _api_client()
    response = client.get("/api/inventory")
    assert response.status_code == 200
    records = response.json()["records"]
    assert [record["username"] for record in records] == [
        "first_inventory",
        "second_inventory",
        "third_inventory",
    ]
    first = records[0]
    assert first["password"] == "pw1"
    assert first["email"] == "first@mail.test"
    assert first["emailPassword"] == "mailpw1"
    assert first["url"] == "https://first.example"
    assert first["inboundAt"] == "2026-01-01 10:00:00"


def test_inbound_record_created_on_insert() -> None:
    _reset_inventory()
    db.insert_account("inbound_user", "pw1", email="in@mail.test")
    assert db.count_inbound_records() == 1
    assert db.count_inventory() == 1


def test_inbound_history_persists_after_outbound() -> None:
    _reset_inventory()
    db.insert_account("persist_user", "pw")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("persist_user",),
        ).fetchone()["inbound_record_id"]
    db.outbound_by_username("persist_user")
    assert not db.exists_in_inventory("persist_user")
    assert db.count_inbound_records() == 1
    inbound_rows = db.list_inbound_history()
    assert len(inbound_rows) == 1
    assert inbound_rows[0]["username"] == "persist_user"
    assert inbound_rows[0]["id"] == inbound_id


def test_reinbound_creates_new_inbound_record() -> None:
    _reset_inventory()
    db.insert_account("rein_user", "pw1")
    with db._connect() as conn:
        first_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("rein_user",),
        ).fetchone()["inbound_record_id"]
    db.outbound_by_username("rein_user")
    db.insert_account("rein_user", "pw2")
    with db._connect() as conn:
        second_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("rein_user",),
        ).fetchone()["inbound_record_id"]
    assert first_id != second_id
    assert db.count_inbound_records() == 2


def test_api_reinbound_from_history_ignores_separator_rules() -> None:
    _reset_inventory()
    client = _api_client()
    custom = db.create_separator_rule("自定义", "::::")
    db.update_separator_rule("builtin-default", enabled=False)
    try:
        db.insert_outbound_record("user----name", "secret", email="e@test.com")
        record_id = db.list_outbound_history()[0]["id"]

        response = client.post(f"/api/outbound/history/{record_id}/reinbound")

        assert response.status_code == 200
        assert db.exists_in_inventory("user----name")
        assert db.count_outbound_records() == 1
    finally:
        db.update_separator_rule("builtin-default", enabled=True)
        db.delete_separator_rule(custom["id"])


def test_api_reinbound_from_history_duplicate_username() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("dup_user", "pw1")
    db.outbound_by_username("dup_user")
    record_id = db.list_outbound_history()[0]["id"]
    db.insert_account("dup_user", "pw2")

    inventory_before = db.count_inventory()
    outbound_before = db.count_outbound_records()
    inbound_before = db.count_inbound_records()

    response = client.post(f"/api/outbound/history/{record_id}/reinbound")

    assert response.status_code == 400
    assert "已在库存中" in response.json()["detail"]
    assert db.count_inventory() == inventory_before
    assert db.count_outbound_records() == outbound_before
    assert db.count_inbound_records() == inbound_before


def test_api_reinbound_from_history_preserves_outbound_and_creates_inbound() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("rein_user", "pw1")
    with db._connect() as conn:
        first_inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("rein_user",),
        ).fetchone()["inbound_record_id"]
    db.outbound_by_username("rein_user")
    record_id = db.list_outbound_history()[0]["id"]
    outbound_before = db.count_outbound_records()

    response = client.post(f"/api/outbound/history/{record_id}/reinbound")

    assert response.status_code == 200
    assert db.count_outbound_records() == outbound_before
    assert db.exists_in_inventory("rein_user")
    assert db.count_inbound_records() == 2
    with db._connect() as conn:
        second_inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("rein_user",),
        ).fetchone()["inbound_record_id"]
    assert first_inbound_id != second_inbound_id
    outbound_rows = db.list_outbound_history()
    assert len(outbound_rows) == 1
    assert outbound_rows[0]["id"] == record_id
    assert outbound_rows[0]["username"] == "rein_user"


def test_outbound_from_inbound_history_in_inventory() -> None:
    _reset_inventory()
    db.insert_account("hist_out_user", "pw1", email="out@test.com")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("hist_out_user",),
        ).fetchone()["inbound_record_id"]
    assert db.exists_in_inventory("hist_out_user")

    row = db.outbound_from_inbound_history(inbound_id)

    assert not db.exists_in_inventory("hist_out_user")
    assert db.count_outbound_records() == 1
    assert row["username"] == "hist_out_user"
    assert row["inbound_record_id"] == inbound_id
    with db._connect() as conn:
        deleted = conn.execute(
            "SELECT 1 FROM accounts WHERE inbound_record_id = ?",
            (inbound_id,),
        ).fetchone()
        assert deleted is None


def test_outbound_from_inbound_history_not_in_inventory() -> None:
    _reset_inventory()
    db.insert_account("gone_user", "pw1")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("gone_user",),
        ).fetchone()["inbound_record_id"]
        conn.execute("DELETE FROM accounts WHERE username = ?", ("gone_user",))
    assert not db.exists_in_inventory("gone_user")
    outbound_before = db.count_outbound_records()

    row = db.outbound_from_inbound_history(inbound_id)

    assert db.count_outbound_records() == outbound_before + 1
    assert row["inbound_record_id"] == inbound_id
    assert row["username"] == "gone_user"


def test_outbound_from_inbound_history_already_outbound() -> None:
    _reset_inventory()
    db.insert_account("dup_out", "pw1")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("dup_out",),
        ).fetchone()["inbound_record_id"]
    db.outbound_by_username("dup_out")

    try:
        db.outbound_from_inbound_history(inbound_id)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "已出库" in str(exc)


def test_api_outbound_from_inbound_history() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("api_hist_out", "pw1", email="api@test.com", url="https://x.com")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("api_hist_out",),
        ).fetchone()["inbound_record_id"]

    response = client.post(f"/api/inbound/history/{inbound_id}/outbound")
    assert response.status_code == 200
    payload = response.json()
    expected = format_account("api_hist_out", "pw1", "api@test.com", None, "https://x.com")
    assert payload["clipboardText"] == expected
    assert payload["record"]["username"] == "api_hist_out"
    assert payload["record"]["inboundRecordId"] == str(inbound_id)
    assert not db.exists_in_inventory("api_hist_out")


def test_api_outbound_from_inbound_history_already_outbound() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("api_dup_out", "pw1")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("api_dup_out",),
        ).fetchone()["inbound_record_id"]
    db.outbound_by_username("api_dup_out")

    response = client.post(f"/api/inbound/history/{inbound_id}/outbound")
    assert response.status_code == 400
    assert "已出库" in response.json()["detail"]


def test_api_reinbound_from_history_clipboard_text() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("clip_rein", "pw1", email="clip@test.com")
    db.outbound_by_username("clip_rein")
    record_id = db.list_outbound_history()[0]["id"]
    outbound_before = db.count_outbound_records()

    response = client.post(f"/api/outbound/history/{record_id}/reinbound")

    assert response.status_code == 200
    payload = response.json()
    assert payload["clipboardText"] == format_account(
        "clip_rein", "pw1", "clip@test.com", None, None
    )
    assert payload["account"]["username"] == "clip_rein"
    assert db.count_outbound_records() == outbound_before


def test_history_shortcut_notes_searchable() -> None:
    _reset_inventory()
    client = _api_client()
    db.insert_account("note_shortcut", "pw1")
    db.set_account_note("note_shortcut", "快捷标签")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("note_shortcut",),
        ).fetchone()["inbound_record_id"]

    outbound = client.post(f"/api/inbound/history/{inbound_id}/outbound")
    assert outbound.status_code == 200

    inbound_rows = db.list_inbound_history(query="快捷标签")
    outbound_rows = db.list_outbound_history(query="快捷标签")
    assert any(row["username"] == "note_shortcut" for row in inbound_rows)
    assert any(row["username"] == "note_shortcut" for row in outbound_rows)

    db.insert_outbound_record("note_rein", "pw2")
    db.set_account_note("note_rein", "重新入库标签")
    rein_id = db.list_outbound_history(query="note_rein")[0]["id"]
    reinbound = client.post(f"/api/outbound/history/{rein_id}/reinbound")
    assert reinbound.status_code == 200
    assert db.search_inventory("重新入库标签")


def test_list_inbound_history_has_outbound() -> None:
    _reset_inventory()
    db.insert_account("has_out_flag", "pw1")
    with db._connect() as conn:
        inbound_id = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("has_out_flag",),
        ).fetchone()["inbound_record_id"]
    db.insert_account("no_out_flag", "pw2")

    rows_before = {row["username"]: row for row in db.list_inbound_history()}
    assert rows_before["has_out_flag"]["has_outbound"] is False
    assert rows_before["no_out_flag"]["has_outbound"] is False

    db.outbound_by_username("has_out_flag")
    rows_after = {row["username"]: row for row in db.list_inbound_history()}
    assert rows_after["has_out_flag"]["has_outbound"] is True
    assert rows_after["no_out_flag"]["has_outbound"] is False


def test_migrate_inbound_history_backfill() -> None:
    _reset_inventory()
    with db._connect() as conn:
        conn.execute(
            """
            INSERT INTO accounts (username, password, email, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("legacy_stock", "pw", "legacy@mail.test", "2026-01-10 09:00:00"),
        )
        conn.execute(
            """
            INSERT INTO outbound_records (
                username, password, inbound_at, outbound_at
            )
            VALUES (?, ?, ?, ?)
            """,
            ("legacy_out", "pw2", "2026-01-05 08:00:00", "2026-01-06 10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO outbound_records (
                username, password, inbound_at, outbound_at
            )
            VALUES (?, ?, ?, ?)
            """,
            ("direct_out", "pw3", "2026-01-07 12:00:00", "2026-01-07 12:00:00"),
        )

    with db._connect() as conn:
        db._migrate_inbound_history(conn)

    with db._connect() as conn:
        stock = conn.execute(
            "SELECT inbound_record_id FROM accounts WHERE username = ?",
            ("legacy_stock",),
        ).fetchone()
        inventory_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("legacy_out",),
        ).fetchone()
        direct_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("direct_out",),
        ).fetchone()

    assert stock["inbound_record_id"] is not None
    assert inventory_out["inbound_record_id"] is not None
    assert direct_out["inbound_record_id"] is None
    assert db.count_inbound_records() == 2


def test_outbound_paths_set_inbound_record_id() -> None:
    _reset_inventory()
    db.insert_account("fifo_user", "pw1")
    db.insert_account("byname_user", "pw2")
    db.insert_account("paste_user", "pw3", email="paste@mail.test")

    fifo = db.outbound_oldest_many(1)[0]
    assert fifo["username"] == "fifo_user"
    with db._connect() as conn:
        fifo_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("fifo_user",),
        ).fetchone()
        assert fifo_out["inbound_record_id"] is not None

    db.outbound_by_username("byname_user")
    with db._connect() as conn:
        byname_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("byname_user",),
        ).fetchone()
        assert byname_out["inbound_record_id"] is not None

    db.commit_outbound_paste_rows(
        [
            {
                "client_id": "line-1",
                "line": "paste_user----x",
                "username": "paste_user",
                "password": "x",
                "email": None,
                "email_password": None,
                "url": None,
            },
            {
                "client_id": "line-2",
                "line": "direct_user----direct_pw",
                "username": "direct_user",
                "password": "direct_pw",
                "email": None,
                "email_password": None,
                "url": None,
            },
        ]
    )
    with db._connect() as conn:
        paste_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("paste_user",),
        ).fetchone()
        direct_out = conn.execute(
            """
            SELECT inbound_record_id
            FROM outbound_records
            WHERE username = ?
            """,
            ("direct_user",),
        ).fetchone()
    assert paste_out["inbound_record_id"] is not None
    assert direct_out["inbound_record_id"] is None


def test_history_filters_parse_dates() -> None:
    import history_filters as hf

    assert hf.parse_date_token("2026-06-02") == hf.date(2026, 6, 2)
    assert hf.parse_date_token("2026 6 2") == hf.date(2026, 6, 2)
    assert hf.parse_date_token("2026/6/2") == hf.date(2026, 6, 2)
    assert hf.parse_date_token("2026-6-2") == hf.date(2026, 6, 2)

    single = hf.parse_range_token("2026-06-02")
    assert single is not None
    assert single.start == hf.date(2026, 6, 2)
    assert single.end == hf.date(2026, 6, 2)

    span = hf.parse_range_token("2026-06-01..2026-06-03")
    assert span is not None
    assert span.start == hf.date(2026, 6, 1)
    assert span.end == hf.date(2026, 6, 3)


def test_list_inbound_history_date_filters() -> None:
    _reset_inventory()
    db.insert_account("day_a", "pw")
    db.insert_account("day_b", "pw")
    with db._connect() as conn:
        conn.execute(
            "UPDATE inbound_records SET inbound_at = ? WHERE username = ?",
            ("2026-06-01 10:00:00", "day_a"),
        )
        conn.execute(
            "UPDATE inbound_records SET inbound_at = ? WHERE username = ?",
            ("2026-06-03 10:00:00", "day_b"),
        )

    single = db.list_inbound_history(range_tokens=["2026-06-01"])
    assert [row["username"] for row in single] == ["day_a"]

    span = db.list_inbound_history(range_tokens=["2026-06-01..2026-06-02"])
    assert [row["username"] for row in span] == ["day_a"]

    text_date = db.list_inbound_history(query="2026 6 3")
    assert [row["username"] for row in text_date] == ["day_b"]


def test_list_unified_history_types() -> None:
    _reset_inventory()
    db.insert_account("unified_in", "pw")
    db.outbound_by_username("unified_in")
    db.insert_account("unified_still", "pw2")

    all_rows = db.list_unified_history(history_type="all")
    assert len(all_rows) == 3
    assert {row["type"] for row in all_rows} == {"inbound", "outbound"}

    inbound_rows = db.list_unified_history(history_type="inbound")
    assert len(inbound_rows) == 2
    assert all(row["type"] == "inbound" for row in inbound_rows)

    outbound_rows = db.list_unified_history(history_type="outbound")
    assert len(outbound_rows) == 1
    assert outbound_rows[0]["type"] == "outbound"


def test_api_history_endpoints_and_filters() -> None:
    _reset_inventory()
    db.insert_account("hist_in", "pw", email="hist@mail.test")
    db.outbound_by_username("hist_in")
    db.insert_account("hist_still", "pw2")
    with db._connect() as conn:
        conn.execute(
            "UPDATE inbound_records SET inbound_at = ? WHERE username = ?",
            ("2026-06-01 10:00:00", "hist_in"),
        )
        conn.execute(
            "UPDATE inbound_records SET inbound_at = ? WHERE username = ?",
            ("2026-06-02 10:00:00", "hist_still"),
        )
        conn.execute(
            "UPDATE outbound_records SET outbound_at = ? WHERE username = ?",
            ("2026-06-01 11:00:00", "hist_in"),
        )

    client = _api_client()

    inbound_response = client.get("/api/inbound/history")
    assert inbound_response.status_code == 200
    assert len(inbound_response.json()["records"]) == 2

    outbound_response = client.get("/api/outbound/history")
    assert outbound_response.status_code == 200
    assert len(outbound_response.json()["records"]) == 1

    all_response = client.get("/api/history", params={"type": "all"})
    assert all_response.status_code == 200
    assert len(all_response.json()["records"]) == 3

    inbound_only = client.get("/api/history", params={"type": "inbound"})
    assert len(inbound_only.json()["records"]) == 2

    outbound_only = client.get("/api/history", params={"type": "outbound"})
    assert len(outbound_only.json()["records"]) == 1

    date_filter = client.get(
        "/api/inbound/history",
        params={"ranges": ["2026-06-01"]},
    )
    assert [row["username"] for row in date_filter.json()["records"]] == ["hist_in"]

    text_date = client.get("/api/inbound/history", params={"q": "2026 6 2"})
    assert [row["username"] for row in text_date.json()["records"]] == ["hist_still"]

    search_q = client.get("/api/history", params={"q": "hist@mail.test"})
    assert len(search_q.json()["records"]) == 2


def test_api_outbound_history_empty() -> None:
    _reset_inventory()
    client = _api_client()

    response = client.get("/api/outbound/history")
    assert response.status_code == 200
    assert response.json()["records"] == []


def test_api_outbound_history_real_records_ordered() -> None:
    _reset_inventory()
    db.insert_account(
        "first_history",
        "pw1",
        email="first@mail.test",
        email_password="mailpw1",
        url="https://first.example",
    )
    db.insert_account("second_history", "pw2", email="second@mail.test")
    db.insert_account("third_history", "pw3")
    db.outbound_by_username("first_history")
    db.outbound_by_username("second_history")
    db.outbound_by_username("third_history")

    with db._connect() as conn:
        conn.execute(
            "UPDATE outbound_records SET outbound_at = ? WHERE username = ?",
            ("2026-01-01 10:00:00", "first_history"),
        )
        conn.execute(
            "UPDATE outbound_records SET outbound_at = ? WHERE username = ?",
            ("2026-01-02 10:00:00", "second_history"),
        )
        conn.execute(
            "UPDATE outbound_records SET outbound_at = ? WHERE username = ?",
            ("2026-01-02 10:00:00", "third_history"),
        )

    client = _api_client()
    response = client.get("/api/outbound/history")
    assert response.status_code == 200
    records = response.json()["records"]
    assert [record["username"] for record in records] == [
        "third_history",
        "second_history",
        "first_history",
    ]
    first = records[2]
    assert first["password"] == "pw1"
    assert first["email"] == "first@mail.test"
    assert first["emailPassword"] == "mailpw1"
    assert first["url"] == "https://first.example"
    assert first["inboundAt"]
    assert first["outboundAt"] == "2026-01-01 10:00:00"


def test_api_direct_outbound_null_inbound_at() -> None:
    _reset_inventory()
    db.insert_outbound_record("direct_api", "pw")
    client = _api_client()

    response = client.get("/api/outbound/history")
    assert response.status_code == 200
    record = next(
        row for row in response.json()["records"] if row["username"] == "direct_api"
    )
    assert record["inboundAt"] is None
    assert record["inboundRecordId"] is None


def test_api_inventory_outbound_has_inbound_at() -> None:
    _reset_inventory()
    db.insert_account("inv_out", "pw", email="inv@mail.test")
    db.outbound_by_username("inv_out")
    client = _api_client()

    response = client.get("/api/outbound/history")
    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["username"] == "inv_out"
    assert record["inboundAt"]
    assert record["inboundRecordId"]


def test_api_unified_history_direct_outbound_date_filter() -> None:
    _reset_inventory()
    db.insert_outbound_record("direct_filter", "pw")
    with db._connect() as conn:
        conn.execute(
            "UPDATE outbound_records SET outbound_at = ? WHERE username = ?",
            ("2026-06-05 14:00:00", "direct_filter"),
        )
    client = _api_client()

    filtered = client.get(
        "/api/history",
        params={"type": "outbound", "ranges": ["2026-06-05"]},
    )
    assert filtered.status_code == 200
    records = filtered.json()["records"]
    assert [row["username"] for row in records] == ["direct_filter"]
    assert records[0]["inboundAt"] is None
    assert records[0]["outboundAt"] == "2026-06-05 14:00:00"


def test_api_outbound_by_username() -> None:
    _reset_inventory()
    db.insert_account("target", "pw", email="target@mail.test")
    client = _api_client()

    response = client.post(
        "/api/outbound/by-username",
        json={"username": "target"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account"]["username"] == "target"
    assert payload["clipboardText"] == "target----pw----target@mail.test----"
    assert not db.exists_in_inventory("target")
    assert db.exists_in_outbound("target")
    assert db.count_outbound_records() == 1

    missing_response = client.post(
        "/api/outbound/by-username",
        json={"username": "target"},
    )
    assert missing_response.status_code == 404
    assert db.count_outbound_records() == 1


def test_api_outbound_paste_commit() -> None:
    _reset_inventory()
    db.insert_account("stocked", "stock_pw", email="stock@mail.test")
    db.insert_outbound_record("old", "old_pw")
    client = _api_client()

    response = client.post(
        "/api/outbound-paste/commit",
        json={
            "rows": [
                {"clientId": "line-1", "line": "stocked----typed_pw"},
                {"clientId": "line-2", "line": "direct----direct_pw----d@mail.test"},
                {"clientId": "line-3", "line": "old----old_pw"},
                {"clientId": "line-4", "line": "bad-line"},
                {"clientId": "line-5", "line": "direct----again"},
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["successCount"] == 2
    assert payload["errorCount"] == 3

    rows = {row["clientId"]: row for row in payload["rows"]}
    assert rows["line-1"]["status"] == "success"
    assert rows["line-1"]["category"] == "inInventory"
    assert rows["line-1"]["password"] == "stock_pw"
    assert rows["line-2"]["status"] == "success"
    assert rows["line-2"]["category"] == "notInInventory"
    assert rows["line-3"]["status"] == "error"
    assert rows["line-3"]["category"] == "inHistory"
    assert rows["line-4"]["status"] == "error"
    assert rows["line-4"]["category"] == "invalid"
    assert rows["line-5"]["status"] == "error"
    assert rows["line-5"]["category"] == "batchDuplicate"
    assert payload["clipboardText"] == "\n".join(
        [
            "stocked----stock_pw----stock@mail.test----",
            "direct----direct_pw----d@mail.test----",
        ]
    )

    assert not db.exists_in_inventory("stocked")
    assert db.exists_in_outbound("stocked")
    assert db.exists_in_outbound("direct")
    assert db.count_outbound_records() == 3

    repeat = client.post(
        "/api/outbound-paste/commit",
        json={"rows": [{"clientId": "line-1", "line": "stocked----stock_pw"}]},
    )
    assert repeat.status_code == 200
    repeat_payload = repeat.json()
    assert repeat_payload["successCount"] == 0
    assert repeat_payload["errorCount"] == 1
    assert repeat_payload["rows"][0]["category"] == "inHistory"
    assert db.count_outbound_records() == 3


def test_api_clipboard_ignore() -> None:
    import api

    client = _api_client()
    response = client.post("/api/clipboard/ignore", json={"text": "skip----pw"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert api._ignored_clipboard_text == "skip----pw"

    response = client.post("/api/clipboard/ignore", json={"text": ""})
    assert response.status_code == 200
    assert api._ignored_clipboard_text is None


def test_api_database_management() -> None:
    _reset_inventory()
    db.insert_account("api_default", "pw")
    default = db.get_active_database_info()
    client = _api_client()

    response = client.get("/api/databases")
    assert response.status_code == 200
    payload = response.json()
    assert payload["activeDatabaseId"] == default["id"]
    assert payload["databases"][0]["inventoryCount"] == 1

    empty = client.post("/api/databases", json={"name": "   "})
    assert empty.status_code == 400

    created = client.post("/api/databases", json={"name": "API 库"})
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["name"] == "API 库"
    assert created_payload["active"] is True
    assert db.count_inventory() == 0

    renamed = client.patch(
        f"/api/databases/{created_payload['id']}",
        json={"name": "API 库 2"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "API 库 2"

    activated = client.post(f"/api/databases/{default['id']}/activate")
    assert activated.status_code == 200
    assert db.exists_in_inventory("api_default")

    empty_clone = client.post(
        f"/api/databases/{default['id']}/clone",
        json={"name": "   "},
    )
    assert empty_clone.status_code == 400

    missing_clone = client.post(
        "/api/databases/missing/clone",
        json={"name": "缺失副本"},
    )
    assert missing_clone.status_code == 400

    cloned = client.post(
        f"/api/databases/{default['id']}/clone",
        json={"name": "API 默认库副本"},
    )
    assert cloned.status_code == 200
    cloned_payload = cloned.json()
    assert cloned_payload["name"] == "API 默认库副本"
    assert cloned_payload["active"] is True
    assert cloned_payload["inventoryCount"] == 1
    db.insert_account("api_clone_only", "pw")

    reactivated = client.post(f"/api/databases/{default['id']}/activate")
    assert reactivated.status_code == 200
    assert not db.exists_in_inventory("api_clone_only")

    with mock.patch.dict("os.environ", {"UPDATE_ADMIN_TOKEN": ""}):
        blocked = client.delete(f"/api/databases/{created_payload['id']}")
        assert blocked.status_code == 403

    with mock.patch.dict("os.environ", {"UPDATE_ADMIN_TOKEN": "secret"}):
        wrong = client.delete(
            f"/api/databases/{created_payload['id']}",
            headers={"X-Update-Token": "bad"},
        )
        assert wrong.status_code == 403

        deleted = client.delete(
            f"/api/databases/{created_payload['id']}",
            headers={"X-Update-Token": "secret"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["id"] == default["id"]

        cloned_deleted = client.delete(
            f"/api/databases/{cloned_payload['id']}",
            headers={"X-Update-Token": "secret"},
        )
        assert cloned_deleted.status_code == 200
        assert cloned_deleted.json()["id"] == default["id"]

        replacement = client.delete(
            f"/api/databases/{default['id']}",
            headers={"X-Update-Token": "secret"},
        )
        assert replacement.status_code == 200
        assert replacement.json()["name"] == "默认数据库"
        assert db.count_inventory() == 0


def test_updater_version_compare() -> None:
    import updater

    assert updater.is_remote_newer("0.1.0", "v0.1.1")
    assert not updater.is_remote_newer("0.1.1", "v0.1.1")
    assert updater.is_remote_newer("0.0.0-dev", "v0.1.1")
    assert not updater.is_remote_newer("0.1.1", "latest")


def test_updater_release_assets() -> None:
    import updater

    release = {
        "tag_name": "v0.2.0",
        "assets": [
            {
                "name": "account-inventory-web-windows.zip",
                "browser_download_url": "https://example.com/app.zip",
            },
            {
                "name": "account-inventory-web-windows.zip.sha256",
                "browser_download_url": "https://example.com/app.zip.sha256",
            },
        ],
    }

    assert updater.find_asset_url(release, updater.RELEASE_ZIP_NAME) == "https://example.com/app.zip"
    assert updater.find_asset_url(release, updater.RELEASE_SHA256_NAME) == "https://example.com/app.zip.sha256"
    assert updater.find_asset_url(release, "missing.zip") is None


def test_updater_ignores_github_token_env() -> None:
    import updater

    class DummyResponse:
        status_code = 200
        headers: dict[str, str] = {}
        url = "https://github.com/owner/repo/releases/tag/v0.2.0"

        def raise_for_status(self) -> None:
            return None

    with mock.patch.dict("os.environ", {"UPDATER_GITHUB_TOKEN": "token-123"}), mock.patch(
        "updater.requests.get",
        return_value=DummyResponse(),
    ) as get_mock:
        release = updater.github_latest_release("owner/repo")

    headers = get_mock.call_args.kwargs["headers"]
    url = get_mock.call_args.args[0]
    assert url == "https://github.com/owner/repo/releases/latest"
    assert "Authorization" not in headers
    assert get_mock.call_args.kwargs["allow_redirects"] is True
    assert release["tag_name"] == "v0.2.0"


def test_updater_web_latest_without_token() -> None:
    import updater

    class DummyResponse:
        status_code = 200
        headers: dict[str, str] = {}
        url = "https://github.com/owner/repo/releases/tag/v0.1.10"

        def raise_for_status(self) -> None:
            return None

    with mock.patch.dict(
        "os.environ",
        {"UPDATER_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""},
    ), mock.patch("updater.requests.get", return_value=DummyResponse()) as get_mock:
        release = updater.github_latest_release("owner/repo")

    url = get_mock.call_args.args[0]
    assert url == "https://github.com/owner/repo/releases/latest"
    assert "api.github.com" not in url
    assert get_mock.call_args.kwargs["allow_redirects"] is True
    assert release["tag_name"] == "v0.1.10"
    assert updater.find_asset_url(release, updater.RELEASE_ZIP_NAME) == (
        "https://github.com/owner/repo/releases/download/v0.1.10/account-inventory-web-windows.zip"
    )


def test_updater_release_tag_parse_and_download_urls() -> None:
    import updater

    assert updater.parse_github_release_tag_from_url(
        "https://github.com/owner/repo/releases/tag/v0.1.10?x=1"
    ) == "v0.1.10"
    assert updater.github_asset_download_url("owner/repo", "v0.1.10", updater.RELEASE_SHA256_NAME) == (
        "https://github.com/owner/repo/releases/download/v0.1.10/"
        "account-inventory-web-windows.zip.sha256"
    )


def test_update_check_ignores_stale_rate_limit_status() -> None:
    import updater
    import updater_runtime

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "VERSION").write_text("0.1.0", encoding="utf-8")
        updater.write_phase_status(
            root,
            "error",
            "GitHub API rate limit exceeded",
            "failed",
            {
                "repo": "owner/repo",
                "local_version": "0.1.0",
                "github_rate_limit_reset": int(time.time()) + 3600,
            },
        )
        with mock.patch.object(
            updater,
            "inspect_latest_release",
            return_value={
                "repo": "owner/repo",
                "local_version": "0.1.0",
                "update_available": True,
                "assets_ready": True,
                "latest_tag": "v0.2.0",
            },
        ) as inspect_mock, mock.patch.dict("os.environ", {"UPDATER_GITHUB_REPO": "owner/repo"}):
            status = updater_runtime.check_latest_update(root)

    inspect_mock.assert_called_once_with("owner/repo", "0.1.0")
    assert status["state"] == "update_available"
    assert status["phase"] == "completed"
    assert status["latest_tag"] == "v0.2.0"


def test_run_update_once_ignores_stale_rate_limit_status() -> None:
    import time
    import updater

    reset_epoch = int(time.time()) + 3600
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "VERSION").write_text("0.1.0", encoding="utf-8")
        updater.write_phase_status(
            root,
            "error",
            "GitHub API rate limit exceeded",
            "failed",
            {
                "repo": "owner/repo",
                "local_version": "0.1.0",
                "github_rate_limit_reset": reset_epoch,
            },
        )
        ctx = updater.RuntimeContext(root, 8000, 0, "python", None, None, Path(sys.executable), "0.1.0")
        with mock.patch.object(
            updater,
            "github_latest_release",
            return_value={
                "tag_name": "v0.1.0",
                "assets": [
                    {
                        "name": updater.RELEASE_ZIP_NAME,
                        "browser_download_url": "https://example.com/app.zip",
                    },
                    {
                        "name": updater.RELEASE_SHA256_NAME,
                        "browser_download_url": "https://example.com/app.zip.sha256",
                    },
                ],
            },
        ) as latest_mock:
            result = updater.run_update_once(ctx, "owner/repo")

    latest_mock.assert_called_once_with("owner/repo")
    assert result["state"] == "idle"
    assert result["message"] == "already up-to-date"


def test_updater_frozen_default_work_dir_is_exe_parent() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "install" / "updater.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", str(exe)):
            assert updater.default_work_dir() == exe.parent


def test_updater_rejects_pyinstaller_temp_work_dir() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        mei_dir = Path(tmp) / "_MEI123456"
        mei_dir.mkdir()
        try:
            updater.validate_work_dir(mei_dir)
        except RuntimeError as exc:
            assert "_MEI123456" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for PyInstaller temp directory")


def test_updater_direct_sidecar_command_uses_install_work_dir() -> None:
    import argparse
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp) / "install"
        sidecar = work_dir / updater.SIDECAR_DIR_NAME / "updater-direct-1.exe"
        args = argparse.Namespace(
            watch=False,
            restore_watch=True,
            interval_hours=24.0,
            work_dir="",
            backend_pid=123,
            port=8000,
            backend_mode="exe",
            backend_executable=str(work_dir / "account-inventory-web.exe"),
            backend_script="",
            python_executable="",
            repo="owner/repo",
        )
        command = updater.build_direct_sidecar_command(args, work_dir, sidecar)

    assert command[0] == str(sidecar)
    assert "--work-dir" in command
    assert command[command.index("--work-dir") + 1] == str(work_dir)
    assert "--restore-watch" not in command


def test_updater_direct_sidecar_handoff_logs_without_argument_collision() -> None:
    import argparse
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp) / "install"
        work_dir.mkdir()
        updater_exe = work_dir / "updater.exe"
        updater_exe.write_bytes(b"")

        args = argparse.Namespace(
            watch=False,
            restore_watch=True,
            interval_hours=24.0,
            work_dir="",
            backend_pid=123,
            port=8000,
            backend_mode="exe",
            backend_executable=str(work_dir / "account-inventory-web.exe"),
            backend_script="",
            python_executable="",
            repo="owner/repo",
        )

        run_result = mock.Mock(returncode=0)
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(
            sys, "executable", str(updater_exe)
        ), mock.patch("shutil.copy2"), mock.patch(
            "subprocess.run", return_value=run_result
        ) as run_mock, mock.patch.object(
            updater.time, "time", return_value=1
        ):
            result = updater.handoff_to_direct_sidecar(args, work_dir)

        assert result == 0
        log_path = work_dir / updater.LOG_FILE_NAME
        assert log_path.exists()
        log_text = log_path.read_text(encoding="utf-8")
        assert "main:handoff" in log_text
        assert "install_work_dir" in log_text
        payload = json.loads(log_text.strip().splitlines()[-1])
        assert payload["stage"] == "main:handoff"
        assert payload["install_work_dir"] == str(work_dir)

        run_mock.assert_called_once()
        command = run_mock.call_args[0][0]
        assert "--work-dir" in command
        assert command[command.index("--work-dir") + 1] == str(work_dir)


def test_updater_print_work_dir_exits_before_update() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with mock.patch.object(sys, "argv", ["updater.py", "--work-dir", str(root), "--print-work-dir-and-exit"]), mock.patch(
            "builtins.print"
        ) as print_mock, mock.patch.object(updater, "run_update_cycle") as cycle_mock:
            assert updater.main() == 0

    print_mock.assert_called_once_with(str(root), flush=True)
    cycle_mock.assert_not_called()


def test_updater_trace_writes_log_file() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        updater.trace(root, "test:stage", value=123)
        lines = (root / updater.LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["stage"] == "test:stage"
    assert payload["value"] == 123


def test_updater_one_shot_lock_skip_writes_status_and_log() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = updater.RuntimeContext(root, 8000, 0, "python", None, None, Path(sys.executable), "0.1.0")
        lock = updater.acquire_single_instance_lock(root)
        try:
            result = updater.run_update_cycle(ctx, "owner/repo", watch=False)
        finally:
            updater.release_single_instance_lock(lock)

        status = json.loads((root / updater.STATUS_FILE_NAME).read_text(encoding="utf-8"))
        log_text = (root / updater.LOG_FILE_NAME).read_text(encoding="utf-8")

    assert result["state"] == "busy"
    assert result["skipped"] is True
    assert status["state"] == "busy"
    assert status["phase"] == "locked"
    assert "lock:exists" in log_text


def test_updater_main_one_shot_runs_once_without_sleep() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with mock.patch.object(sys, "argv", ["updater.py", "--work-dir", str(root)]), mock.patch.object(
            updater,
            "run_update_cycle",
            return_value={"state": "idle", "message": "already up-to-date", "extra": {}},
        ) as cycle_mock, mock.patch("updater.time.sleep") as sleep_mock:
            assert updater.main() == 0

    cycle_mock.assert_called_once()
    sleep_mock.assert_not_called()


def test_update_success_refreshes_status_and_runtime_version() -> None:
    import updater

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "VERSION").write_text("0.1.0", encoding="utf-8")
        (root / updater.RUNTIME_FILE_NAME).write_text(
            json.dumps({"app_version": "0.1.0", "port": 8000}, ensure_ascii=False),
            encoding="utf-8",
        )
        ctx = updater.RuntimeContext(root, 8000, 0, "python", None, None, Path(sys.executable), "0.1.0")

        def fake_prepare(
            ctx_arg: updater.RuntimeContext,
            repo: str,
            latest_tag: str,
            zip_url: str,
            sha_url: str,
            temp_root: Path,
            summary: dict[str, object],
        ) -> updater.PreparedUpdate:
            (root / "VERSION").write_text("0.2.0", encoding="utf-8")
            return updater.PreparedUpdate(repo, latest_tag, root, root, dict(summary))

        with mock.patch.object(
            updater,
            "github_latest_release",
            return_value={
                "tag_name": "v0.2.0",
                "assets": [
                    {"name": updater.RELEASE_ZIP_NAME, "browser_download_url": "https://example.com/app.zip"},
                    {"name": updater.RELEASE_SHA256_NAME, "browser_download_url": "https://example.com/app.zip.sha256"},
                ],
            },
        ), mock.patch.object(updater, "prepare_update", side_effect=fake_prepare), mock.patch.object(
            updater,
            "apply_update",
            return_value={"restart_required": False, "updated_targets": ["VERSION"]},
        ):
            result = updater.run_update_once(ctx, "owner/repo")

        status = json.loads((root / updater.STATUS_FILE_NAME).read_text(encoding="utf-8"))
        runtime = json.loads((root / updater.RUNTIME_FILE_NAME).read_text(encoding="utf-8"))

    assert result["state"] == "updated"
    assert result["extra"]["local_version"] == "0.2.0"
    assert result["extra"]["updated_to_version"] == "0.2.0"
    assert status["local_version"] == "0.2.0"
    assert status["updated_to_version"] == "0.2.0"
    assert runtime["app_version"] == "0.2.0"


def test_download_to_retries_connection_error_and_cleans_part() -> None:
    import updater

    class DummyResponse:
        status_code = 200

        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return [b"ok"]

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "asset.zip"
        with mock.patch(
            "updater.requests.get",
            side_effect=[updater.requests.ConnectionError("reset"), DummyResponse()],
        ) as get_mock, mock.patch("updater.time.sleep") as sleep_mock:
            updater.download_to("https://example.com/asset.zip", output, work_dir=Path(tmp))

        assert output.read_bytes() == b"ok"
        assert not Path(f"{output}.part").exists()
        assert get_mock.call_count == 2
        sleep_mock.assert_called_once()


def test_download_to_retries_503_but_not_404() -> None:
    import requests
    import updater

    class DummyResponse:
        def __init__(self, status_code: int, chunks: list[bytes] | None = None):
            self.status_code = status_code
            self.chunks = chunks or []

        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                response = requests.Response()
                response.status_code = self.status_code
                raise requests.HTTPError(f"{self.status_code} error", response=response)

        def iter_content(self, chunk_size: int) -> list[bytes]:
            return self.chunks

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "asset.zip"
        with mock.patch(
            "updater.requests.get",
            side_effect=[DummyResponse(503), DummyResponse(200, [b"ok"])],
        ) as get_mock, mock.patch("updater.time.sleep"):
            updater.download_to("https://example.com/asset.zip", output, work_dir=Path(tmp))
        assert output.read_bytes() == b"ok"
        assert get_mock.call_count == 2

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "missing.zip"
        with mock.patch("updater.requests.get", return_value=DummyResponse(404)) as get_mock:
            try:
                updater.download_to("https://example.com/missing.zip", output, work_dir=Path(tmp))
            except requests.HTTPError:
                pass
            else:
                raise AssertionError("expected 404 HTTPError")
        assert get_mock.call_count == 1
        assert not output.exists()
        assert not Path(f"{output}.part").exists()


def test_updater_whitelist_blocks_data_and_source() -> None:
    import updater

    assert updater.is_allowed("account-inventory-web.exe")
    assert updater.is_allowed("updater.exe")
    assert updater.is_allowed("VERSION")
    assert updater.is_allowed("start-web.bat")
    assert updater.is_allowed("web/out/index.html")
    assert not updater.is_allowed("data/accounts.db")
    assert not updater.is_allowed(".updater.status.json")
    assert not updater.is_allowed("api.py")
    assert not updater.is_allowed("web/src/app/page.tsx")


def test_update_trigger_token_guard() -> None:
    import updater_runtime

    (updater_runtime.ROOT / ".updater.status.json").unlink(missing_ok=True)
    client = _api_client()
    with mock.patch.dict("os.environ", {}, clear=False):
        with mock.patch.dict("os.environ", {"UPDATE_ADMIN_TOKEN": ""}):
            response = client.post("/api/runtime/trigger-update")
            assert response.status_code == 403

    with mock.patch.dict("os.environ", {"UPDATE_ADMIN_TOKEN": "secret"}):
        response = client.post("/api/runtime/trigger-update", headers={"X-Update-Token": "bad"})
        assert response.status_code == 403

        with mock.patch.object(updater_runtime, "launch_update_once", return_value=1234):
            response = client.post("/api/runtime/trigger-update", headers={"X-Update-Token": "secret"})
            assert response.status_code == 200
            assert response.json()["sidecar_pid"] == 1234


def test_launch_update_once_command() -> None:
    import updater_runtime

    class DummyProcess:
        pid = 4321

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "updater.py").write_text("print('x')", encoding="utf-8")
        (root / "VERSION").write_text("0.1.0", encoding="utf-8")
        updater_runtime.write_runtime_info("127.0.0.1", 8123, root)
        with mock.patch.object(updater_runtime, "stop_update_watcher") as stop, mock.patch.object(
            updater_runtime,
            "_popen_detached",
            return_value=DummyProcess(),
        ) as popen:
            pid = updater_runtime.launch_update_once(root)

    assert pid == 4321
    stop.assert_not_called()
    command = popen.call_args.args[0]
    assert "--restore-watch" not in command
    assert "--watch" not in command
    assert "--work-dir" in command
    assert str(root) in command
    assert "--port" in command
    assert "8123" in command


def test_app_browser_url_localhost() -> None:
    import app as web_app

    assert web_app._browser_url("127.0.0.1", 8000) == "http://127.0.0.1:8000/"
    assert web_app._browser_url("localhost", 8000) == "http://localhost:8000/"


def test_app_browser_url_wildcard_host() -> None:
    import app as web_app

    assert web_app._browser_url("0.0.0.0", 8000) == "http://127.0.0.1:8000/"
    assert web_app._browser_url("::", 8000) == "http://127.0.0.1:8000/"
    assert web_app._browser_url("", 8000) == "http://127.0.0.1:8000/"


def test_app_browser_url_ipv6() -> None:
    import app as web_app

    assert web_app._browser_url("::1", 8000) == "http://[::1]:8000/"
    assert web_app._browser_url("[::1]", 8000) == "http://[::1]:8000/"


def test_app_frontend_file_for_html_route() -> None:
    import app as web_app

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        index = out_dir / "index.html"
        settings = out_dir / "settings.html"
        nested = out_dir / "history" / "index.html"
        index.write_text("home", encoding="utf-8")
        settings.write_text("settings", encoding="utf-8")
        nested.parent.mkdir()
        nested.write_text("history", encoding="utf-8")

        with mock.patch.object(web_app, "WEB_OUT_DIR", out_dir), mock.patch.object(
            web_app,
            "WEB_INDEX",
            index,
        ):
            assert web_app.frontend_file_for_path("settings") == settings.resolve()
            assert web_app.frontend_file_for_path("history") == nested.resolve()
            assert web_app.frontend_file_for_path("missing") == index


def test_app_open_browser_after_port_ready() -> None:
    import app as web_app

    with mock.patch.object(
        web_app,
        "_is_port_open",
        side_effect=[False, True],
    ) as port_open, mock.patch.object(web_app.webbrowser, "open", return_value=True) as open_mock:
        thread = web_app.open_browser_after_start("127.0.0.1", 8000)
        thread.join(timeout=2)

    assert not thread.is_alive()
    assert port_open.call_count == 2
    open_mock.assert_called_once_with("http://127.0.0.1:8000/", new=2)


def test_app_browser_open_failure_does_not_raise() -> None:
    import app as web_app

    with mock.patch.object(web_app, "_is_port_open", return_value=True), mock.patch.object(
        web_app.webbrowser,
        "open",
        side_effect=RuntimeError("browser unavailable"),
    ), mock.patch("builtins.print") as print_mock:
        web_app._open_browser_when_ready("127.0.0.1", 8000, timeout_seconds=0.1, check_interval=0)

    print_mock.assert_called_once()


def run_all() -> tuple[int, list[str]]:
    failures: list[str] = []
    tests = [
        ("1 initial inventory 0", test_scenario_1_initial_inventory_zero),
        ("2 inventory duplicate block", test_scenario_2_inventory_duplicate_blocked),
        ("3 full format inbound", test_scenario_3_full_format_inbound),
        ("4 FIFO first outbound", test_scenario_4_fifo_first_outbound),
        ("5 second outbound + history", test_scenario_5_second_outbound_and_history),
        ("6 outbound history re-inbound", test_scenario_6_outbound_history_confirm_logic),
        ("7 empty outbound", test_scenario_7_empty_outbound),
        ("parser validation", test_parser_errors),
        ("parser five segments", test_parser_five_segments),
        ("format_account", test_format_account),
        ("batch inbound url passthrough", test_batch_inbound_url_passthrough),
        ("search inventory and history", test_search_inventory_and_history),
        ("search LIKE escape", test_search_like_escape),
        ("failure_lines_for_clipboard", test_failure_lines_for_clipboard),
        ("batch inbound mixed lines", test_batch_inbound_mixed_lines),
        ("batch inbound duplicate in batch", test_batch_inbound_duplicate_in_batch),
        ("batch inbound seen username duplicate", test_batch_inbound_seen_username_duplicate),
        ("batch outbound default 1", test_batch_outbound_default_one),
        ("batch outbound FIFO 2", test_batch_outbound_fifo_two),
        ("batch outbound exceeds inventory", test_batch_outbound_exceeds_inventory),
        ("outbound_oldest_many(0)", test_outbound_oldest_many_zero),
        ("get_latest_outbound_times batch", test_get_latest_outbound_times_batch),
        ("exists many batch", test_exists_many_batch),
        ("clipboard copy_text", test_clipboard_copy_text),
        ("clipboard read_text", test_clipboard_read_text),
        ("extract_valid_account_lines", test_extract_valid_account_lines),
        ("read batch clipboard import", test_read_batch_clipboard_import),
        ("ignore app clipboard", test_ignore_app_clipboard),
        ("batch pending approve", test_batch_inbound_pending_approve),
        ("batch pending cancel", test_batch_inbound_pending_cancel),
        ("review keyboard approve", test_review_pending_keyboard_toggle_and_approve),
        ("review keyboard move", test_review_pending_keyboard_move_cursor),
        ("review keyboard cancel", test_review_pending_keyboard_cancel_selected),
        ("review keyboard esc", test_review_pending_keyboard_esc_exits),
        ("review keyboard y warn", test_review_pending_keyboard_y_without_selection),
        ("console_input arrow keys", test_console_input_read_key_arrows),
        ("read_line_or_exit esc", test_read_line_or_exit_esc),
        ("read_line_or_exit q is normal input", test_read_line_or_exit_q_is_normal_input),
        ("read_line_or_exit unix esc", test_read_line_or_exit_unix_esc),
        ("inbound mode stays after batch", test_inbound_mode_stays_after_batch),
        ("outbound mode invalid then retry", test_outbound_mode_invalid_then_retry),
        ("search mode empty query retries", test_search_mode_empty_query_retries),
        ("outbound by username", test_outbound_by_username),
        ("search single inventory outbound", test_search_single_inventory_offers_outbound),
        ("search multiple no outbound prompt", test_search_multiple_inventory_no_outbound_prompt),
        ("classify outbound in inventory", test_classify_outbound_line_in_inventory),
        ("classify outbound not in inventory", test_classify_outbound_line_not_in_inventory),
        ("classify outbound already outbound", test_classify_outbound_line_already_outbound),
        ("classify outbound re-inbound ready", test_classify_outbound_line_reinbound_ready),
        ("classify outbound batch duplicate", test_classify_outbound_line_batch_duplicate),
        ("insert_outbound_record", test_insert_outbound_record),
        ("database registry existing db", test_database_registry_registers_existing_db),
        ("database create switch rename delete", test_database_create_switch_rename_and_delete),
        ("database clone copies data", test_database_clone_copies_data_and_stays_independent),
        ("separator rules default", test_separator_rules_default),
        ("separator rules crud validation", test_separator_rules_crud_validation),
        ("parse multi separator", test_parse_multi_separator),
        ("output stays default separator", test_output_stays_default_separator),
        ("clone copies separator rules", test_clone_copies_separator_rules),
        ("process outbound batch mixed", test_process_outbound_batch_mixed),
        ("outbound paste mode stays after batch", test_outbound_paste_mode_stays_after_batch),
        ("handle entry outbound paste", test_handle_entry_outbound_paste),
        ("api inbound preview", test_api_inbound_preview),
        ("api separator rules", test_api_separator_rules),
        ("api inbound commit", test_api_inbound_commit),
        ("api fifo preview and commit", test_api_fifo_preview_and_commit),
        ("account notes table exists", test_account_notes_table_exists),
        ("set account note empty skip", test_set_account_note_empty_skip),
        ("set account note no overwrite", test_set_account_note_no_overwrite),
        ("set account note overwrite", test_set_account_note_overwrite),
        ("search inventory by note", test_search_inventory_by_note),
        ("search outbound history by note", test_search_outbound_history_by_note),
        ("list inbound history by note", test_list_inbound_history_by_note),
        ("list outbound history by note", test_list_outbound_history_by_note),
        ("api inbound commit with note", test_api_inbound_commit_with_note),
        ("api fifo commit with note", test_api_fifo_commit_with_note),
        ("api outbound paste with note", test_api_outbound_paste_with_note),
        ("api note no overwrite without flag", test_api_note_no_overwrite_without_flag),
        ("api note overwrite with flag", test_api_note_overwrite_with_flag),
        ("api fifo preview new head after commit", test_api_fifo_preview_new_head_after_commit),
        ("api fifo preview reflects database switch", test_api_fifo_preview_reflects_database_switch),
        ("api fifo commit multiple notes", test_api_fifo_commit_multiple_notes),
        ("api outbound by username with note searchable", test_api_outbound_by_username_with_note_searchable),
        ("api outbound by username note without overwrite", test_api_outbound_by_username_note_without_overwrite),
        ("note overwrite logic mirror", test_note_overwrite_logic_mirror),
        ("web note overwrite vitest", test_web_note_overwrite_vitest),
        ("api search inventory and history", test_api_search_inventory_and_history),
        ("api inventory empty", test_api_inventory_empty),
        ("api inventory ordered", test_api_inventory_real_records_ordered),
        ("inbound record created", test_inbound_record_created_on_insert),
        ("inbound persists after outbound", test_inbound_history_persists_after_outbound),
        ("reinbound new record", test_reinbound_creates_new_inbound_record),
        (
            "api reinbound ignores separator rules",
            test_api_reinbound_from_history_ignores_separator_rules,
        ),
        (
            "api reinbound duplicate username",
            test_api_reinbound_from_history_duplicate_username,
        ),
        (
            "api reinbound preserves outbound history",
            test_api_reinbound_from_history_preserves_outbound_and_creates_inbound,
        ),
        (
            "outbound from inbound history in inventory",
            test_outbound_from_inbound_history_in_inventory,
        ),
        (
            "outbound from inbound history not in inventory",
            test_outbound_from_inbound_history_not_in_inventory,
        ),
        (
            "outbound from inbound history already outbound",
            test_outbound_from_inbound_history_already_outbound,
        ),
        ("api outbound from inbound history", test_api_outbound_from_inbound_history),
        (
            "api outbound from inbound history duplicate",
            test_api_outbound_from_inbound_history_already_outbound,
        ),
        (
            "api reinbound clipboard text",
            test_api_reinbound_from_history_clipboard_text,
        ),
        ("history shortcut notes searchable", test_history_shortcut_notes_searchable),
        ("list inbound history has outbound", test_list_inbound_history_has_outbound),
        ("migrate inbound history", test_migrate_inbound_history_backfill),
        ("outbound inbound_record_id paths", test_outbound_paths_set_inbound_record_id),
        ("history filters parse dates", test_history_filters_parse_dates),
        ("list inbound history filters", test_list_inbound_history_date_filters),
        ("list unified history types", test_list_unified_history_types),
        ("api history endpoints filters", test_api_history_endpoints_and_filters),
        ("api outbound history empty", test_api_outbound_history_empty),
        ("api outbound history ordered", test_api_outbound_history_real_records_ordered),
        ("api direct outbound null inbound", test_api_direct_outbound_null_inbound_at),
        ("api inventory outbound inbound", test_api_inventory_outbound_has_inbound_at),
        (
            "api unified direct outbound filter",
            test_api_unified_history_direct_outbound_date_filter,
        ),
        ("api outbound by username", test_api_outbound_by_username),
        ("api outbound paste commit", test_api_outbound_paste_commit),
        ("api clipboard ignore", test_api_clipboard_ignore),
        ("api database management", test_api_database_management),
        ("updater version compare", test_updater_version_compare),
        ("updater release assets", test_updater_release_assets),
        ("updater ignores github token env", test_updater_ignores_github_token_env),
        ("updater web latest without token", test_updater_web_latest_without_token),
        ("updater release tag parse and download urls", test_updater_release_tag_parse_and_download_urls),
        ("update check ignores stale rate limit status", test_update_check_ignores_stale_rate_limit_status),
        ("run update once ignores stale rate limit status", test_run_update_once_ignores_stale_rate_limit_status),
        ("updater frozen default work dir", test_updater_frozen_default_work_dir_is_exe_parent),
        ("updater rejects pyinstaller temp work dir", test_updater_rejects_pyinstaller_temp_work_dir),
        ("updater direct sidecar command", test_updater_direct_sidecar_command_uses_install_work_dir),
        ("updater direct sidecar handoff", test_updater_direct_sidecar_handoff_logs_without_argument_collision),
        ("updater print work dir exits", test_updater_print_work_dir_exits_before_update),
        ("updater trace writes log", test_updater_trace_writes_log_file),
        ("updater one shot lock skip", test_updater_one_shot_lock_skip_writes_status_and_log),
        ("updater main one shot once", test_updater_main_one_shot_runs_once_without_sleep),
        ("update success refreshes version", test_update_success_refreshes_status_and_runtime_version),
        ("download retry connection error", test_download_to_retries_connection_error_and_cleans_part),
        ("download retry http status", test_download_to_retries_503_but_not_404),
        ("updater whitelist", test_updater_whitelist_blocks_data_and_source),
        ("update trigger token guard", test_update_trigger_token_guard),
        ("launch update once command", test_launch_update_once_command),
        ("app browser url localhost", test_app_browser_url_localhost),
        ("app browser url wildcard host", test_app_browser_url_wildcard_host),
        ("app browser url ipv6", test_app_browser_url_ipv6),
        ("app frontend html route", test_app_frontend_file_for_html_route),
        ("app open browser after port ready", test_app_open_browser_after_port_ready),
        ("app browser open failure", test_app_browser_open_failure_does_not_raise),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS: {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL: {name} — {exc}")
    return passed, failures


if __name__ == "__main__":
    tmp = _use_temp_db()
    try:
        total, fails = run_all()
        print()
        print(f"Results: {total} passed, {len(fails)} failed")
        if fails:
            for f in fails:
                print(f"  - {f}")
            sys.exit(1)
    finally:
        tmp.cleanup()
