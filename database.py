"""SQLite persistence for account inventory and outbound history."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_DATA_DIR = _app_dir() / "data"
_DB_NAME = "accounts.db"


def get_db_path() -> Path:
    return _DATA_DIR / _DB_NAME


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _migrate_add_url_column(conn: sqlite3.Connection) -> None:
    for table in ("accounts", "outbound_records"):
        if not _column_exists(conn, table, "url"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN url TEXT")


def _escape_like(substring: str) -> str:
    return substring.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT,
                email_password TEXT,
                url TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS outbound_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                email_password TEXT,
                url TEXT,
                inbound_at TEXT NOT NULL,
                outbound_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """
        )
        _migrate_add_url_column(conn)


def count_inventory() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
        return int(row["n"])


def exists_in_inventory(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM accounts WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
        return row is not None


def exists_in_outbound(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM outbound_records WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
        return row is not None


def get_latest_outbound_time(username: str) -> str | None:
    times = get_latest_outbound_times([username])
    return times.get(username)


def get_latest_outbound_times(usernames: list[str]) -> dict[str, str]:
    if not usernames:
        return {}

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT username, MAX(outbound_at) AS outbound_at
            FROM outbound_records
            WHERE username IN ({placeholders})
            GROUP BY username
            """,
            unique,
        ).fetchall()
    return {row["username"]: row["outbound_at"] for row in rows}


def exists_in_inventory_many(usernames: list[str]) -> set[str]:
    if not usernames:
        return set()

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT username FROM accounts WHERE username IN ({placeholders})",
            unique,
        ).fetchall()
    return {row["username"] for row in rows}


def exists_in_outbound_many(usernames: list[str]) -> set[str]:
    if not usernames:
        return set()

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT username FROM outbound_records WHERE username IN ({placeholders})",
            unique,
        ).fetchall()
    return {row["username"] for row in rows}


def insert_account(
    username: str,
    password: str,
    email: str | None = None,
    email_password: str | None = None,
    url: str | None = None,
) -> None:
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO accounts (username, password, email, email_password, url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, password, email, email_password, url),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"账号 {username} 已在库存中") from exc


def _row_to_account_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "username": row["username"],
        "password": row["password"],
        "email": row["email"],
        "email_password": row["email_password"],
        "url": row["url"],
    }


def _search_table(
    table: str,
    substring: str,
    *,
    order_by: str,
) -> list[dict[str, Any]]:
    if not substring:
        return []

    pattern = f"%{_escape_like(substring)}%"
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT username, password, email, email_password, url
            FROM {table}
            WHERE username LIKE ? ESCAPE '\\'
               OR password LIKE ? ESCAPE '\\'
               OR email LIKE ? ESCAPE '\\'
               OR email_password LIKE ? ESCAPE '\\'
               OR url LIKE ? ESCAPE '\\'
            ORDER BY {order_by}
            """,
            (pattern, pattern, pattern, pattern, pattern),
        ).fetchall()
    return [_row_to_account_dict(row) for row in rows]


def search_inventory(substring: str) -> list[dict[str, Any]]:
    return _search_table(
        "accounts",
        substring,
        order_by="created_at ASC, id ASC",
    )


def search_outbound_history(substring: str) -> list[dict[str, Any]]:
    return _search_table(
        "outbound_records",
        substring,
        order_by="outbound_at DESC, id DESC",
    )


def outbound_oldest_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, password, email, email_password, url, created_at
            FROM accounts
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (count,),
        ).fetchall()
        if not rows:
            return []

        records: list[dict[str, Any]] = []
        for row in rows:
            conn.execute(
                """
                INSERT INTO outbound_records (
                    username, password, email, email_password, url, inbound_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["username"],
                    row["password"],
                    row["email"],
                    row["email_password"],
                    row["url"],
                    row["created_at"],
                ),
            )
            records.append(
                {
                    "username": row["username"],
                    "password": row["password"],
                    "email": row["email"],
                    "email_password": row["email_password"],
                    "url": row["url"],
                    "created_at": row["created_at"],
                }
            )

        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"DELETE FROM accounts WHERE id IN ({placeholders})",
            ids,
        )
        return records


def outbound_oldest() -> dict[str, Any] | None:
    records = outbound_oldest_many(1)
    return records[0] if records else None


def count_outbound_records() -> int:
    """Helper for tests."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM outbound_records").fetchone()
        return int(row["n"])
