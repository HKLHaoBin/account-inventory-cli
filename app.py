"""Single-command web entry point.

Run with:
    python app.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import app
from updater_runtime import maybe_start_auto_update, write_runtime_info

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
WEB_OUT_DIR = WEB_DIR / "out"
WEB_INDEX = WEB_OUT_DIR / "index.html"


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def ensure_frontend_build() -> None:
    """Build the static frontend when the export output is missing."""
    if WEB_INDEX.exists():
        return
    if not WEB_DIR.exists():
        print("未找到 web 目录，仅启动 API 服务。", file=sys.stderr)
        return

    print("未找到 web/out，正在构建前端静态产物...")
    subprocess.run(
        [_npm_command(), "install"],
        cwd=WEB_DIR,
        check=True,
    )
    subprocess.run(
        [_npm_command(), "run", "build"],
        cwd=WEB_DIR,
        check=True,
    )


def mount_frontend() -> None:
    if not WEB_INDEX.exists():
        return

    next_assets = WEB_OUT_DIR / "_next"
    if next_assets.exists():
        app.mount("/_next", StaticFiles(directory=next_assets), name="next-assets")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        icon = WEB_OUT_DIR / "favicon.ico"
        if not icon.exists():
            raise HTTPException(status_code=404)
        return FileResponse(icon)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str = "") -> FileResponse:
        if path.startswith("api/") or path.startswith("ws/"):
            raise HTTPException(status_code=404)

        requested = (WEB_OUT_DIR / path).resolve()
        if requested.is_file() and WEB_OUT_DIR in requested.parents:
            return FileResponse(requested)

        route_index = (WEB_OUT_DIR / path / "index.html").resolve()
        if route_index.is_file() and WEB_OUT_DIR in route_index.parents:
            return FileResponse(route_index)

        return FileResponse(WEB_INDEX)


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
    ensure_frontend_build()
    mount_frontend()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", "8000"))
    write_runtime_info(host, port, ROOT)
    maybe_start_auto_update(ROOT)
    open_browser_after_start(host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
