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
import database as db
from batch import InboundFailure, InboundPending, InboundReady, classify_inbound_line
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
    u, p, e, ep = parse_account_line("a----b")
    db.insert_account(u, p, e, ep)
    assert db.count_inventory() == 1
    assert db.exists_in_inventory("a")
    try:
        db.insert_account("a", "b2")
        raise AssertionError("expected IntegrityError / ValueError")
    except ValueError:
        pass
    assert db.count_inventory() == 1


def test_scenario_3_full_format_inbound() -> None:
    u, p, e, ep = parse_account_line("a2----b2----e@x.com----ep")
    db.insert_account(u, p, e, ep)
    assert db.count_inventory() == 2


def test_scenario_4_fifo_first_outbound() -> None:
    record = db.outbound_oldest()
    assert record is not None
    text = format_account(
        record["username"],
        record["password"],
        record["email"],
        record["email_password"],
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
    for bad in ("", "only", "a----", "----b", "a----b----c----d----e"):
        try:
            parse_account_line(bad)
            raise AssertionError(f"expected error for: {bad!r}")
        except ValueError:
            pass


def test_format_account() -> None:
    assert format_account("u", "p") == "u----p"
    assert format_account("u", "p", "e", "ep") == "u----p----e----ep"


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
    with mock.patch("builtins.input", side_effect=["a 1"]):
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
    with mock.patch("builtins.input", side_effect=["c 1"]):
        approved, failures = cli._review_pending(pending)
    assert approved == 0
    assert len(failures) == 1
    assert failures[0].reason == "用户取消录入（曾出现在出库记录）"
    assert not db.exists_in_inventory("hist2")


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
        ("format_account", test_format_account),
        ("batch inbound mixed lines", test_batch_inbound_mixed_lines),
        ("batch inbound duplicate in batch", test_batch_inbound_duplicate_in_batch),
        ("batch inbound seen username duplicate", test_batch_inbound_seen_username_duplicate),
        ("batch outbound default 1", test_batch_outbound_default_one),
        ("batch outbound FIFO 2", test_batch_outbound_fifo_two),
        ("batch outbound exceeds inventory", test_batch_outbound_exceeds_inventory),
        ("outbound_oldest_many(0)", test_outbound_oldest_many_zero),
        ("batch pending approve", test_batch_inbound_pending_approve),
        ("batch pending cancel", test_batch_inbound_pending_cancel),
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
