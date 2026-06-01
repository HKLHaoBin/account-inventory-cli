"""FastAPI service for the account inventory web UI."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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


class AccountPayload(BaseModel):
    id: str
    username: str
    password: str
    email: str | None = None
    emailPassword: str | None = None
    url: str | None = None
    inboundAt: str


class OutboundRecordPayload(AccountPayload):
    outboundAt: str


class SearchResultPayload(BaseModel):
    id: str
    source: Literal["inventory", "history"]
    account: AccountPayload | OutboundRecordPayload
    matchedField: str


class SearchPayload(BaseModel):
    results: list[SearchResultPayload]


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


class DashboardPayload(BaseModel):
    stats: StatsPayload
    fifoPreview: list[AccountPayload]
    recentActivities: list[ActivityPayload]


class InboundPreviewRequest(BaseModel):
    text: str = ""


class ClipboardIgnoreRequest(BaseModel):
    text: str = ""


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


class InboundPreviewPayload(BaseModel):
    rows: list[InboundPreviewRow]


class InboundCommitLine(BaseModel):
    clientId: str
    line: str


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


class OutboundPasteCommitPayload(BaseModel):
    rows: list[OutboundPasteResultRow]
    successCount: int
    errorCount: int
    clipboardText: str


class FifoQuantityRequest(BaseModel):
    quantity: int = 1


class OutboundByUsernameRequest(BaseModel):
    username: str


class FifoPreviewPayload(BaseModel):
    max: int
    quantity: int
    rows: list[AccountPayload]


class FifoCommitPayload(FifoPreviewPayload):
    clipboardText: str


class OutboundByUsernamePayload(BaseModel):
    account: AccountPayload
    clipboardText: str


def _account_payload(row: dict) -> AccountPayload:
    return AccountPayload(
        id=str(row["id"]),
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=row["created_at"],
    )


def _outbound_record_payload(row: dict) -> OutboundRecordPayload:
    return OutboundRecordPayload(
        id=str(row["id"]),
        username=row["username"],
        password=row["password"],
        email=row["email"],
        emailPassword=row["email_password"],
        url=row["url"],
        inboundAt=row["inbound_at"],
        outboundAt=row["outbound_at"],
    )


def _matched_field(row: dict, query: str) -> str:
    q = query.casefold()
    for key in ("username", "password", "email", "email_password", "url"):
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
    )


def _parse_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _preview_rows_from_lines(lines: list[str]) -> list[InboundPreviewRow]:
    parsed_usernames: list[str] = []
    parsed_by_line: dict[str, tuple[str, str, str | None, str | None, str | None]] = {}

    for line in lines:
        try:
            parsed = parse_account_line(line)
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
            ) or parse_account_line(line)
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
        fifoPreview=[_account_payload(row) for row in db.fifo_preview_many(5)],
        recentActivities=[
            ActivityPayload(**activity)
            for activity in db.list_recent_activities(limit=10)
        ],
    )


@app.get("/api/search", response_model=SearchPayload)
def search_accounts(q: str = "") -> SearchPayload:
    query = q.strip()
    if not query:
        return SearchPayload(results=[])

    results: list[SearchResultPayload] = []
    for row in db.search_inventory(query):
        results.append(
            SearchResultPayload(
                id=f"inv-{row['id']}",
                source="inventory",
                account=_account_payload(row),
                matchedField=_matched_field(row, query),
            )
        )

    for row in db.search_outbound_history(query):
        results.append(
            SearchResultPayload(
                id=f"hist-{row['id']}",
                source="history",
                account=_outbound_record_payload(row),
                matchedField=_matched_field(row, query),
            )
        )

    return SearchPayload(results=results)


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
            parsed_usernames.append(parse_account_line(item.line)[0])
        except ValueError:
            continue

    inventory_exists = db.exists_in_inventory_many(parsed_usernames)
    outbound_exists = db.exists_in_outbound_many(parsed_usernames)
    outbound_times = db.get_latest_outbound_times(parsed_usernames)
    seen: set[str] = set()
    results: list[InboundCommitResultRow] = []

    for item in payload.rows:
        try:
            username, password, email, email_password, url = parse_account_line(item.line)
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
        results.append(
            InboundCommitResultRow(
                **base,
                category="pending" if is_pending else "ready",
                lastOutboundAt=outbound_times.get(username) if is_pending else None,
                status="success",
                message="入库成功",
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
def commit_fifo(payload: FifoQuantityRequest) -> FifoCommitPayload:
    global _ignored_clipboard_text

    max_count = db.count_inventory()
    quantity = min(max(payload.quantity, 0), max_count)
    records = db.outbound_oldest_many(quantity)
    rows = [_account_payload({**record, "id": index + 1}) for index, record in enumerate(records)]
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
            username, password, email, email_password, url = parse_account_line(line)
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

    committed = {
        row["client_id"]: _outbound_paste_result_payload(row)
        for row in db.commit_outbound_paste_rows(parsed_rows)
    }

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

    clipboard_text = _format_account_row(record)
    _ignored_clipboard_text = clipboard_text or None
    return OutboundByUsernamePayload(
        account=_account_payload({**record, "id": username}),
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
                valid_lines, rejected_count = extract_valid_account_lines(text)
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
