"""Shared static frontend mounting helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def frontend_file_for_path(web_out_dir: Path, path: str) -> Path:
    web_root = web_out_dir.resolve()
    web_index = web_root / "index.html"
    requested = (web_root / path).resolve()
    if requested.is_file() and web_root in requested.parents:
        return requested

    html_route = (web_root / f"{path}.html").resolve()
    if html_route.is_file() and web_root in html_route.parents:
        return html_route

    route_index = (web_root / path / "index.html").resolve()
    if route_index.is_file() and web_root in route_index.parents:
        return route_index

    return web_index


def mount_frontend(app: FastAPI, web_out_dir: Path) -> bool:
    web_out_dir = web_out_dir.resolve()
    web_index = web_out_dir / "index.html"
    if not web_index.is_file():
        return False

    next_assets = web_out_dir / "_next"
    if next_assets.is_dir():
        app.mount("/_next", StaticFiles(directory=next_assets), name="next-assets")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        icon = web_out_dir / "favicon.ico"
        if not icon.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(icon)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str = "") -> FileResponse:
        if path.startswith("api/") or path.startswith("ws/") or path.startswith("local/"):
            raise HTTPException(status_code=404)
        return FileResponse(frontend_file_for_path(web_out_dir, path))

    return True
