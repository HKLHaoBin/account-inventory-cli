"""SQLite persistence for account inventory and outbound history."""

from __future__ import annotations

import sqlite3
import sys
import gc
import json
import shutil
import time
import uuid
from datetime import datetime, timedelta
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


def _normalize_database_groups(
    raw_groups: object,
) -> list[dict[str, Any]]:
    if not isinstance(raw_groups, list):
        return []

    groups: list[dict[str, Any]] = []
    seen_group_ids: set[str] = set()
    for raw in raw_groups:
        if not isinstance(raw, dict):
            continue
        group_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        raw_ids = raw.get("databaseIds")
        if raw_ids is None:
            raw_ids = raw.get("database_ids")
        if not group_id or not name or not isinstance(raw_ids, list):
            continue
        if group_id in seen_group_ids:
            continue
        database_ids: list[str] = []
        seen_db_ids: set[str] = set()
        for raw_id in raw_ids:
            database_id = str(raw_id or "").strip()
            if not database_id or database_id in seen_db_ids:
                continue
            seen_db_ids.add(database_id)
            database_ids.append(database_id)
        groups.append(
            {
                "id": group_id,
                "name": name,
                "databaseIds": database_ids,
            }
        )
        seen_group_ids.add(group_id)
    return groups


def _write_registry(
    records: list[dict[str, Any]],
    active_id: str,
    *,
    database_groups: list[dict[str, Any]] | None = None,
) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    normalized: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["active"] = item["id"] == active_id
        normalized.append(item)
    existing = _read_registry_payload()
    groups = (
        database_groups
        if database_groups is not None
        else _normalize_database_groups(existing.get("database_groups"))
    )
    payload = {
        "active_database_id": active_id,
        "databases": normalized,
        "database_groups": groups,
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


_BUILTIN_DEFAULT_RULE_ID = "builtin-default"


def _migrate_separator_rules(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS separator_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            separator TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            built_in INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_separator_rules_separator
            ON separator_rules(separator);
        """
    )
    count = conn.execute("SELECT COUNT(*) AS n FROM separator_rules").fetchone()["n"]
    if count == 0:
        conn.execute(
            """
            INSERT INTO separator_rules (
                id, name, separator, enabled, built_in, sort_order, created_at
            ) VALUES (?, ?, ?, 1, 1, 0, ?)
            """,
            (_BUILTIN_DEFAULT_RULE_ID, "默认规则", "----", _now_iso()),
        )


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


def _migrate_account_notes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS account_notes (
            username TEXT PRIMARY KEY,
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )


def _note_from_row(row: sqlite3.Row) -> str:
    if "note" not in row.keys():
        return ""
    value = row["note"]
    return "" if value is None else str(value)


def set_account_note(username: str, note: str | None, *, overwrite: bool = False) -> str:
    username = username.strip()
    if not username:
        return ""
    if note is None:
        return get_account_notes([username]).get(username, "")

    new_note = note.strip()
    if not new_note and not overwrite:
        return get_account_notes([username]).get(username, "")

    with _connect() as conn:
        row = conn.execute(
            "SELECT note FROM account_notes WHERE username = ?",
            (username,),
        ).fetchone()
        current = "" if row is None else str(row["note"] or "")
        if current.strip() and not overwrite:
            return current

        value_to_store = note.strip() if overwrite else new_note
        conn.execute(
            """
            INSERT INTO account_notes (username, note, updated_at)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT(username) DO UPDATE SET
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (username, value_to_store),
        )
        return value_to_store


def get_account_notes(usernames: list[str]) -> dict[str, str]:
    normalized = [name.strip() for name in usernames if name and name.strip()]
    if not normalized:
        return {}

    placeholders = ",".join("?" * len(normalized))
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT username, note
            FROM account_notes
            WHERE username IN ({placeholders})
            """,
            normalized,
        ).fetchall()

    notes = {name: "" for name in normalized}
    for row in rows:
        notes[str(row["username"])] = str(row["note"] or "")
    return notes


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
    _migrate_separator_rules(conn)
    _migrate_account_notes(conn)


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


def list_database_groups() -> list[dict[str, Any]]:
    payload = _read_registry_payload()
    return _normalize_database_groups(payload.get("database_groups"))


def _validate_database_group_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError("组名称不能为空")
    if len(value) > 60:
        raise ValueError("组名称不能超过 60 个字符")
    return value


def save_database_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records, active_id = _ensure_registry()
    valid_ids = {record["id"] for record in records}
    normalized: list[dict[str, Any]] = []
    seen_db_ids: set[str] = set()

    for raw in groups:
        if not isinstance(raw, dict):
            raise ValueError("组配置格式无效")
        group_id = str(raw.get("id") or "").strip() or uuid.uuid4().hex
        name = _validate_database_group_name(str(raw.get("name") or ""))
        raw_ids = raw.get("databaseIds")
        if raw_ids is None:
            raw_ids = raw.get("database_ids")
        if not isinstance(raw_ids, list):
            raise ValueError("databaseIds 必须是数组")

        database_ids: list[str] = []
        for raw_id in raw_ids:
            database_id = str(raw_id or "").strip()
            if not database_id:
                continue
            if database_id not in valid_ids:
                raise ValueError(f"数据库不存在：{database_id}")
            if database_id in seen_db_ids:
                raise ValueError(f"数据库不能属于多个组：{database_id}")
            seen_db_ids.add(database_id)
            database_ids.append(database_id)

        normalized.append(
            {
                "id": group_id,
                "name": name,
                "databaseIds": database_ids,
            }
        )

    _write_registry(records, active_id, database_groups=normalized)
    return normalized


def get_group_database_ids(database_id: str | None = None) -> list[str]:
    if database_id is None:
        database_id = _active_database_record()["id"]
    else:
        database_id = database_id.strip()

    for group in list_database_groups():
        if database_id in group["databaseIds"]:
            return list(group["databaseIds"])
    return [database_id]


def _database_record_by_id(
    database_id: str,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    items = records if records is not None else _ensure_registry()[0]
    return next((item for item in items if item["id"] == database_id), None)


def exists_in_inventory_many_for_group(
    usernames: list[str],
    database_id: str | None = None,
) -> set[str]:
    if not usernames:
        return set()

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    found: set[str] = set()
    records, _ = _ensure_registry()
    for db_id in get_group_database_ids(database_id):
        record = _database_record_by_id(db_id, records)
        if record is None:
            continue
        _init_database_file(record)
        with _connect_to(_database_path(record)) as conn:
            rows = conn.execute(
                f"SELECT username FROM accounts WHERE username IN ({placeholders})",
                unique,
            ).fetchall()
        found.update(row["username"] for row in rows)
        if len(found) == len(unique):
            break
    return found


def exists_in_outbound_many_for_group(
    usernames: list[str],
    database_id: str | None = None,
) -> set[str]:
    if not usernames:
        return set()

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    found: set[str] = set()
    records, _ = _ensure_registry()
    for db_id in get_group_database_ids(database_id):
        record = _database_record_by_id(db_id, records)
        if record is None:
            continue
        _init_database_file(record)
        with _connect_to(_database_path(record)) as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT username
                FROM outbound_records
                WHERE username IN ({placeholders})
                """,
                unique,
            ).fetchall()
        found.update(row["username"] for row in rows)
        if len(found) == len(unique):
            break
    return found


def get_latest_outbound_times_for_group(
    usernames: list[str],
    database_id: str | None = None,
) -> dict[str, str]:
    if not usernames:
        return {}

    unique = list(dict.fromkeys(usernames))
    placeholders = ",".join("?" * len(unique))
    latest: dict[str, str] = {}
    records, _ = _ensure_registry()
    for db_id in get_group_database_ids(database_id):
        record = _database_record_by_id(db_id, records)
        if record is None:
            continue
        _init_database_file(record)
        with _connect_to(_database_path(record)) as conn:
            rows = conn.execute(
                f"""
                SELECT username, MAX(outbound_at) AS outbound_at
                FROM outbound_records
                WHERE username IN ({placeholders})
                GROUP BY username
                """,
                unique,
            ).fetchall()
        for row in rows:
            username = row["username"]
            outbound_at = row["outbound_at"]
            current = latest.get(username)
            if current is None or outbound_at > current:
                latest[username] = outbound_at
    return latest


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


def _unlink_database_file(path: Path, *, attempts: int = 10, delay: float = 0.05) -> None:
    last_exc: OSError | None = None
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            gc.collect()
            time.sleep(delay * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def delete_database(database_id: str) -> dict[str, Any]:
    records, active_id = _ensure_registry()
    record = next((item for item in records if item["id"] == database_id), None)
    if record is None:
        raise ValueError("数据库不存在")

    remaining = [item for item in records if item["id"] != database_id]
    target_path = _database_path(record)
    try:
        _unlink_database_file(target_path)
    except OSError as exc:
        raise ValueError(f"删除数据库文件失败：{exc}") from exc

    if not remaining:
        replacement = _default_database_record()
        remaining = [replacement]
        active_id = replacement["id"]
        cleaned_groups: list[dict[str, Any]] = []
        for group in list_database_groups():
            cleaned_groups.append({**group, "databaseIds": []})
        _write_registry(remaining, active_id, database_groups=cleaned_groups)
        _init_database_file(replacement)
        return database_info(replacement)

    next_active_id = active_id if active_id != database_id else str(remaining[0]["id"])
    remaining_ids = {item["id"] for item in remaining}
    cleaned_groups: list[dict[str, Any]] = []
    for group in list_database_groups():
        cleaned_groups.append(
            {
                **group,
                "databaseIds": [
                    item_id
                    for item_id in group["databaseIds"]
                    if item_id != database_id and item_id in remaining_ids
                ],
            }
        )
    _write_registry(remaining, next_active_id, database_groups=cleaned_groups)
    active = next(item for item in remaining if item["id"] == next_active_id)
    _init_database_file(active)
    return database_info({**active, "active": True})


def _account_text_search_clause(
    query: str,
    *,
    table_alias: str = "",
) -> tuple[str, list[str]]:
    text = query.strip()
    if not text:
        return "", []

    prefix = f"{table_alias}." if table_alias else ""
    pattern = f"%{_escape_like(text)}%"
    return (
        f"""
        (
            {prefix}username LIKE ? ESCAPE '\\'
            OR {prefix}password LIKE ? ESCAPE '\\'
            OR {prefix}email LIKE ? ESCAPE '\\'
            OR {prefix}email_password LIKE ? ESCAPE '\\'
            OR {prefix}url LIKE ? ESCAPE '\\'
            OR an.note LIKE ? ESCAPE '\\'
        )
        """,
        [pattern, pattern, pattern, pattern, pattern, pattern],
    )


def _build_inventory_where(query: str) -> tuple[str, list[Any]]:
    clause, params = _account_text_search_clause(query, table_alias="a")
    if not clause:
        return "", []
    return f"WHERE {clause}", params


def _inventory_order_clause(sort_by: str, sort_dir: str) -> str:
    direction = "DESC" if sort_dir.strip().lower() == "desc" else "ASC"
    if sort_by.strip() == "username":
        return f"a.username {direction}, a.id {direction}"
    return f"a.created_at {direction}, a.id {direction}"


def count_inventory(*, query: str = "") -> int:
    where_sql, params = _build_inventory_where(query)
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM accounts AS a
            LEFT JOIN account_notes AS an ON an.username = a.username
            {where_sql}
            """,
            params,
        ).fetchone()
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
        "note": _note_from_row(row),
    }


def _search_table(
    table: str,
    substring: str,
    *,
    columns: str,
    order_by: str,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not substring:
        return []

    clause, params = _account_text_search_clause(substring, table_alias="t")
    sql = f"""
        SELECT {columns}
        FROM {table} AS t
        LEFT JOIN account_notes AS an ON an.username = t.username
        WHERE {clause}
        ORDER BY {order_by}
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _count_search_table(table: str, substring: str) -> int:
    if not substring:
        return 0

    clause, params = _account_text_search_clause(substring, table_alias="t")
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM {table} AS t
            LEFT JOIN account_notes AS an ON an.username = t.username
            WHERE {clause}
            """,
            params,
        ).fetchone()
    return int(row["n"])


def list_inventory(
    *,
    query: str = "",
    sort_by: str = "inboundAt",
    sort_dir: str = "asc",
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_inventory_where(query)
    order_clause = _inventory_order_clause(sort_by, sort_dir)
    sql = f"""
        SELECT a.id, a.username, a.password, a.email, a.email_password, a.url,
               a.created_at, COALESCE(an.note, '') AS note
        FROM accounts AS a
        LEFT JOIN account_notes AS an ON an.username = a.username
        {where_sql}
        ORDER BY {order_clause}
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]

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
    result = {
        "id": row["id"],
        "username": row["username"],
        "password": row["password"],
        "email": row["email"],
        "email_password": row["email_password"],
        "url": row["url"],
        "inbound_at": row["inbound_at"],
        "note": _note_from_row(row),
    }
    if "has_outbound" in row.keys():
        result["has_outbound"] = bool(row["has_outbound"])
    return result


def _history_text_clause(
    query: str,
    *,
    include_url: bool = True,
    table_alias: str = "",
) -> tuple[str, list[str]]:
    del include_url
    return _account_text_search_clause(query, table_alias=table_alias)


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
    table_alias: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    ranges, text_query = _collect_history_ranges(query, range_tokens)

    text_clause, text_params = _history_text_clause(
        text_query,
        include_url=include_url,
        table_alias=table_alias,
    )
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


def count_inbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> int:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ir.inbound_at",
        table_alias="ir",
    )
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM inbound_records AS ir
            LEFT JOIN account_notes AS an ON an.username = ir.username
            {where_sql}
            """,
            params,
        ).fetchone()
    return int(row["n"])


def list_inbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ir.inbound_at",
        table_alias="ir",
    )
    sql = f"""
        SELECT ir.id, ir.username, ir.password, ir.email, ir.email_password, ir.url,
               ir.inbound_at, COALESCE(an.note, '') AS note,
               EXISTS (
                   SELECT 1 FROM outbound_records AS ob
                   WHERE ob.inbound_record_id = ir.id
               ) AS has_outbound
        FROM inbound_records AS ir
        LEFT JOIN account_notes AS an ON an.username = ir.username
        {where_sql}
        ORDER BY ir.inbound_at DESC, ir.id DESC
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_inbound_dict(row) for row in rows]


def get_inbound_record(record_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT ir.id, ir.username, ir.password, ir.email, ir.email_password, ir.url,
                   ir.inbound_at, COALESCE(an.note, '') AS note
            FROM inbound_records AS ir
            LEFT JOIN account_notes AS an ON an.username = ir.username
            WHERE ir.id = ?
            """,
            (record_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_inbound_dict(row)


def outbound_from_inbound_history(record_id: int) -> dict[str, Any]:
    with _connect() as conn:
        inbound_row = conn.execute(
            """
            SELECT ir.id, ir.username, ir.password, ir.email, ir.email_password, ir.url,
                   ir.inbound_at
            FROM inbound_records AS ir
            WHERE ir.id = ?
            """,
            (record_id,),
        ).fetchone()
        if inbound_row is None:
            raise ValueError("入库记录不存在")

        existing = conn.execute(
            "SELECT 1 FROM outbound_records WHERE inbound_record_id = ?",
            (record_id,),
        ).fetchone()
        if existing is not None:
            raise ValueError("该入库记录已出库")

        account_row = conn.execute(
            """
            SELECT id, username, password, email, email_password, url,
                   created_at, inbound_record_id
            FROM accounts
            WHERE inbound_record_id = ?
            """,
            (record_id,),
        ).fetchone()

        if account_row is not None:
            conn.execute(
                """
                INSERT INTO outbound_records (
                    username, password, email, email_password, url,
                    inbound_at, inbound_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_row["username"],
                    account_row["password"],
                    account_row["email"],
                    account_row["email_password"],
                    account_row["url"],
                    account_row["created_at"],
                    account_row["inbound_record_id"],
                ),
            )
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_row["id"],))
        else:
            conn.execute(
                """
                INSERT INTO outbound_records (
                    username, password, email, email_password, url,
                    inbound_at, inbound_record_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inbound_row["username"],
                    inbound_row["password"],
                    inbound_row["email"],
                    inbound_row["email_password"],
                    inbound_row["url"],
                    inbound_row["inbound_at"],
                    record_id,
                ),
            )

        outbound_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        outbound_row = conn.execute(
            """
            SELECT ob.id, ob.username, ob.password, ob.email, ob.email_password, ob.url,
                   ob.inbound_at, ob.outbound_at, ob.inbound_record_id,
                   COALESCE(an.note, '') AS note
            FROM outbound_records AS ob
            LEFT JOIN account_notes AS an ON an.username = ob.username
            WHERE ob.id = ?
            """,
            (outbound_id,),
        ).fetchone()

    return {
        **_row_to_account_dict(outbound_row),
        "inbound_at": outbound_row["inbound_at"],
        "outbound_at": outbound_row["outbound_at"],
        "inbound_record_id": outbound_row["inbound_record_id"],
    }


def get_outbound_record(record_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT ob.id, ob.username, ob.password, ob.email, ob.email_password, ob.url,
                   ob.inbound_at, ob.outbound_at, ob.inbound_record_id,
                   COALESCE(an.note, '') AS note
            FROM outbound_records AS ob
            LEFT JOIN account_notes AS an ON an.username = ob.username
            WHERE ob.id = ?
            """,
            (record_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        **_row_to_account_dict(row),
        "inbound_at": row["inbound_at"],
        "outbound_at": row["outbound_at"],
        "inbound_record_id": row["inbound_record_id"],
    }


def count_outbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> int:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ob.outbound_at",
        table_alias="ob",
    )
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM outbound_records AS ob
            LEFT JOIN account_notes AS an ON an.username = ob.username
            {where_sql}
            """,
            params,
        ).fetchone()
    return int(row["n"])


def list_outbound_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ob.outbound_at",
        table_alias="ob",
    )
    sql = f"""
        SELECT ob.id, ob.username, ob.password, ob.email, ob.email_password, ob.url,
               ob.inbound_at, ob.outbound_at, ob.inbound_record_id,
               COALESCE(an.note, '') AS note
        FROM outbound_records AS ob
        LEFT JOIN account_notes AS an ON an.username = ob.username
        {where_sql}
        ORDER BY ob.outbound_at DESC, ob.id DESC
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]

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


def _unified_history_union_sql(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> tuple[str, list[Any]]:
    inbound_where, inbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ir.inbound_at",
        table_alias="ir",
    )
    outbound_where, outbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ob.outbound_at",
        table_alias="ob",
    )
    sql = f"""
        SELECT 'inbound' AS type, ir.id, ir.username, ir.password, ir.email,
               ir.email_password, ir.url, ir.inbound_at, NULL AS outbound_at,
               ir.inbound_at AS timestamp,
               EXISTS (
                   SELECT 1 FROM outbound_records AS ob2
                   WHERE ob2.inbound_record_id = ir.id
               ) AS has_outbound,
               COALESCE(an.note, '') AS note,
               NULL AS inbound_record_id
        FROM inbound_records AS ir
        LEFT JOIN account_notes AS an ON an.username = ir.username
        {inbound_where}
        UNION ALL
        SELECT 'outbound' AS type, ob.id, ob.username, ob.password, ob.email,
               ob.email_password, ob.url, ob.inbound_at, ob.outbound_at,
               ob.outbound_at AS timestamp,
               0 AS has_outbound,
               COALESCE(an.note, '') AS note,
               ob.inbound_record_id
        FROM outbound_records AS ob
        LEFT JOIN account_notes AS an ON an.username = ob.username
        {outbound_where}
    """
    return sql, [*inbound_params, *outbound_params]


def _row_to_unified_dict(row: sqlite3.Row) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": row["id"],
        "type": row["type"],
        "username": row["username"],
        "password": row["password"],
        "email": row["email"],
        "email_password": row["email_password"],
        "url": row["url"],
        "inbound_at": row["inbound_at"],
        "outbound_at": row["outbound_at"],
        "timestamp": row["timestamp"],
        "note": _note_from_row(row),
    }
    if row["type"] == "inbound":
        result["has_outbound"] = bool(row["has_outbound"])
    if row["type"] == "outbound":
        result["inbound_record_id"] = row["inbound_record_id"]
    return result


def count_unified_history(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> int:
    union_sql, params = _unified_history_union_sql(
        query=query,
        range_tokens=range_tokens,
    )
    with _connect() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM ({union_sql})",
            params,
        ).fetchone()
    return int(row["n"])


def list_unified_history(
    *,
    history_type: str = "all",
    query: str = "",
    range_tokens: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized = history_type.strip().lower()
    if normalized == "inbound":
        return [
            {**row, "type": "inbound", "timestamp": row["inbound_at"]}
            for row in list_inbound_history(
                query=query,
                range_tokens=range_tokens,
                offset=offset,
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
                offset=offset,
                limit=limit,
            )
        ]

    union_sql, params = _unified_history_union_sql(
        query=query,
        range_tokens=range_tokens,
    )
    sql = f"""
        SELECT *
        FROM ({union_sql})
        ORDER BY timestamp DESC, id DESC
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_unified_dict(row) for row in rows]


def export_history_records(
    *,
    history_type: str = "all",
    query: str = "",
    range_tokens: list[str] | None = None,
) -> list[dict[str, Any]]:
    return list_unified_history(
        history_type=history_type,
        query=query,
        range_tokens=range_tokens,
    )


def _parse_kline_timestamp(value: str) -> datetime:
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return datetime.fromisoformat(text)
    if "T" in text:
        text = text.replace("T", " ", 1)
    return datetime.fromisoformat(text)


def _format_kline_sql_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_kline_api_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _format_kline_bucket_time(value: datetime) -> str:
    return _format_kline_api_timestamp(value)


def _stock_delta(event: dict[str, Any]) -> int:
    if event["type"] == "inbound":
        return 1
    if event["type"] == "outbound":
        if event.get("inbound_record_id") is not None:
            return -1
    return 0


def _append_kline_time_bounds(
    where_sql: str,
    params: list[Any],
    column: str,
    *,
    lower: str | None = None,
    upper: str | None = None,
    upper_exclusive: bool = False,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    bound_params: list[Any] = []
    if lower is not None:
        clauses.append(f"{column} >= ?")
        bound_params.append(lower)
    if upper is not None:
        op = "<" if upper_exclusive else "<="
        clauses.append(f"{column} {op} ?")
        bound_params.append(upper)
    if not clauses:
        return where_sql, params
    extra = " AND ".join(clauses)
    if where_sql:
        return f"{where_sql} AND {extra}", [*params, *bound_params]
    return f"WHERE {extra}", bound_params


def get_kline_data_bounds(
    *, query: str = "", range_tokens: list[str] | None = None
) -> dict[str, Any]:
    inbound_where, inbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ir.inbound_at",
        table_alias="ir",
    )
    outbound_where, outbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ob.outbound_at",
        table_alias="ob",
    )
    sql = f"""
        SELECT MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts
        FROM (
            SELECT ir.inbound_at AS timestamp
            FROM inbound_records AS ir
            LEFT JOIN account_notes AS an ON an.username = ir.username
            {inbound_where}
            UNION ALL
            SELECT ob.outbound_at AS timestamp
            FROM outbound_records AS ob
            LEFT JOIN account_notes AS an ON an.username = ob.username
            {outbound_where}
        )
    """
    with _connect() as conn:
        row = conn.execute(sql, [*inbound_params, *outbound_params]).fetchone()

    min_ts = row["min_ts"]
    max_ts = row["max_ts"]
    if min_ts is None or max_ts is None:
        return {"dataFrom": None, "dataTo": None, "hasData": False}

    min_dt = _parse_kline_timestamp(str(min_ts))
    max_dt = _parse_kline_timestamp(str(max_ts))
    return {
        "dataFrom": _format_kline_api_timestamp(min_dt),
        "dataTo": _format_kline_api_timestamp(max_dt),
        "hasData": True,
    }


def _fetch_kline_events(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    lower: str | None = None,
    upper: str | None = None,
    upper_exclusive: bool = False,
) -> list[dict[str, Any]]:
    inbound_where, inbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ir.inbound_at",
        table_alias="ir",
    )
    outbound_where, outbound_params = _build_history_where(
        query=query,
        range_tokens=range_tokens,
        timestamp_column="ob.outbound_at",
        table_alias="ob",
    )
    inbound_where, inbound_params = _append_kline_time_bounds(
        inbound_where,
        inbound_params,
        "ir.inbound_at",
        lower=lower,
        upper=upper,
        upper_exclusive=upper_exclusive,
    )
    outbound_where, outbound_params = _append_kline_time_bounds(
        outbound_where,
        outbound_params,
        "ob.outbound_at",
        lower=lower,
        upper=upper,
        upper_exclusive=upper_exclusive,
    )
    sql = f"""
        SELECT type, id, timestamp, inbound_record_id
        FROM (
            SELECT 'inbound' AS type, ir.id, ir.inbound_at AS timestamp,
                   NULL AS inbound_record_id
            FROM inbound_records AS ir
            LEFT JOIN account_notes AS an ON an.username = ir.username
            {inbound_where}
            UNION ALL
            SELECT 'outbound' AS type, ob.id, ob.outbound_at AS timestamp,
                   ob.inbound_record_id
            FROM outbound_records AS ob
            LEFT JOIN account_notes AS an ON an.username = ob.username
            {outbound_where}
        )
        ORDER BY timestamp ASC, type ASC, id ASC
    """
    with _connect() as conn:
        rows = conn.execute(sql, [*inbound_params, *outbound_params]).fetchall()
    return [
        {
            "type": row["type"],
            "timestamp": row["timestamp"],
            "inbound_record_id": row["inbound_record_id"],
        }
        for row in rows
    ]


def list_kline_events(
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
    from_ts: str,
    to_ts: str,
) -> list[dict[str, Any]]:
    return _fetch_kline_events(
        query=query,
        range_tokens=range_tokens,
        lower=from_ts,
        upper=to_ts,
    )


def _compute_balance_before(
    from_ts: str,
    *,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> int:
    events = _fetch_kline_events(
        query=query,
        range_tokens=range_tokens,
        upper=from_ts,
        upper_exclusive=True,
    )
    return sum(_stock_delta(event) for event in events)


def _floor_to_bucket(ts: datetime, bucket: str) -> datetime:
    if bucket == "second":
        return ts.replace(microsecond=0)
    if bucket == "minute":
        return ts.replace(second=0, microsecond=0)
    if bucket == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        day_start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start - timedelta(days=day_start.weekday())
    if bucket == "month":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported bucket: {bucket}")


def _next_bucket(ts: datetime, bucket: str) -> datetime:
    if bucket == "second":
        return ts + timedelta(seconds=1)
    if bucket == "minute":
        return ts + timedelta(minutes=1)
    if bucket == "hour":
        return ts + timedelta(hours=1)
    if bucket == "day":
        return ts + timedelta(days=1)
    if bucket == "week":
        return ts + timedelta(weeks=1)
    if bucket == "month":
        if ts.month == 12:
            return ts.replace(year=ts.year + 1, month=1)
        return ts.replace(month=ts.month + 1)
    raise ValueError(f"unsupported bucket: {bucket}")


def _iter_buckets(from_ts: datetime, to_ts: datetime, bucket: str):
    current = _floor_to_bucket(from_ts, bucket)
    end = _floor_to_bucket(to_ts, bucket)
    while current <= end:
        yield current
        current = _next_bucket(current, bucket)


def _count_buckets(from_ts: datetime, to_ts: datetime, bucket: str) -> int:
    return sum(1 for _ in _iter_buckets(from_ts, to_ts, bucket))


def resolve_auto_bucket(from_ts: str, to_ts: str) -> str:
    from_dt = _parse_kline_timestamp(from_ts)
    to_dt = _parse_kline_timestamp(to_ts)
    span_seconds = (to_dt - from_dt).total_seconds()
    if span_seconds <= 10 * 60:
        chosen = "second"
    elif span_seconds <= 12 * 3600:
        chosen = "minute"
    elif span_seconds <= 2 * 86400:
        chosen = "hour"
    elif span_seconds <= 120 * 86400:
        chosen = "day"
    elif span_seconds <= 730 * 86400:
        chosen = "week"
    else:
        chosen = "month"

    order = ["second", "minute", "hour", "day", "week", "month"]
    index = order.index(chosen)
    while index < len(order):
        bucket = order[index]
        if _count_buckets(from_dt, to_dt, bucket) <= 500:
            return bucket
        index += 1
    return "month"


def build_history_kline(
    *,
    from_ts: str,
    to_ts: str,
    bucket: str,
    query: str = "",
    range_tokens: list[str] | None = None,
) -> dict[str, Any]:
    from_dt = _parse_kline_timestamp(from_ts)
    to_dt = _parse_kline_timestamp(to_ts)
    from_sql = _format_kline_sql_timestamp(from_dt)
    to_sql = _format_kline_sql_timestamp(to_dt)
    resolved_bucket = (
        resolve_auto_bucket(from_sql, to_sql) if bucket == "auto" else bucket
    )

    balance = _compute_balance_before(
        from_sql,
        query=query,
        range_tokens=range_tokens,
    )
    events = list_kline_events(
        query=query,
        range_tokens=range_tokens,
        from_ts=from_sql,
        to_ts=to_sql,
    )
    events_by_bucket: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        bucket_start = _floor_to_bucket(
            _parse_kline_timestamp(event["timestamp"]),
            resolved_bucket,
        )
        key = _format_kline_bucket_time(bucket_start)
        events_by_bucket.setdefault(key, []).append(event)

    candles: list[dict[str, Any]] = []
    totals = {
        "inboundCount": 0,
        "outboundCount": 0,
        "stockOutboundCount": 0,
        "netChange": 0,
    }
    running_balance = balance

    for bucket_start in _iter_buckets(from_dt, to_dt, resolved_bucket):
        bucket_key = _format_kline_bucket_time(bucket_start)
        bucket_events = events_by_bucket.get(bucket_key, [])

        open_balance = running_balance
        high = open_balance
        low = open_balance
        close = open_balance
        inbound_count = 0
        outbound_count = 0
        stock_outbound_count = 0

        for event in bucket_events:
            if event["type"] == "inbound":
                inbound_count += 1
            elif event["type"] == "outbound":
                outbound_count += 1
                if event.get("inbound_record_id") is not None:
                    stock_outbound_count += 1

            running_balance += _stock_delta(event)
            high = max(high, running_balance)
            low = min(low, running_balance)
            close = running_balance

        net_change = inbound_count - stock_outbound_count
        candles.append(
            {
                "time": bucket_key,
                "open": open_balance,
                "high": high,
                "low": low,
                "close": close,
                "inboundCount": inbound_count,
                "outboundCount": outbound_count,
                "stockOutboundCount": stock_outbound_count,
                "netChange": net_change,
            }
        )
        totals["inboundCount"] += inbound_count
        totals["outboundCount"] += outbound_count
        totals["stockOutboundCount"] += stock_outbound_count
        totals["netChange"] += net_change

    return {
        "bucket": resolved_bucket,
        "from": _format_kline_api_timestamp(from_dt),
        "to": _format_kline_api_timestamp(to_dt),
        "candles": candles,
        "totals": totals,
    }


def fifo_preview_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    return list_inventory(limit=count)


def count_search_inventory(substring: str) -> int:
    return _count_search_table("accounts", substring)


def search_inventory(
    substring: str,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = _search_table(
        "accounts",
        substring,
        columns=(
            "t.id, t.username, t.password, t.email, t.email_password, t.url, "
            "t.created_at, COALESCE(an.note, '') AS note"
        ),
        order_by="t.created_at ASC, t.id ASC",
        offset=offset,
        limit=limit,
    )
    return [
        {
            **row,
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def count_search_outbound_history(substring: str) -> int:
    return _count_search_table("outbound_records", substring)


def search_outbound_history(
    substring: str,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = _search_table(
        "outbound_records",
        substring,
        columns=(
            "t.id, t.username, t.password, t.email, t.email_password, t.url, "
            "t.inbound_at, t.outbound_at, t.inbound_record_id, "
            "COALESCE(an.note, '') AS note"
        ),
        order_by="t.outbound_at DESC, t.id DESC",
        offset=offset,
        limit=limit,
    )
    return [
        {
            **row,
            "inbound_at": row["inbound_at"],
            "outbound_at": row["outbound_at"],
            "inbound_record_id": row.get("inbound_record_id"),
        }
        for row in rows
    ]


def count_search_inbound_history(substring: str) -> int:
    return _count_search_table("inbound_records", substring)


def search_inbound_history(
    substring: str,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    rows = _search_table(
        "inbound_records",
        substring,
        columns=(
            "t.id, t.username, t.password, t.email, t.email_password, t.url, "
            "t.inbound_at, COALESCE(an.note, '') AS note"
        ),
        order_by="t.inbound_at DESC, t.id DESC",
        offset=offset,
        limit=limit,
    )
    return [_row_to_inbound_dict(row) for row in rows]


def outbound_oldest_many(count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.username, a.password, a.email, a.email_password, a.url,
                   a.created_at, a.inbound_record_id, COALESCE(an.note, '') AS note
            FROM accounts AS a
            LEFT JOIN account_notes AS an ON an.username = a.username
            ORDER BY a.created_at ASC, a.id ASC
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
                    "note": _note_from_row(row),
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


def _row_to_separator_rule(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "separator": row["separator"],
        "enabled": bool(row["enabled"]),
        "built_in": bool(row["built_in"]),
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
    }


def _validate_separator_rule_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError("规则名称不能为空")
    if len(value) > 40:
        raise ValueError("规则名称不能超过 40 个字符")
    return value


def _validate_separator_rule_separator(separator: str) -> str:
    value = separator.strip()
    if not value:
        raise ValueError("分隔符不能为空")
    if "\n" in value or "\r" in value:
        raise ValueError("分隔符不能包含换行符")
    if len(value) > 20:
        raise ValueError("分隔符长度不能超过 20 个字符")
    return value


def _count_enabled_separator_rules(
    conn: sqlite3.Connection,
    *,
    exclude_id: str | None = None,
) -> int:
    if exclude_id:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM separator_rules
            WHERE enabled = 1 AND id != ?
            """,
            (exclude_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM separator_rules WHERE enabled = 1"
        ).fetchone()
    return int(row["n"])


def list_separator_rules() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, separator, enabled, built_in, sort_order, created_at
            FROM separator_rules
            ORDER BY sort_order ASC, created_at ASC
            """
        ).fetchall()
    return [_row_to_separator_rule(row) for row in rows]


def list_enabled_separators() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT separator
            FROM separator_rules
            WHERE enabled = 1
            ORDER BY sort_order ASC, created_at ASC
            """
        ).fetchall()
    return [row["separator"] for row in rows]


def create_separator_rule(name: str, separator: str) -> dict[str, Any]:
    validated_name = _validate_separator_rule_name(name)
    validated_separator = _validate_separator_rule_separator(separator)
    rule_id = uuid.uuid4().hex
    with _connect() as conn:
        existing = conn.execute(
            "SELECT 1 FROM separator_rules WHERE separator = ? LIMIT 1",
            (validated_separator,),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"分隔符「{validated_separator}」已存在")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM separator_rules"
        ).fetchone()["m"]
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO separator_rules (
                id, name, separator, enabled, built_in, sort_order, created_at
            ) VALUES (?, ?, ?, 1, 0, ?, ?)
            """,
            (rule_id, validated_name, validated_separator, int(max_order) + 1, now),
        )
        row = conn.execute(
            """
            SELECT id, name, separator, enabled, built_in, sort_order, created_at
            FROM separator_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    return _row_to_separator_rule(row)


def update_separator_rule(
    rule_id: str,
    *,
    name: str | None = None,
    separator: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, separator, enabled, built_in, sort_order, created_at
            FROM separator_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        if row is None:
            raise ValueError("分隔规则不存在")

        new_name = (
            _validate_separator_rule_name(name) if name is not None else row["name"]
        )
        new_separator = (
            _validate_separator_rule_separator(separator)
            if separator is not None
            else row["separator"]
        )
        new_enabled = enabled if enabled is not None else bool(row["enabled"])

        if separator is not None and new_separator != row["separator"]:
            duplicate = conn.execute(
                """
                SELECT 1
                FROM separator_rules
                WHERE separator = ? AND id != ?
                LIMIT 1
                """,
                (new_separator, rule_id),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(f"分隔符「{new_separator}」已存在")

        if not new_enabled:
            if _count_enabled_separator_rules(conn, exclude_id=rule_id) == 0:
                raise ValueError("至少需要保留一条启用的分隔规则")

        conn.execute(
            """
            UPDATE separator_rules
            SET name = ?, separator = ?, enabled = ?
            WHERE id = ?
            """,
            (new_name, new_separator, int(new_enabled), rule_id),
        )
        updated = conn.execute(
            """
            SELECT id, name, separator, enabled, built_in, sort_order, created_at
            FROM separator_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    return _row_to_separator_rule(updated)


def delete_separator_rule(rule_id: str) -> None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, separator, enabled, built_in, sort_order, created_at
            FROM separator_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        if row is None:
            raise ValueError("分隔规则不存在")
        if row["built_in"]:
            raise ValueError("不能删除内置分隔规则")
        if row["enabled"]:
            if _count_enabled_separator_rules(conn, exclude_id=rule_id) == 0:
                raise ValueError("至少需要保留一条启用的分隔规则")
        conn.execute("DELETE FROM separator_rules WHERE id = ?", (rule_id,))
