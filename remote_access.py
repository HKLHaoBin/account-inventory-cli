"""Unified remote access gate for non-loopback HTTP and WebSocket traffic."""

from __future__ import annotations

import ipaddress
import os
import secrets
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

REMOTE_ACCESS_TOKEN_ENV = "REMOTE_ACCESS_TOKEN"
REMOTE_ACCESS_HEADER = "X-Remote-Access-Token"
REMOTE_ACCESS_COOKIE = "remote_access_token"

_PUBLIC_GET_PATHS = {"/remote-access"}
_PUBLIC_API_PATHS = {
    ("POST", "/api/remote-access/session"),
    ("DELETE", "/api/remote-access/session"),
}


class RemoteAccessSessionRequest(BaseModel):
    token: str = ""


def expected_token() -> str:
    return os.getenv(REMOTE_ACCESS_TOKEN_ENV, "").strip()


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().lower()
    if normalized == "testclient":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            return mapped.is_loopback
    return False


def should_enforce(client_host: str | None) -> bool:
    return not is_loopback_host(client_host)


def token_from_request(request: Request) -> str | None:
    header_token = request.headers.get(REMOTE_ACCESS_HEADER, "").strip()
    if header_token:
        return header_token
    cookie_token = request.cookies.get(REMOTE_ACCESS_COOKIE, "").strip()
    return cookie_token or None


def token_from_websocket(websocket: WebSocket) -> str | None:
    cookie_token = websocket.cookies.get(REMOTE_ACCESS_COOKIE, "").strip()
    return cookie_token or None


def is_valid_token(token: str | None) -> bool:
    expected = expected_token()
    if not expected or not token:
        return False
    return secrets.compare_digest(token.strip(), expected)


def _is_public_path(method: str, path: str) -> bool:
    if method == "GET" and path in _PUBLIC_GET_PATHS:
        return True
    return (method.upper(), path) in _PUBLIC_API_PATHS


def _remote_access_login_html(next_path: str) -> str:
    safe_next = quote(next_path or "/", safe="/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>远程访问验证</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .card {{
      width: min(420px, calc(100vw - 32px));
      padding: 24px;
      border-radius: 16px;
      background: #111827;
      border: 1px solid #334155;
      box-shadow: 0 20px 40px rgba(15, 23, 42, 0.45);
    }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    p {{ margin: 0 0 16px; color: #94a3b8; line-height: 1.5; }}
    label {{ display: block; margin-bottom: 8px; font-size: 14px; }}
    input {{
      width: 100%;
      box-sizing: border-box;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #475569;
      background: #0b1220;
      color: #f8fafc;
    }}
    button {{
      margin-top: 16px;
      width: 100%;
      padding: 10px 12px;
      border: 0;
      border-radius: 10px;
      background: #2563eb;
      color: white;
      font-weight: 600;
      cursor: pointer;
    }}
    .error {{ margin-top: 12px; color: #fca5a5; min-height: 20px; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>远程访问验证</h1>
    <p>当前连接来自非本机地址，请输入远程访问令牌后继续。</p>
    <form id="login-form">
      <label for="token">远程访问令牌</label>
      <input id="token" name="token" type="password" autocomplete="off" required />
      <button type="submit">验证并进入</button>
      <div id="error" class="error"></div>
    </form>
  </div>
  <script>
    const form = document.getElementById("login-form");
    const errorEl = document.getElementById("error");
    const nextPath = decodeURIComponent("{safe_next}");
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      errorEl.textContent = "";
      const token = document.getElementById("token").value.trim();
      if (!token) {{
        errorEl.textContent = "请输入远程访问令牌";
        return;
      }}
      try {{
        const response = await fetch("/api/remote-access/session", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ token }}),
        }});
        if (!response.ok) {{
          let detail = "令牌无效";
          try {{
            const payload = await response.json();
            if (payload.detail) detail = payload.detail;
          }} catch (_) {{}}
          errorEl.textContent = detail;
          return;
        }}
        window.location.href = nextPath || "/";
      }} catch (_) {{
        errorEl.textContent = "验证失败，请稍后重试";
      }}
    }});
  </script>
</body>
</html>"""


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REMOTE_ACCESS_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=REMOTE_ACCESS_COOKIE, path="/")


def install_remote_access(app: FastAPI) -> None:
    @app.middleware("http")
    async def remote_access_middleware(request: Request, call_next):
        client_host = request.client.host if request.client else None
        path = request.url.path

        if not should_enforce(client_host):
            return await call_next(request)

        if _is_public_path(request.method, path):
            return await call_next(request)

        if not expected_token():
            return JSONResponse(
                status_code=403,
                content={"detail": "REMOTE_ACCESS_TOKEN is not configured"},
            )

        if is_valid_token(token_from_request(request)):
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid remote access token"},
            )

        next_path = path
        if request.url.query:
            next_path = f"{path}?{request.url.query}"
        return RedirectResponse(
            url=f"/remote-access?next={quote(next_path, safe='')}",
            status_code=302,
        )

    @app.get("/remote-access", include_in_schema=False)
    def remote_access_page(next: str = "/") -> HTMLResponse:
        return HTMLResponse(_remote_access_login_html(next))

    @app.post("/api/remote-access/session")
    def create_remote_access_session(
        payload: RemoteAccessSessionRequest,
    ) -> JSONResponse:
        if not expected_token():
            raise HTTPException(
                status_code=403,
                detail="REMOTE_ACCESS_TOKEN is not configured",
            )
        if not is_valid_token(payload.token):
            raise HTTPException(status_code=401, detail="invalid remote access token")
        response = JSONResponse({"ok": True})
        _set_session_cookie(response, payload.token.strip())
        return response

    @app.delete("/api/remote-access/session")
    def delete_remote_access_session() -> JSONResponse:
        response = JSONResponse({"ok": True})
        _clear_session_cookie(response)
        return response


async def ensure_remote_access_websocket(websocket: WebSocket) -> bool:
    client_host = websocket.client.host if websocket.client else None
    if not should_enforce(client_host):
        return True

    if not expected_token():
        await websocket.close(code=1008, reason="REMOTE_ACCESS_TOKEN is not configured")
        return False

    if not is_valid_token(token_from_websocket(websocket)):
        await websocket.close(code=1008, reason="invalid remote access token")
        return False

    return True
