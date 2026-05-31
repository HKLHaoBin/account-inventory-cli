"""SQLite persistence for account inventory and outbound history."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DB_NAME = "accounts.db"


def get_db_path() -> Path:
    return _DATA_DIR / _DB_NAME


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS outbound_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                email_password TEXT,
                inbound_at TEXT NOT NULL,
                outbound_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """
        )


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
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT outbound_at
            FROM outbound_records
            WHERE username = ?
            ORDER BY outbound_at DESC, id DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        return row["outbound_at"] if row else None


def insert_account(
    username: str,
    password: str,
    email: str | None = None,
    email_password: str | None = None,
) -> None:
    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO accounts (username, password, email, email_password)
                VALUES (?, ?, ?, ?)
                """,
                (username, password, email, email_password),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"账号 {username} 已在库存中") from exc


def outbound_oldest_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, password, email, email_password, created_at
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
                    username, password, email, email_password, inbound_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["username"],
                    row["password"],
                    row["email"],
                    row["email_password"],
                    row["created_at"],
                ),
            )
            records.append(
                {
                    "username": row["username"],
                    "password": row["password"],
                    "email": row["email"],
                    "email_password": row["email_password"],
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
