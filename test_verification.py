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

import database as db
import parser
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
