"""SQLite persistence for account inventory and outbound history."""

from __future__ import annotations

import sqlite3
import sys
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from history_filters import (
    DateRange,
    build_date_or_clause,
    parse_ranges,
    q_to_date_range,
)


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_DATA_DIR = _app_dir() / "data"
_DB_NAME = "accounts.db"
_REGISTRY_NAME = "databases.json"
_DEFAULT_DB_ID = "default"
_DEFAULT_DB_NAME = "默认数据库"


def get_db_path() -> Path:
    active = _active_database_record()
    return _DATA_DIR / active["file_name"]


def _connect_to(path: Path) -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect() -> sqlite3.Connection:
    return _connect_to(get_db_path())


def _registry_path() -> Path:
    return _DATA_DIR / _REGISTRY_NAME


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_database_record() -> dict[str, Any]:
    return {
        "id": _DEFAULT_DB_ID,
        "name": _DEFAULT_DB_NAME,
        "file_name": _DB_NAME,
        "created_at": _now_iso(),
        "active": True,
    }


def _database_path(record: dict[str, Any]) -> Path:
    return _DATA_DIR / str(record["file_name"])


def _read_registry_payload() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_registry(records: list[dict[str, Any]], active_id: str) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    normalized: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["active"] = item["id"] == active_id
        normalized.append(item)
    payload = {
        "active_database_id": active_id,
        "databases": normalized,
    }
    _registry_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_registry(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    raw_records = payload.get("databases")
    if not isinstance(raw_records, list):
        return [], ""

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        database_id = str(raw.get("id") or "").strip()
        file_name = str(raw.get("file_name") or "").strip()
        if not database_id or not file_name or database_id in seen:
            continue
        records.append(
            {
                "id": database_id,
                "name": str(raw.get("name") or _DEFAULT_DB_NAME).strip()
                or _DEFAULT_DB_NAME,
                "file_name": Path(file_name).name,
                "created_at": str(raw.get("created_at") or _now_iso()),
                "active": bool(raw.get("active")),
            }
        )
        seen.add(database_id)

    active_id = str(payload.get("active_database_id") or "").strip()
    if not active_id:
        active = next((record for record in records if record["active"]), None)
        active_id = str(active["id"]) if active else ""
    if records and active_id not in {record["id"] for record in records}:
        active_id = str(records[0]["id"])
    return records, active_id


def _ensure_registry() -> tuple[list[dict[str, Any]], str]:
    payload = _read_registry_payload()
    records, active_id = _normalize_registry(payload)
    if not records:
        records = [_default_database_record()]
        active_id = _DEFAULT_DB_ID
        _write_registry(records, active_id)
        return records, active_id

    if not any(record["active"] for record in records):
        _write_registry(records, active_id)
        records, active_id = _normalize_registry(_read_registry_payload())
    return records, active_id


def _active_database_record() -> dict[str, Any]:
    records, active_id = _ensure_registry()
    for record in records:
        if record["id"] == active_id:
            return record
    return records[0]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _migrate_add_url_column(conn: sqlite3.Connection) -> None:
    for table in ("accounts", "outbound_records"):
        if not _column_exists(conn, table, "url"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN url TEXT")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _migrate_inbound_history(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inbound_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            email_password TEXT,
            url TEXT,
            inbound_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )

    if not _column_exists(conn, "accounts", "inbound_record_id"):
        conn.execute("ALTER TABLE accounts ADD COLUMN inbound_record_id INTEGER")
    if not _column_exists(conn, "outbound_records", "inbound_record_id"):
        conn.execute("ALTER TABLE outbound_records ADD COLUMN inbound_record_id INTEGER")

    if not _table_exists(conn, "accounts"):
        return

    account_rows = conn.execute(
        """
        SELECT id, username, password, email, email_password, url, created_at
        FROM accounts
        WHERE inbound_record_id IS NULL
        """
    ).fetchall()
    for row in account_rows:
        cursor = conn.execute(
            """
            INSERT INTO inbound_records (
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
        conn.execute(
            "UPDATE accounts SET inbound_record_id = ? WHERE id = ?",
            (cursor.lastrowid, row["id"]),
        )

    outbound_rows = conn.execute(
        """
        SELECT id, username, password, email, email_password, url,
               inbound_at, outbound_at, inbound_record_id
        FROM outbound_records
        WHERE inbound_record_id IS NULL
          AND inbound_at != outbound_at
        """
    ).fetchall()
    for row in outbound_rows:
        existing = conn.execute(
            """
            SELECT id
            FROM inbound_records
            WHERE username = ?
              AND inbound_at = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (row["username"], row["inbound_at"]),
        ).fetchone()
        if existing is not None:
            inbound_record_id = existing["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO inbound_records (
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
                    row["inbound_at"],
                ),
            )
            inbound_record_id = cursor.lastrowid
        conn.execute(
            "UPDATE outbound_records SET inbound_record_id = ? WHERE id = ?",
            (inbound_record_id, row["id"]),
        )


def _escape_like(substring: str) -> str:
    return substring.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _init_schema(conn: sqlite3.Connection) -> None:
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
    _migrate_inbound_history(conn)


def _init_database_file(record: dict[str, Any]) -> None:
    with _connect_to(_database_path(record)) as conn:
        _init_schema(conn)


def init_db() -> None:
    record = _active_database_record()
    _init_database_file(record)


def _public_database_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "name": record["name"],
        "file_name": record["file_name"],
        "path": str(_database_path(record)),
        "created_at": record["created_at"],
        "active": bool(record["active"]),
    }


def list_databases() -> list[dict[str, Any]]:
    records, active_id = _ensure_registry()
    return [
        _public_database_record({**record, "active": record["id"] == active_id})
        for record in records
    ]


def get_active_database() -> dict[str, Any]:
    return _public_database_record(_active_database_record())


def _counts_for_record(record: dict[str, Any]) -> dict[str, int]:
    _init_database_file(record)
    with _connect_to(_database_path(record)) as conn:
        inventory = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
        inbound = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM inbound_records
            WHERE date(inbound_at) = date('now', 'localtime')
            """
        ).fetchone()
        outbound = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM outbound_records
            WHERE date(outbound_at) = date('now', 'localtime')
            """
        ).fetchone()
    return {
        "inventory_count": int(inventory["n"]),
        "today_inbound": int(inbound["n"]),
        "today_outbound": int(outbound["n"]),
    }


def database_info(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **_public_database_record(record),
        **_counts_for_record(record),
    }


def list_database_info() -> list[dict[str, Any]]:
    records, active_id = _ensure_registry()
    return [
        database_info({**record, "active": record["id"] == active_id})
        for record in records
    ]


def get_active_database_info() -> dict[str, Any]:
    return database_info(_active_database_record())


def _validate_database_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError("数据库名称不能为空")
    if len(value) > 60:
        raise ValueError("数据库名称不能超过 60 个字符")
    return value


def create_database(name: str) -> dict[str, Any]:
    records, _ = _ensure_registry()
    database_id = uuid.uuid4().hex
    record = {
        "id": database_id,
        "name": _validate_database_name(name),
        "file_name": f"accounts-{database_id[:12]}.db",
        "created_at": _now_iso(),
        "active": True,
    }
    records.append(record)
    _write_registry(records, database_id)
    _init_database_file(record)
    return database_info(record)


def clone_database(database_id: str, name: str) -> dict[str, Any]:
    records, _ = _ensure_registry()
    source = next((item for item in records if item["id"] == database_id), None)
    if source is None:
        raise ValueError("数据库不存在")

    _init_database_file(source)
    clone_id = uuid.uuid4().hex
    clone = {
        "id": clone_id,
        "name": _validate_database_name(name),
        "file_name": f"accounts-{clone_id[:12]}.db",
        "created_at": _now_iso(),
        "active": True,
    }

    try:
        shutil.copy2(_database_path(source), _database_path(clone))
    except OSError as exc:
        raise ValueError(f"克隆数据库文件失败：{exc}") from exc

    records.append(clone)
    _write_registry(records, clone_id)
    _init_database_file(clone)
    return database_info(clone)


def set_active_database(database_id: str) -> dict[str, Any]:
    records, _ = _ensure_registry()
    record = next((item for item in records if item["id"] == database_id), None)
    if record is None:
        raise ValueError("数据库不存在")
    _write_registry(records, database_id)
    _init_database_file(record)
    return database_info({**record, "active": True})


def rename_database(database_id: str, name: str) -> dict[str, Any]:
    records, active_id = _ensure_registry()
    record = next((item for item in records if item["id"] == database_id), None)
    if record is None:
        raise ValueError("数据库不存在")
    record["name"] = _validate_database_name(name)
    _write_registry(records, active_id)
    return database_info({**record, "active": record["id"] == active_id})


def delete_database(database_id: str) -> dict[str, Any]:
    records, active_id = _ensure_registry()
    record = next((item for item in records if item["id"] == database_id), None)
    if record is None:
        raise ValueError("数据库不存在")

    remaining = [item for item in records if item["id"] != database_id]
    target_path = _database_path(record)
    try:
        target_path.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(f"删除数据库文件失败：{exc}") from exc

    if not remaining:
        replacement = _default_database_record()
        remaining = [replacement]
        active_id = replacement["id"]
        _write_registry(remaining, active_id)
        _init_database_file(replacement)
        return database_info(replacement)

    next_active_id = active_id if active_id != database_id else str(remaining[0]["id"])
    _write_registry(remaining, next_active_id)
    active = next(item for item in remaining if item["id"] == next_active_id)
    _init_database_file(active)
    return database_info({**active, "active": True})


def count_inventory() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
        return int(row["n"])


def count_today_inbound() -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM inbound_records
            WHERE date(inbound_at) = date('now', 'localtime')
            """
        ).fetchone()
        return int(row["n"])


def count_today_outbound() -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM outbound_records
            WHERE date(outbound_at) = date('now', 'localtime')
            """
        ).fetchone()
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
            now = conn.execute(
                "SELECT datetime('now', 'localtime') AS now"
            ).fetchone()["now"]
            cursor = conn.execute(
                """
                INSERT INTO inbound_records (
                    username, password, email, email_password, url, inbound_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, password, email, email_password, url, now),
            )
            inbound_record_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO accounts (
                    username, password, email, email_password, url,
                    created_at, inbound_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    password,
                    email,
                    email_password,
                    url,
                    now,
                    inbound_record_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"账号 {username} 已在库存中") from exc


def _row_to_account_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
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
    columns: str,
    order_by: str,
) -> list[dict[str, Any]]:
    if not substring:
        return []

    pattern = f"%{_escape_like(substring)}%"
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {columns}
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
    return [dict(row) for row in rows]


def list_inventory(limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, username, password, email, email_password, url, created_at
        FROM accounts
        ORDER BY created_at ASC, id ASC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            **_row_to_account_dict(row),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_recent_activities(limit: int = 10) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT type, id, username, timestamp
            FROM (
                SELECT 'inbound' AS type, id, username, inbound_at AS timestamp
                FROM inbound_records
                UNION ALL
                SELECT 'outbound' AS type, id, username, outbound_at AS timestamp
                FROM outbound_records
            )
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": f"{row['type']}-{row['id']}",
            "type": row["type"],
            "username": row["username"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]


def _row_to_inbound_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "password": row["password"],
        "email": row["email"],
        "email_password": row["email_password"],
        "url": row["url"],
        "inbound_at": row["inbound_at"],
    }


def _history_text_clause(
    query: str,
    *,
    include_url: bool = True,
) -> tuple[str, list[str]]:
    if not query:
        return "", []

    pattern = f"%{_escape_like(query)}%"
    if include_url:
        return (
            """
            (
                username LIKE ? ESCAPE '\\'
                OR password LIKE ? ESCAPE '\\'
                OR email LIKE ? ESCAPE '\\'
                OR email_password LIKE ? ESCAPE '\\'
                OR url LIKE ? ESCAPE '\\'
            )
            """,
            [pattern, pattern, pattern, pattern, pattern],
        )
    return (
        """
        (
            username LIKE ? ESCAPE '\\'
            OR password LIKE ? ESCAPE '\\'
            OR email LIKE ? ESCAPE '\\'
            OR email_password LIKE ? ESCAPE '\\'
        )
        """,
        [pattern, pattern, pattern, pattern],
    )


def _collect_history_ranges(
    query: str,
    range_tokens: list[str] | None,
) -> tuple[list[DateRange], str]:
    text_query = query.strip()
    parsed_query = q_to_date_range(text_query)
    if parsed_query is not None:
        text_query = ""

    ranges = parse_ranges(range_tokens or [])
    if parsed_query is not None:
        existing = {(item.start, item.end) for item in ranges}
        key = (parsed_query.start, parsed_query.end)
        if key not in existing:
            ranges.append(parsed_query)
    return ranges, text_query


def _build_history_where(
    *,
    query: str,
    range_tokens: list[str] | None,
    timestamp_column: str,
    include_url: bool = True,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    ranges, text_query = _collect_history_ranges(query, range_tokens)

    text_clause, text_params = _history_text_clause(text_query, include_url=include_url)
    if text_clause:
        clauses.append(text_clause)
        params.extend(text_params)

    date_clause, date_params = build_date_or_clause(timestamp_column, ranges)
    if date_clause:
        clauses.append(date_clause)
        params.extend(date_params)

    if not clauses:
        return "", []
    return f"WHERE {' AND '.join(clauses)}", params


def list_inbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="inbound_at",
    )
    sql = f"""
        SELECT id, username, password, email, email_password, url, inbound_at
        FROM inbound_records
        {where_sql}
        ORDER BY inbound_at DESC, id DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params = [*params, limit]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_inbound_dict(row) for row in rows]


def list_outbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="outbound_at",
    )
    sql = f"""
        SELECT id, username, password, email, email_password, url,
               inbound_at, outbound_at, inbound_record_id
        FROM outbound_records
        {where_sql}
        ORDER BY outbound_at DESC, id DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params = [*params, limit]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            **_row_to_account_dict(row),
            "inbound_at": row["inbound_at"],
            "outbound_at": row["outbound_at"],
            "inbound_record_id": row["inbound_record_id"],
        }
        for row in rows
    ]


def list_unified_history(
    *,
    history_type: str = "all",
    query: str = "",
    range_tokens: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized = history_type.strip().lower()
    if normalized == "inbound":
        return [
            {**row, "type": "inbound", "timestamp": row["inbound_at"]}
            for row in list_inbound_history(
                query=query,
                range_tokens=range_tokens,
                limit=limit,
            )
        ]
    if normalized == "outbound":
        return [
            {
                **row,
                "type": "outbound",
                "timestamp": row["outbound_at"],
            }
            for row in list_outbound_history(
                query=query,
                range_tokens=range_tokens,
                limit=limit,
            )
        ]

    inbound_rows = list_inbound_history(query=query, range_tokens=range_tokens)
    outbound_rows = list_outbound_history(query=query, range_tokens=range_tokens)
    merged: list[dict[str, Any]] = []
    for row in inbound_rows:
        merged.append(
            {
                **row,
                "type": "inbound",
                "timestamp": row["inbound_at"],
            }
        )
    for row in outbound_rows:
        merged.append(
            {
                **row,
                "type": "outbound",
                "timestamp": row["outbound_at"],
            }
        )
    merged.sort(key=lambda item: (item["timestamp"], item["id"]), reverse=True)
    if limit is not None:
        return merged[:limit]
    return merged

def fifo_preview_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    return list_inventory(limit=count)


def search_inventory(substring: str) -> list[dict[str, Any]]:
    rows = _search_table(
        "accounts",
        substring,
        columns="id, username, password, email, email_password, url, created_at",
        order_by="created_at ASC, id ASC",
    )
    return [
        {
            **row,
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def search_outbound_history(substring: str) -> list[dict[str, Any]]:
    rows = _search_table(
        "outbound_records",
        substring,
        columns=(
            "id, username, password, email, email_password, url, "
            "inbound_at, outbound_at, inbound_record_id"
        ),
        order_by="outbound_at DESC, id DESC",
    )
    return [
        {
            **row,
            "inbound_at": row["inbound_at"],
            "outbound_at": row["outbound_at"],
        }
        for row in rows
    ]


def outbound_oldest_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, password, email, email_password, url,
                   created_at, inbound_record_id
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
                    username, password, email, email_password, url,
                    inbound_at, inbound_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["username"],
                    row["password"],
                    row["email"],
                    row["email_password"],
                    row["url"],
                    row["created_at"],
                    row["inbound_record_id"],
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


def outbound_by_username(username: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, username, password, email, email_password, url,
                   created_at, inbound_record_id
            FROM accounts
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            """
            INSERT INTO outbound_records (
                username, password, email, email_password, url,
                inbound_at, inbound_record_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["username"],
                row["password"],
                row["email"],
                row["email_password"],
                row["url"],
                row["created_at"],
                row["inbound_record_id"],
            ),
        )
        conn.execute("DELETE FROM accounts WHERE id = ?", (row["id"],))

        return {
            "username": row["username"],
            "password": row["password"],
            "email": row["email"],
            "email_password": row["email_password"],
            "url": row["url"],
            "created_at": row["created_at"],
        }


def commit_outbound_paste_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    usernames = [row["username"] for row in rows]
    placeholders = ",".join("?" * len(usernames))

    with _connect() as conn:
        inventory_rows = conn.execute(
            f"""
            SELECT id, username, password, email, email_password, url,
                   created_at, inbound_record_id
            FROM accounts
            WHERE username IN ({placeholders})
            """,
            usernames,
        ).fetchall()
        inventory_by_username = {row["username"]: row for row in inventory_rows}

        outbound_rows = conn.execute(
            f"""
            SELECT DISTINCT username
            FROM outbound_records
            WHERE username IN ({placeholders})
            """,
            usernames,
        ).fetchall()
        outbound_usernames = {row["username"] for row in outbound_rows}
        now = conn.execute("SELECT datetime('now', 'localtime') AS now").fetchone()["now"]

        results: list[dict[str, Any]] = []
        outbound_account_ids: list[int] = []
        for item in rows:
            username = item["username"]
            inventory_row = inventory_by_username.get(username)
            if inventory_row is not None:
                conn.execute(
                    """
                    INSERT INTO outbound_records (
                        username, password, email, email_password, url,
                        inbound_at, inbound_record_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inventory_row["username"],
                        inventory_row["password"],
                        inventory_row["email"],
                        inventory_row["email_password"],
                        inventory_row["url"],
                        inventory_row["created_at"],
                        inventory_row["inbound_record_id"],
                    ),
                )
                outbound_account_ids.append(inventory_row["id"])
                results.append(
                    {
                        "client_id": item["client_id"],
                        "line": item["line"],
                        "category": "inInventory",
                        "status": "success",
                        "message": "出库成功",
                        **_row_to_account_dict(inventory_row),
                        "created_at": inventory_row["created_at"],
                    }
                )
                continue

            if username in outbound_usernames:
                results.append(
                    {
                        "client_id": item["client_id"],
                        "line": item["line"],
                        "category": "inHistory",
                        "status": "error",
                        "message": "已在出库记录中",
                        "username": username,
                        "password": item["password"],
                        "email": item["email"],
                        "email_password": item["email_password"],
                        "url": item["url"],
                        "created_at": now,
                    }
                )
                continue

            conn.execute(
                """
                INSERT INTO outbound_records (
                    username, password, email, email_password, url, inbound_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    item["password"],
                    item["email"],
                    item["email_password"],
                    item["url"],
                    now,
                ),
            )
            results.append(
                {
                    "client_id": item["client_id"],
                    "line": item["line"],
                    "category": "notInInventory",
                    "status": "success",
                    "message": "已直接写入出库历史",
                    "username": username,
                    "password": item["password"],
                    "email": item["email"],
                    "email_password": item["email_password"],
                    "url": item["url"],
                    "created_at": now,
                }
            )

        if outbound_account_ids:
            delete_placeholders = ",".join("?" * len(outbound_account_ids))
            conn.execute(
                f"DELETE FROM accounts WHERE id IN ({delete_placeholders})",
                outbound_account_ids,
            )

        return results


def insert_outbound_record(
    username: str,
    password: str,
    email: str | None = None,
    email_password: str | None = None,
    url: str | None = None,
) -> None:
    with _connect() as conn:
        now = conn.execute("SELECT datetime('now', 'localtime') AS now").fetchone()["now"]
        conn.execute(
            """
            INSERT INTO outbound_records (
                username, password, email, email_password, url, inbound_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, password, email, email_password, url, now),
        )


def count_outbound_records() -> int:
    """Helper for tests."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM outbound_records").fetchone()
        return int(row["n"])


def count_inbound_records() -> int:
    """Helper for tests."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM inbound_records").fetchone()
        return int(row["n"])
