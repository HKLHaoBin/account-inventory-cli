"""Automated verification of the 7 scenarios from the implementation plan."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
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


def test_updater_github_token_header() -> None:
    import updater

    class DummyResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"tag_name": "v0.2.0", "assets": []}

    with mock.patch.dict("os.environ", {"UPDATER_GITHUB_TOKEN": "token-123"}), mock.patch(
        "updater.requests.get",
        return_value=DummyResponse(),
    ) as get_mock:
        release = updater.github_latest_release("owner/repo")

    headers = get_mock.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer token-123"
    assert release["tag_name"] == "v0.2.0"


def test_update_check_rate_limit_status() -> None:
    import updater
    import updater_runtime

    reset_epoch = 1767225600
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "VERSION").write_text("0.1.0", encoding="utf-8")
        with mock.patch.object(
            updater,
            "inspect_latest_release",
            side_effect=updater.GitHubRateLimitError(reset_epoch),
        ):
            status = updater_runtime.check_latest_update(root)

    assert status["state"] == "error"
    assert status["phase"] == "failed"
    assert "GitHub API rate limit exceeded" in status["message"]
    assert status["github_rate_limit_reset"] == reset_epoch
    assert status["github_rate_limit_reset_at"]


def test_update_check_rate_limit_cooldown() -> None:
    import time
    import updater
    import updater_runtime

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
        with mock.patch.dict(
            "os.environ",
            {"UPDATER_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""},
        ), mock.patch.object(updater, "inspect_latest_release") as inspect_mock:
            status = updater_runtime.check_latest_update(root)

    inspect_mock.assert_not_called()
    assert status["state"] == "error"
    assert status["github_rate_limit_reset"] == reset_epoch


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
    stop.assert_called_once()
    command = popen.call_args.args[0]
    assert "--restore-watch" in command
    assert "--work-dir" in command
    assert str(root) in command
    assert "--port" in command
    assert "8123" in command


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
        ("process outbound batch mixed", test_process_outbound_batch_mixed),
        ("outbound paste mode stays after batch", test_outbound_paste_mode_stays_after_batch),
        ("handle entry outbound paste", test_handle_entry_outbound_paste),
        ("api inbound preview", test_api_inbound_preview),
        ("api inbound commit", test_api_inbound_commit),
        ("api fifo preview and commit", test_api_fifo_preview_and_commit),
        ("api search inventory and history", test_api_search_inventory_and_history),
        ("api inventory empty", test_api_inventory_empty),
        ("api inventory ordered", test_api_inventory_real_records_ordered),
        ("api outbound history empty", test_api_outbound_history_empty),
        ("api outbound history ordered", test_api_outbound_history_real_records_ordered),
        ("api outbound by username", test_api_outbound_by_username),
        ("api outbound paste commit", test_api_outbound_paste_commit),
        ("api clipboard ignore", test_api_clipboard_ignore),
        ("updater version compare", test_updater_version_compare),
        ("updater release assets", test_updater_release_assets),
        ("updater github token header", test_updater_github_token_header),
        ("update check rate limit status", test_update_check_rate_limit_status),
        ("update check rate limit cooldown", test_update_check_rate_limit_cooldown),
        ("updater whitelist", test_updater_whitelist_blocks_data_and_source),
        ("update trigger token guard", test_update_trigger_token_guard),
        ("launch update once command", test_launch_update_once_command),
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
