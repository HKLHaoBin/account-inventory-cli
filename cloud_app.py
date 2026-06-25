"""Cloud-mode local client entry point.

Provides embedded static frontend, clipboard watching, and API proxying to a
configured remote backend. Does not initialize or write local SQLite databases.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import httpx
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import clipboard
from cloud_config import CloudConfig, load_config, save_config
from frontend_static import mount_frontend
from remote_access import (
    REMOTE_ACCESS_HEADER,
    ensure_remote_access_websocket,
    install_remote_access,
)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

PROXY_SKIP_REQUEST_HEADERS = HOP_BY_HOP_HEADERS | {"accept-encoding"}
PROXY_SKIP_RESPONSE_HEADERS = HOP_BY_HOP_HEADERS | {"content-encoding"}

_ignored_clipboard_text: str | None = None


def resolve_web_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


ROOT = resolve_web_root()
WEB_OUT_DIR = ROOT / "web" / "out"

app = FastAPI(title="Account Inventory Cloud Client")
install_remote_access(app)
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


class CloudConfigPayload(BaseModel):
    cloudApiBaseUrl: str | None
    configured: bool
    remoteAccessTokenConfigured: bool


class CloudConfigUpdateRequest(BaseModel):
    cloudApiBaseUrl: str = ""
    remoteAccessToken: str | None = None


class ClipboardIgnoreRequest(BaseModel):
    text: str = ""


def _config_payload(config: CloudConfig | None = None) -> CloudConfigPayload:
    current = config or load_config()
    return CloudConfigPayload(
        cloudApiBaseUrl=current.cloud_api_base_url,
        configured=current.configured,
        remoteAccessTokenConfigured=bool(current.remote_access_token),
    )


def _forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in PROXY_SKIP_REQUEST_HEADERS:
            continue
        headers[key] = value
    return headers


def _response_headers(headers: httpx.Headers) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in PROXY_SKIP_RESPONSE_HEADERS:
            continue
        forwarded[key] = value
    return forwarded


@app.get("/local/config", response_model=CloudConfigPayload)
def get_local_config() -> CloudConfigPayload:
    return _config_payload()


@app.put("/local/config", response_model=CloudConfigPayload)
def put_local_config(payload: CloudConfigUpdateRequest) -> CloudConfigPayload:
    try:
        if payload.remoteAccessToken is None:
            config = save_config(payload.cloudApiBaseUrl)
        else:
            config = save_config(
                payload.cloudApiBaseUrl,
                remote_access_token=payload.remoteAccessToken,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _config_payload(config)


@app.post("/local/config/test")
def test_local_config() -> dict[str, bool]:
    config = load_config()
    if not config.configured or not config.cloud_api_base_url:
        raise HTTPException(status_code=428, detail="请先配置数据库服务地址")

    url = f"{config.cloud_api_base_url}/api/dashboard"
    headers: dict[str, str] = {}
    if config.remote_access_token:
        headers[REMOTE_ACCESS_HEADER] = config.remote_access_token
    try:
        response = requests.get(url, timeout=10, headers=headers)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"无法连接云端服务：{exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip() or f"云端返回 {response.status_code}"
        raise HTTPException(status_code=502, detail=detail)

    return {"ok": True}


@app.post("/api/clipboard/ignore")
def ignore_clipboard(payload: ClipboardIgnoreRequest) -> dict[str, bool]:
    global _ignored_clipboard_text
    _ignored_clipboard_text = payload.text or None
    return {"ok": True}


@app.websocket("/ws/clipboard")
async def clipboard_socket(websocket: WebSocket) -> None:
    if not await ensure_remote_access_websocket(websocket):
        return
    await websocket.accept()
    last_seen: str | None = None
    try:
        while True:
            text = clipboard.read_text()
            if text and text != last_seen and text != _ignored_clipboard_text:
                await websocket.send_json({"source": "clipboard", "text": text})
                last_seen = text
            await asyncio.sleep(0.8)
    except WebSocketDisconnect:
        return


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_api(request: Request, path: str) -> Response:
    config = load_config()
    if not config.configured or not config.cloud_api_base_url:
        raise HTTPException(status_code=428, detail="请先配置数据库服务地址")

    target = f"{config.cloud_api_base_url}/api/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    body = await request.body()
    headers = _forward_headers(request)
    if config.remote_access_token:
        headers[REMOTE_ACCESS_HEADER] = config.remote_access_token

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                target,
                content=body,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接云端服务：{exc}") from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


def _browser_host(host: str) -> str:
    normalized = host.strip()
    if normalized in {"", "0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    if normalized.startswith("[") and normalized.endswith("]"):
        return normalized[1:-1]
    return normalized


def _browser_url(host: str, port: int) -> str:
    browser_host = _browser_host(host)
    url_host = browser_host
    if ":" in browser_host and not browser_host.startswith("["):
        url_host = f"[{browser_host}]"
    return f"http://{url_host}:{int(port)}/"


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((_browser_host(host), int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _open_browser_when_ready(
    host: str,
    port: int,
    *,
    timeout_seconds: float = 12.0,
    check_interval: float = 0.25,
) -> None:
    url = _browser_url(host, port)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port):
            try:
                webbrowser.open(url, new=2)
            except Exception as exc:
                print(f"无法自动打开浏览器：{exc}", file=sys.stderr)
            return
        time.sleep(check_interval)


def open_browser_after_start(host: str, port: int) -> threading.Thread:
    thread = threading.Thread(
        target=_open_browser_when_ready,
        args=(host, port),
        daemon=True,
    )
    thread.start()
    return thread


def main() -> None:
    mount_frontend(app, WEB_OUT_DIR)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", "8000"))
    open_browser_after_start(host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
