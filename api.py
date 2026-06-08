"""FastAPI service for the account inventory web UI."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

import clipboard
import database as db
import updater_runtime
from parser import extract_valid_account_lines, format_account, parse_account_line

InboundCategory = Literal["ready", "duplicate", "pending", "invalid", "batchDuplicate"]
OutboundCategory = Literal[
    "inInventory", "notInInventory", "inHistory", "invalid", "batchDuplicate"
]
CommitStatus = Literal["success", "error", "warning", "skipped"]

app = FastAPI(title="Account Inventory API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()
_ignored_clipboard_text: str | None = None

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _normalize_pagination(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[int, int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    return page, page_size, offset


def _total_pages(total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    return math.ceil(total / page_size)


def _page_inventory_usernames(usernames: list[str]) -> list[str]:
    if not usernames:
        return []
    return sorted(db.exists_in_inventory_many(usernames))


class AccountPayload(BaseModel):
    id: str
    username: str
    password: str
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    inboundAt: str
    note: str | None = None


class OutboundRecordPayload(BaseModel):
    id: str
    username: str
    password: str
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    inboundAt: str | None = None
    inboundRecordId: str | None = None
    outboundAt: str
    note: str | None = None


class InboundRecordPayload(BaseModel):
    id: str
    username: str
    password: str
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    inboundAt: str
    note: str | None = None
    hasOutbound: bool = False


class HistoryRecordPayload(BaseModel):
    id: str
    type: Literal["inbound", "outbound"]
    username: str
    password: str
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    inboundAt: str | None = None
    outboundAt: str | None = None
    timestamp: str
    note: str | None = None
    hasOutbound: bool = False


class InboundHistoryPayload(BaseModel):
    records: list[InboundRecordPayload]
    total: int = 0
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE
    totalPages: int = 0


class HistoryPayload(BaseModel):
    records: list[HistoryRecordPayload]
    total: int = 0
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE
    totalPages: int = 0
    inventoryUsernames: list[str] = Field(default_factory=list)


class HistoryExportPayload(BaseModel):
    text: str
    count: int


class KlineCandlePayload(BaseModel):
    time: str
    open: int
    high: int
    low: int
    close: int
    inboundCount: int
    outboundCount: int
    stockOutboundCount: int
    netChange: int


class KlineTotalsPayload(BaseModel):
    inboundCount: int
    outboundCount: int
    stockOutboundCount: int
    netChange: int


class KlinePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    bucket: Literal["hour", "day", "week", "month"]
    from_: str = Field(alias="from")
    to: str
    candles: list[KlineCandlePayload]
    totals: KlineTotalsPayload
    dataFrom: str | None = None
    dataTo: str | None = None
    hasData: bool = False


class SearchResultPayload(BaseModel):
    id: str
    source: Literal["inventory", "history"]
    account: AccountPayload | OutboundRecordPayload
    matchedField: str


class SearchPayload(BaseModel):
    results: list[SearchResultPayload]
    total: int = 0
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE
    totalPages: int = 0
    inventoryTotal: int = 0
    historyTotal: int = 0


class OutboundHistoryPayload(BaseModel):
    records: list[OutboundRecordPayload]
    total: int = 0
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE
    totalPages: int = 0
    inventoryUsernames: list[str] = Field(default_factory=list)


class ReinboundFromHistoryPayload(BaseModel):
    account: AccountPayload
    clipboardText: str


class OutboundFromInboundHistoryPayload(BaseModel):
    record: OutboundRecordPayload
    clipboardText: str


class InventoryPayload(BaseModel):
    records: list[AccountPayload]
    total: int = 0
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE
    totalPages: int = 0


class ActivityPayload(BaseModel):
    id: str
    type: Literal["inbound", "outbound"]
    username: str
    timestamp: str


class StatsPayload(BaseModel):
    inventoryCount: int
    todayInbound: int
    todayOutbound: int
    pendingCount: int = 0


class DatabaseInfoPayload(BaseModel):
    id: str
    name: str
    fileName: str
    path: str
    createdAt: str
    active: bool
    inventoryCount: int
    todayInbound: int
    todayOutbound: int


class DatabaseListPayload(BaseModel):
    databases: list[DatabaseInfoPayload]
    activeDatabaseId: str


class DashboardPayload(BaseModel):
    stats: StatsPayload
    database: DatabaseInfoPayload
    fifoPreview: list[AccountPayload]
    recentActivities: list[ActivityPayload]


class InboundPreviewRequest(BaseModel):
    text: str = ""


class ClipboardIgnoreRequest(BaseModel):
    text: str = ""


class CreateDatabaseRequest(BaseModel):
    name: str = ""


class CloneDatabaseRequest(BaseModel):
    name: str = ""


class RenameDatabaseRequest(BaseModel):
    name: str = ""


class InboundPreviewRow(BaseModel):
    clientId: str
    line: str
    username: str | None = None
    password: str | None = None
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    category: InboundCategory
    reason: str | None = None
    lastOutboundAt: str | None = None
    note: str | None = None


class InboundPreviewPayload(BaseModel):
    rows: list[InboundPreviewRow]


class InboundCommitLine(BaseModel):
    clientId: str
    line: str
    note: str | None = None
    overwriteNote: bool = False


class InboundCommitRequest(BaseModel):
    rows: list[InboundCommitLine] = Field(default_factory=list)
    approvedPendingClientIds: list[str] = Field(default_factory=list)


class InboundCommitResultRow(InboundPreviewRow):
    status: CommitStatus
    message: str


class InboundCommitPayload(BaseModel):
    rows: list[InboundCommitResultRow]
    successCount: int
    errorCount: int
    warningCount: int


class OutboundPasteCommitLine(BaseModel):
    clientId: str
    line: str
    note: str | None = None
    overwriteNote: bool = False


class OutboundPasteCommitRequest(BaseModel):
    rows: list[OutboundPasteCommitLine] = Field(default_factory=list)


class OutboundPasteResultRow(BaseModel):
    clientId: str
    line: str
    username: str | None = None
    password: str | None = None
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    category: OutboundCategory
    status: Literal["success", "error"]
    message: str
    note: str | None = None


class OutboundPasteCommitPayload(BaseModel):
    rows: list[OutboundPasteResultRow]
    successCount: int
    errorCount: int
    clipboardText: str


class FifoQuantityRequest(BaseModel):
    quantity: int = 1


class FifoNoteEntry(BaseModel):
    username: str
    note: str | None = None
    overwriteNote: bool = False


class FifoCommitRequest(BaseModel):
    quantity: int = 1
    notes: list[FifoNoteEntry] = Field(default_factory=list)


class OutboundByUsernameRequest(BaseModel):
    username: str
    note: str | None = None
    overwriteNote: bool = False


class FifoPreviewPayload(BaseModel):
    max: int
    quantity: int
    rows: list[AccountPayload]


class FifoCommitPayload(FifoPreviewPayload):
    clipboardText: str


class OutboundByUsernamePayload(BaseModel):
    account: AccountPayload
    clipboardText: str


class SeparatorRulePayload(BaseModel):
    id: str
    name: str
    separator: str
    enabled: bool
    builtIn: bool
    createdAt: str


class CreateSeparatorRuleRequest(BaseModel):
    name: str
    separator: str


class UpdateSeparatorRuleRequest(BaseModel):
    name: str | None = None
    separator: str | None = None
    enabled: bool | None = None


class SeparatorRuleListPayload(BaseModel):
    rules: list[SeparatorRulePayload]


def _enabled_separators() -> list[str]:
    return db.list_enabled_separators()


def _parse_line(line: str):
    return parse_account_line(line, _enabled_separators())


def _extract_valid_lines(text: str):
    return extract_valid_account_lines(text, _enabled_separators())


def _account_payload(row: dict) -> AccountPayload:
    return AccountPayload(
        id=str(row["id"]),
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=row["created_at"],
        note=row.get("note") or "",
    )


def _outbound_inbound_fields(row: dict) -> tuple[str | None, str | None]:
    inbound_record_id = row.get("inbound_record_id")
    if inbound_record_id is None:
        return None, None
    return row["inbound_at"], str(inbound_record_id)


def _outbound_record_payload(row: dict) -> OutboundRecordPayload:
    inbound_at, inbound_record_id = _outbound_inbound_fields(row)
    return OutboundRecordPayload(
        id=str(row["id"]),
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=inbound_at,
        inboundRecordId=inbound_record_id,
        outboundAt=row["outbound_at"],
        note=row.get("note") or "",
    )


def _inbound_record_payload(row: dict) -> InboundRecordPayload:
    return InboundRecordPayload(
        id=str(row["id"]),
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=row["inbound_at"],
        note=row.get("note") or "",
        hasOutbound=bool(row.get("has_outbound")),
    )


def _history_record_payload(row: dict) -> HistoryRecordPayload:
    record_type = row["type"]
    if record_type == "outbound":
        inbound_at, _ = _outbound_inbound_fields(row)
    else:
        inbound_at = row["inbound_at"]
    return HistoryRecordPayload(
        id=f"{record_type}-{row['id']}",
        type=record_type,
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=inbound_at,
        outboundAt=row.get("outbound_at"),
        timestamp=row["timestamp"],
        note=row.get("note") or "",
        hasOutbound=bool(row.get("has_outbound")) if record_type == "inbound" else False,
    )


def _matched_field(row: dict, query: str) -> str:
    q = query.casefold()
    for key in ("username", "password", "email", "email_password", "url", "note"):
        value = row.get(key)
        if value and q in str(value).casefold():
            return str(value)
    return row.get("username") or ""


def _format_account_row(row: dict) -> str:
    return format_account(
        row["username"],
        row["password"],
        row["email"],
        row["email_password"],
        row["url"],
    )


def _outbound_paste_result_payload(row: dict) -> OutboundPasteResultRow:
    return OutboundPasteResultRow(
        clientId=row["client_id"],
        line=row["line"],
        username=row.get("username"),
        password=row.get("password"),
        email=row.get("email"),
        emailPassword=row.get("email_password"),
        url=row.get("url"),
        category=row["category"],
        status=row["status"],
        message=row["message"],
        note=row.get("note") or "",
    )


def _database_payload(row: dict) -> DatabaseInfoPayload:
    return DatabaseInfoPayload(
        id=str(row["id"]),
        name=row["name"],
        fileName=row["file_name"],
        path=row["path"],
        createdAt=row["created_at"],
        active=bool(row["active"]),
        inventoryCount=int(row["inventory_count"]),
        todayInbound=int(row["today_inbound"]),
        todayOutbound=int(row["today_outbound"]),
    )


def _separator_rule_payload(row: dict) -> SeparatorRulePayload:
    return SeparatorRulePayload(
        id=row["id"],
        name=row["name"],
        separator=row["separator"],
        enabled=bool(row["enabled"]),
        builtIn=bool(row["built_in"]),
        createdAt=row["created_at"],
    )


def _parse_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_kline_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            parsed = datetime.fromisoformat(text)
            if end_of_day:
                return parsed.replace(hour=23, minute=59, second=59, microsecond=0)
            return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无效的日期时间：{text}") from exc


def _resolve_kline_range(
    from_value: str | None,
    to_value: str | None,
) -> tuple[str, str]:
    now = datetime.now().replace(microsecond=0)
    to_dt = _parse_kline_datetime(to_value, end_of_day=True) or now
    from_dt = _parse_kline_datetime(from_value) or (to_dt - timedelta(days=90))
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
    return (
        from_dt.strftime("%Y-%m-%d %H:%M:%S"),
        to_dt.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _resolve_clamped_kline_window(
    request_from_dt: datetime,
    request_to_dt: datetime,
    data_from_dt: datetime,
    data_to_dt: datetime,
) -> tuple[datetime, datetime]:
    request_span = request_to_dt - request_from_dt
    data_span = data_to_dt - data_from_dt

    if request_span > data_span:
        return data_from_dt, data_to_dt

    if request_to_dt < data_from_dt:
        return data_from_dt, min(data_from_dt + request_span, data_to_dt)

    if request_from_dt > data_to_dt:
        return max(data_to_dt - request_span, data_from_dt), data_to_dt

    return max(request_from_dt, data_from_dt), min(request_to_dt, data_to_dt)


def _kline_payload(row: dict) -> KlinePayload:
    return KlinePayload(
        bucket=row["bucket"],
        from_=row["from"],
        to=row["to"],
        candles=[KlineCandlePayload(**candle) for candle in row["candles"]],
        totals=KlineTotalsPayload(**row["totals"]),
        dataFrom=row.get("dataFrom"),
        dataTo=row.get("dataTo"),
        hasData=bool(row.get("hasData", False)),
    )


def _empty_kline_payload(
    *,
    from_ts: str,
    to_ts: str,
    data_from: str | None,
    data_to: str | None,
    has_data: bool,
) -> KlinePayload:
    from_dt = db._parse_kline_timestamp(from_ts)
    to_dt = db._parse_kline_timestamp(to_ts)
    return KlinePayload(
        bucket=db.resolve_auto_bucket(from_ts, to_ts),
        from_=db._format_kline_api_timestamp(from_dt),
        to=db._format_kline_api_timestamp(to_dt),
        candles=[],
        totals=KlineTotalsPayload(
            inboundCount=0,
            outboundCount=0,
            stockOutboundCount=0,
            netChange=0,
        ),
        dataFrom=data_from,
        dataTo=data_to,
        hasData=has_data,
    )


def _preview_rows_from_lines(lines: list[str]) -> list[InboundPreviewRow]:
    parsed_usernames: list[str] = []
    parsed_by_line: dict[str, tuple[str, str, str | None, str | None, str | None]] = {}

    for line in lines:
        try:
            parsed = _parse_line(line)
        except ValueError:
            continue
        parsed_by_line[line] = parsed
        parsed_usernames.append(parsed[0])

    inventory_exists = db.exists_in_inventory_many(parsed_usernames)
    outbound_exists = db.exists_in_outbound_many(parsed_usernames)
    outbound_times = db.get_latest_outbound_times(parsed_usernames)
    seen: set[str] = set()
    rows: list[InboundPreviewRow] = []

    for index, line in enumerate(lines, start=1):
        client_id = f"line-{index}"
        try:
            username, password, email, email_password, url = parsed_by_line.get(
                line
            ) or _parse_line(line)
        except ValueError as exc:
            rows.append(
                InboundPreviewRow(
                    clientId=client_id,
                    line=line,
                    category="invalid",
                    reason=str(exc),
                )
            )
            continue

        base = {
            "clientId": client_id,
            "line": line,
            "username": username,
            "password": password,
            "email": email,
            "emailPassword": email_password,
            "url": url,
        }

        if username in inventory_exists:
            rows.append(
                InboundPreviewRow(
                    **base,
                    category="duplicate",
                    reason=f"账号 {username} 已在库存中",
                )
            )
            continue

        if username in seen:
            rows.append(
                InboundPreviewRow(
                    **base,
                    category="batchDuplicate",
                    reason="本批次内账号重复",
                )
            )
            continue

        seen.add(username)
        if username in outbound_exists:
            rows.append(
                InboundPreviewRow(
                    **base,
                    category="pending",
                    lastOutboundAt=outbound_times.get(username),
                )
            )
        else:
            rows.append(InboundPreviewRow(**base, category="ready"))

    return rows


@app.get("/api/dashboard", response_model=DashboardPayload)
def get_dashboard() -> DashboardPayload:
    return DashboardPayload(
        stats=StatsPayload(
            inventoryCount=db.count_inventory(),
            todayInbound=db.count_today_inbound(),
            todayOutbound=db.count_today_outbound(),
            pendingCount=0,
        ),
        database=_database_payload(db.get_active_database_info()),
        fifoPreview=[_account_payload(row) for row in db.fifo_preview_many(5)],
        recentActivities=[
            ActivityPayload(**activity)
            for activity in db.list_recent_activities(limit=10)
        ],
    )


@app.get("/api/databases", response_model=DatabaseListPayload)
def get_databases() -> DatabaseListPayload:
    databases = [_database_payload(row) for row in db.list_database_info()]
    active = next((item.id for item in databases if item.active), "")
    return DatabaseListPayload(databases=databases, activeDatabaseId=active)


@app.post("/api/databases", response_model=DatabaseInfoPayload)
def create_database(payload: CreateDatabaseRequest) -> DatabaseInfoPayload:
    try:
        return _database_payload(db.create_database(payload.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/databases/{database_id}/clone", response_model=DatabaseInfoPayload)
def clone_database(
    database_id: str,
    payload: CloneDatabaseRequest,
) -> DatabaseInfoPayload:
    try:
        return _database_payload(db.clone_database(database_id, payload.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/databases/{database_id}/activate", response_model=DatabaseInfoPayload)
def activate_database(database_id: str) -> DatabaseInfoPayload:
    try:
        return _database_payload(db.set_active_database(database_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/databases/{database_id}", response_model=DatabaseInfoPayload)
def rename_database(
    database_id: str,
    payload: RenameDatabaseRequest,
) -> DatabaseInfoPayload:
    try:
        return _database_payload(db.rename_database(database_id, payload.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/databases/{database_id}", response_model=DatabaseInfoPayload)
def delete_database(
    database_id: str,
    x_update_token: str | None = Header(default=None),
) -> DatabaseInfoPayload:
    updater_runtime.require_update_admin_token(x_update_token)
    try:
        return _database_payload(db.delete_database(database_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/separator-rules", response_model=SeparatorRuleListPayload)
def get_separator_rules() -> SeparatorRuleListPayload:
    return SeparatorRuleListPayload(
        rules=[_separator_rule_payload(row) for row in db.list_separator_rules()]
    )


@app.post("/api/separator-rules", response_model=SeparatorRulePayload)
def create_separator_rule(payload: CreateSeparatorRuleRequest) -> SeparatorRulePayload:
    try:
        return _separator_rule_payload(
            db.create_separator_rule(payload.name, payload.separator)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/separator-rules/{rule_id}", response_model=SeparatorRulePayload)
def update_separator_rule(
    rule_id: str,
    payload: UpdateSeparatorRuleRequest,
) -> SeparatorRulePayload:
    try:
        return _separator_rule_payload(
            db.update_separator_rule(
                rule_id,
                name=payload.name,
                separator=payload.separator,
                enabled=payload.enabled,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/separator-rules/{rule_id}")
def delete_separator_rule(rule_id: str) -> dict[str, bool]:
    try:
        db.delete_separator_rule(rule_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inventory", response_model=InventoryPayload)
def get_inventory(
    page: int = 1,
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, alias="pageSize"),
    q: str = "",
    sort_by: str = Query(default="inboundAt", alias="sortBy"),
    sort_dir: str = Query(default="asc", alias="sortDir"),
) -> InventoryPayload:
    page, page_size, offset = _normalize_pagination(page, page_size)
    query = q.strip()
    total = db.count_inventory(query=query)
    rows = db.list_inventory(
        query=query,
        sort_by=sort_by,
        sort_dir=sort_dir,
        offset=offset,
        limit=page_size,
    )
    return InventoryPayload(
        records=[_account_payload(row) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=_total_pages(total, page_size),
    )


def _search_result_inventory(row: dict, query: str) -> SearchResultPayload:
    return SearchResultPayload(
        id=f"inv-{row['id']}",
        source="inventory",
        account=_account_payload(row),
        matchedField=_matched_field(row, query),
    )


def _search_result_history(row: dict, query: str) -> SearchResultPayload:
    return SearchResultPayload(
        id=f"hist-{row['id']}",
        source="history",
        account=_outbound_record_payload(row),
        matchedField=_matched_field(row, query),
    )


@app.get("/api/search", response_model=SearchPayload)
def search_accounts(
    q: str = "",
    page: int = 1,
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, alias="pageSize"),
    source: Literal["all", "inventory", "history"] = "all",
) -> SearchPayload:
    query = q.strip()
    page, page_size, offset = _normalize_pagination(page, page_size)

    if not query:
        return SearchPayload(
            results=[],
            total=0,
            page=page,
            pageSize=page_size,
            totalPages=0,
            inventoryTotal=0,
            historyTotal=0,
        )

    inventory_total = db.count_search_inventory(query)
    history_total = db.count_search_outbound_history(query)

    if source == "inventory":
        total = inventory_total
        rows = db.search_inventory(query, offset=offset, limit=page_size)
        results = [_search_result_inventory(row, query) for row in rows]
        return SearchPayload(
            results=results,
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=_total_pages(total, page_size),
            inventoryTotal=inventory_total,
            historyTotal=history_total,
        )

    if source == "history":
        total = history_total
        rows = db.search_outbound_history(query, offset=offset, limit=page_size)
        results = [_search_result_history(row, query) for row in rows]
        return SearchPayload(
            results=results,
            total=total,
            page=page,
            pageSize=page_size,
            totalPages=_total_pages(total, page_size),
            inventoryTotal=inventory_total,
            historyTotal=history_total,
        )

    total = inventory_total + history_total
    results: list[SearchResultPayload] = []
    if offset < inventory_total:
        inventory_limit = min(page_size, inventory_total - offset)
        for row in db.search_inventory(
            query,
            offset=offset,
            limit=inventory_limit,
        ):
            results.append(_search_result_inventory(row, query))

    remaining = page_size - len(results)
    if remaining > 0:
        history_offset = max(0, offset - inventory_total)
        for row in db.search_outbound_history(
            query,
            offset=history_offset,
            limit=remaining,
        ):
            results.append(_search_result_history(row, query))

    return SearchPayload(
        results=results,
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=_total_pages(total, page_size),
        inventoryTotal=inventory_total,
        historyTotal=history_total,
    )


@app.get("/api/outbound/history", response_model=OutboundHistoryPayload)
def get_outbound_history(
    q: str = "",
    ranges: list[str] = Query(default=[]),
    page: int = 1,
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, alias="pageSize"),
) -> OutboundHistoryPayload:
    page, page_size, offset = _normalize_pagination(page, page_size)
    query = q.strip()
    total = db.count_outbound_history(query=query, range_tokens=ranges)
    rows = db.list_outbound_history(
        query=query,
        range_tokens=ranges,
        offset=offset,
        limit=page_size,
    )
    page_usernames = [row["username"] for row in rows]
    return OutboundHistoryPayload(
        records=[_outbound_record_payload(row) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=_total_pages(total, page_size),
        inventoryUsernames=_page_inventory_usernames(page_usernames),
    )


@app.post(
    "/api/outbound/history/{record_id}/reinbound",
    response_model=ReinboundFromHistoryPayload,
)
def reinbound_from_outbound_history(record_id: int) -> ReinboundFromHistoryPayload:
    row = db.get_outbound_record(record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="出库记录不存在")

    username = row["username"]
    if db.exists_in_inventory(username):
        raise HTTPException(status_code=400, detail=f"账号 {username} 已在库存中")

    try:
        db.insert_account(
            username,
            row["password"],
            row["email"],
            row["email_password"],
            row["url"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    note = str(row.get("note") or "").strip()
    if note:
        db.set_account_note(username, note, overwrite=False)

    inventory_rows = db.search_inventory(username)
    account_row = next(
        (item for item in inventory_rows if item["username"] == username),
        None,
    )
    if account_row is None:
        raise HTTPException(status_code=500, detail="入库后未找到库存记录")

    return ReinboundFromHistoryPayload(
        account=_account_payload(
            {**account_row, "created_at": account_row["created_at"]}
        ),
        clipboardText=_format_account_row(row),
    )


@app.post(
    "/api/inbound/history/{record_id}/outbound",
    response_model=OutboundFromInboundHistoryPayload,
)
def outbound_from_inbound_history(record_id: int) -> OutboundFromInboundHistoryPayload:
    try:
        row = db.outbound_from_inbound_history(record_id)
    except ValueError as exc:
        message = str(exc)
        if "不存在" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    return OutboundFromInboundHistoryPayload(
        record=_outbound_record_payload(row),
        clipboardText=_format_account_row(row),
    )


@app.get("/api/inbound/history", response_model=InboundHistoryPayload)
def get_inbound_history(
    q: str = "",
    ranges: list[str] = Query(default=[]),
    page: int = 1,
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, alias="pageSize"),
) -> InboundHistoryPayload:
    page, page_size, offset = _normalize_pagination(page, page_size)
    query = q.strip()
    total = db.count_inbound_history(query=query, range_tokens=ranges)
    rows = db.list_inbound_history(
        query=query,
        range_tokens=ranges,
        offset=offset,
        limit=page_size,
    )
    return InboundHistoryPayload(
        records=[_inbound_record_payload(row) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=_total_pages(total, page_size),
    )


@app.get("/api/history", response_model=HistoryPayload)
def get_history(
    type: Literal["all", "inbound", "outbound"] = "all",
    q: str = "",
    ranges: list[str] = Query(default=[]),
    page: int = 1,
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, alias="pageSize"),
) -> HistoryPayload:
    page, page_size, offset = _normalize_pagination(page, page_size)
    query = q.strip()
    if type == "inbound":
        total = db.count_inbound_history(query=query, range_tokens=ranges)
    elif type == "outbound":
        total = db.count_outbound_history(query=query, range_tokens=ranges)
    else:
        total = db.count_unified_history(query=query, range_tokens=ranges)
    rows = db.list_unified_history(
        history_type=type,
        query=query,
        range_tokens=ranges,
        offset=offset,
        limit=page_size,
    )
    outbound_usernames = [
        row["username"] for row in rows if row["type"] == "outbound"
    ]
    return HistoryPayload(
        records=[_history_record_payload(row) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
        totalPages=_total_pages(total, page_size),
        inventoryUsernames=_page_inventory_usernames(outbound_usernames),
    )


@app.get("/api/history/export", response_model=HistoryExportPayload)
def export_history(
    type: Literal["all", "inbound", "outbound"] = "all",
    q: str = "",
    ranges: list[str] = Query(default=[]),
) -> HistoryExportPayload:
    rows = db.export_history_records(
        history_type=type,
        query=q.strip(),
        range_tokens=ranges,
    )
    lines = [_format_account_row(row) for row in rows]
    text = "\n".join(line for line in lines if line)
    return HistoryExportPayload(text=text, count=len(rows))


@app.get("/api/history/kline", response_model=KlinePayload)
def get_history_kline(
    from_value: str | None = Query(default=None, alias="from"),
    to_value: str | None = Query(default=None, alias="to"),
    bucket: Literal["auto", "hour", "day", "week", "month"] = "auto",
    q: str = "",
    ranges: list[str] = Query(default=[]),
) -> KlinePayload:
    from_ts, to_ts = _resolve_kline_range(from_value, to_value)
    bounds = db.get_kline_data_bounds(query=q.strip(), range_tokens=ranges)

    if not bounds["hasData"]:
        return _empty_kline_payload(
            from_ts=from_ts,
            to_ts=to_ts,
            data_from=None,
            data_to=None,
            has_data=False,
        )

    data_from_dt = db._parse_kline_timestamp(bounds["dataFrom"])
    data_to_dt = db._parse_kline_timestamp(bounds["dataTo"])
    request_from_dt = db._parse_kline_timestamp(from_ts)
    request_to_dt = db._parse_kline_timestamp(to_ts)
    clamped_from_dt, clamped_to_dt = _resolve_clamped_kline_window(
        request_from_dt,
        request_to_dt,
        data_from_dt,
        data_to_dt,
    )

    clamped_from_ts = db._format_kline_sql_timestamp(clamped_from_dt)
    clamped_to_ts = db._format_kline_sql_timestamp(clamped_to_dt)
    result = db.build_history_kline(
        from_ts=clamped_from_ts,
        to_ts=clamped_to_ts,
        bucket=bucket,
        query=q.strip(),
        range_tokens=ranges,
    )
    result["dataFrom"] = bounds["dataFrom"]
    result["dataTo"] = bounds["dataTo"]
    result["hasData"] = True
    return _kline_payload(result)


@app.get("/api/runtime/update-status")
def get_update_status() -> dict[str, object]:
    return updater_runtime.read_update_status()


@app.post("/api/runtime/check-update")
def check_update() -> dict[str, object]:
    return updater_runtime.check_latest_update()


@app.post("/api/runtime/trigger-update")
def trigger_update(x_update_token: str | None = Header(default=None)) -> dict[str, object]:
    return updater_runtime.trigger_update(x_update_token)


@app.post("/api/inbound/preview", response_model=InboundPreviewPayload)
def preview_inbound(payload: InboundPreviewRequest) -> InboundPreviewPayload:
    return InboundPreviewPayload(rows=_preview_rows_from_lines(_parse_lines(payload.text)))


@app.post("/api/clipboard/ignore")
def ignore_clipboard(payload: ClipboardIgnoreRequest) -> dict[str, bool]:
    global _ignored_clipboard_text
    _ignored_clipboard_text = payload.text or None
    return {"ok": True}


@app.post("/api/inbound/commit", response_model=InboundCommitPayload)
def commit_inbound(payload: InboundCommitRequest) -> InboundCommitPayload:
    approved = set(payload.approvedPendingClientIds)
    parsed_usernames: list[str] = []
    for item in payload.rows:
        try:
            parsed_usernames.append(_parse_line(item.line)[0])
        except ValueError:
            continue

    inventory_exists = db.exists_in_inventory_many(parsed_usernames)
    outbound_exists = db.exists_in_outbound_many(parsed_usernames)
    outbound_times = db.get_latest_outbound_times(parsed_usernames)
    seen: set[str] = set()
    results: list[InboundCommitResultRow] = []

    for item in payload.rows:
        try:
            username, password, email, email_password, url = _parse_line(item.line)
        except ValueError as exc:
            results.append(
                InboundCommitResultRow(
                    clientId=item.clientId,
                    line=item.line,
                    category="invalid",
                    reason=str(exc),
                    status="error",
                    message=str(exc),
                )
            )
            continue

        base = {
            "clientId": item.clientId,
            "line": item.line,
            "username": username,
            "password": password,
            "email": email,
            "emailPassword": email_password,
            "url": url,
        }

        if username in inventory_exists:
            message = f"账号 {username} 已在库存中"
            results.append(
                InboundCommitResultRow(
                    **base,
                    category="duplicate",
                    reason=message,
                    status="error",
                    message=message,
                )
            )
            continue

        if username in seen:
            message = "本批次内账号重复"
            results.append(
                InboundCommitResultRow(
                    **base,
                    category="batchDuplicate",
                    reason=message,
                    status="error",
                    message=message,
                )
            )
            continue

        seen.add(username)
        is_pending = username in outbound_exists
        if is_pending and item.clientId not in approved:
            results.append(
                InboundCommitResultRow(
                    **base,
                    category="pending",
                    lastOutboundAt=outbound_times.get(username),
                    status="warning",
                    message="曾出库账号未批准，已取消入库",
                )
            )
            continue

        try:
            db.insert_account(username, password, email, email_password, url)
        except ValueError as exc:
            results.append(
                InboundCommitResultRow(
                    **base,
                    category="duplicate",
                    reason=str(exc),
                    status="error",
                    message=str(exc),
                )
            )
            inventory_exists.add(username)
            continue

        inventory_exists.add(username)
        final_note = db.set_account_note(
            username,
            item.note,
            overwrite=item.overwriteNote,
        )
        results.append(
            InboundCommitResultRow(
                **base,
                category="pending" if is_pending else "ready",
                lastOutboundAt=outbound_times.get(username) if is_pending else None,
                status="success",
                message="入库成功",
                note=final_note,
            )
        )

    return InboundCommitPayload(
        rows=results,
        successCount=sum(1 for row in results if row.status == "success"),
        errorCount=sum(1 for row in results if row.status == "error"),
        warningCount=sum(1 for row in results if row.status == "warning"),
    )


@app.post("/api/outbound/fifo/preview", response_model=FifoPreviewPayload)
def preview_fifo(payload: FifoQuantityRequest) -> FifoPreviewPayload:
    max_count = db.count_inventory()
    quantity = min(max(payload.quantity, 0), max_count)
    return FifoPreviewPayload(
        max=max_count,
        quantity=quantity,
        rows=[_account_payload(row) for row in db.fifo_preview_many(quantity)],
    )


@app.post("/api/outbound/fifo/commit", response_model=FifoCommitPayload)
def commit_fifo(payload: FifoCommitRequest) -> FifoCommitPayload:
    global _ignored_clipboard_text

    max_count = db.count_inventory()
    quantity = min(max(payload.quantity, 0), max_count)
    records = db.outbound_oldest_many(quantity)
    note_by_username = {
        entry.username.strip(): entry
        for entry in payload.notes
        if entry.username.strip()
    }
    for record in records:
        entry = note_by_username.get(record["username"])
        if entry is None:
            continue
        record["note"] = db.set_account_note(
            record["username"],
            entry.note,
            overwrite=entry.overwriteNote,
        )
    rows = [
        _account_payload({**record, "id": index + 1, "created_at": record["created_at"]})
        for index, record in enumerate(records)
    ]
    clipboard_text = "\n".join(
        format_account(
            record["username"],
            record["password"],
            record["email"],
            record["email_password"],
            record["url"],
        )
        for record in records
    )
    _ignored_clipboard_text = clipboard_text or None
    return FifoCommitPayload(
        max=max_count,
        quantity=len(rows),
        rows=rows,
        clipboardText=clipboard_text,
    )


@app.post("/api/outbound-paste/commit", response_model=OutboundPasteCommitPayload)
def commit_outbound_paste(
    payload: OutboundPasteCommitRequest,
) -> OutboundPasteCommitPayload:
    global _ignored_clipboard_text

    parsed_rows: list[dict[str, object]] = []
    immediate_results: dict[str, OutboundPasteResultRow] = {}
    seen: set[str] = set()

    for item in payload.rows:
        line = item.line.strip()
        if not line:
            continue

        try:
            username, password, email, email_password, url = _parse_line(line)
        except ValueError as exc:
            immediate_results[item.clientId] = OutboundPasteResultRow(
                clientId=item.clientId,
                line=line,
                category="invalid",
                status="error",
                message=str(exc),
            )
            continue

        base = {
            "clientId": item.clientId,
            "line": line,
            "username": username,
            "password": password,
            "email": email,
            "emailPassword": email_password,
            "url": url,
        }

        if username in seen:
            immediate_results[item.clientId] = OutboundPasteResultRow(
                **base,
                category="batchDuplicate",
                status="error",
                message="本批次内账号重复",
            )
            continue

        seen.add(username)
        parsed_rows.append(
            {
                "client_id": item.clientId,
                "line": line,
                "username": username,
                "password": password,
                "email": email,
                "email_password": email_password,
                "url": url,
            }
        )

    note_by_client_id = {
        item.clientId: item for item in payload.rows if item.clientId
    }
    committed_rows = db.commit_outbound_paste_rows(parsed_rows)
    committed: dict[str, OutboundPasteResultRow] = {}
    for row in committed_rows:
        if row["status"] != "success":
            committed[row["client_id"]] = _outbound_paste_result_payload(row)
            continue
        item = note_by_client_id.get(row["client_id"])
        final_note = db.set_account_note(
            row["username"],
            item.note if item is not None else None,
            overwrite=item.overwriteNote if item is not None else False,
        )
        row["note"] = final_note
        committed[row["client_id"]] = _outbound_paste_result_payload(row)

    results: list[OutboundPasteResultRow] = []
    for item in payload.rows:
        row = immediate_results.get(item.clientId) or committed.get(item.clientId)
        if row is not None:
            results.append(row)

    success_rows = [row for row in results if row.status == "success"]
    clipboard_text = "\n".join(
        format_account(
            row.username or "",
            row.password or "",
            row.email,
            row.emailPassword,
            row.url,
        )
        for row in success_rows
    )
    _ignored_clipboard_text = clipboard_text or None
    return OutboundPasteCommitPayload(
        rows=results,
        successCount=len(success_rows),
        errorCount=sum(1 for row in results if row.status == "error"),
        clipboardText=clipboard_text,
    )


@app.post("/api/outbound/by-username", response_model=OutboundByUsernamePayload)
def commit_outbound_by_username(
    payload: OutboundByUsernameRequest,
) -> OutboundByUsernamePayload:
    global _ignored_clipboard_text

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="账号不能为空")

    record = db.outbound_by_username(username)
    if record is None:
        raise HTTPException(status_code=404, detail="账号不在库存中，无法出库")

    final_note = db.set_account_note(
        username,
        payload.note,
        overwrite=payload.overwriteNote,
    )
    record["note"] = final_note
    clipboard_text = _format_account_row(record)
    _ignored_clipboard_text = clipboard_text or None
    return OutboundByUsernamePayload(
        account=_account_payload({**record, "id": username, "created_at": record["created_at"]}),
        clipboardText=clipboard_text,
    )


@app.websocket("/ws/clipboard")
async def clipboard_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    last_seen: str | None = None
    try:
        while True:
            text = clipboard.read_text()
            if (
                text
                and text != last_seen
                and text != _ignored_clipboard_text
            ):
                valid_lines, rejected_count = _extract_valid_lines(text)
                if valid_lines:
                    normalized = "\n".join(valid_lines)
                    await websocket.send_json(
                        {
                            "source": "clipboard",
                            "text": normalized,
                            "validLines": valid_lines,
                            "rejectedCount": rejected_count,
                        }
                    )
                    last_seen = text
            await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return
