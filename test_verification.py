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
from parser import format_account, parse_account_line


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
    with mock.patch("console_input.read_line_or_exit", side_effect=side_effect):
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
    with mock.patch("console_input.read_line_or_exit", side_effect=side_effect), mock.patch(
        "cli.copy_to_clipboard", return_value=True
    ):
        cli.handle_outbound_paste()
    assert db.count_inventory() == 0
    assert db.exists_in_outbound("direct")


def test_handle_entry_outbound_paste() -> None:
    _reset_inventory()
    side_effect = ["2", "new----pw", "", None]
    with mock.patch("console_input.read_line_or_exit", side_effect=side_effect), mock.patch(
        "cli.copy_to_clipboard", return_value=True
    ):
        cli.handle_entry()
    assert db.exists_in_outbound("new")


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
