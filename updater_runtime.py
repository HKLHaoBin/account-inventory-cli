"""Runtime helpers for update checks and updater sidecar management."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

import updater

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RUNTIME_FILE_NAME = ".updater.runtime.json"
STATUS_FILE_NAME = ".updater.status.json"
LOCK_FILE_NAME = ".updater.pid"
SIDECAR_DIR_NAME = ".updater-sidecar"
UPDATE_ADMIN_TOKEN_ENV = "UPDATE_ADMIN_TOKEN"
AUTO_UPDATE_ENV = "UPDATE_AUTO_ENABLED"
AUTO_UPDATE_INTERVAL_ENV = "UPDATE_INTERVAL_HOURS"

_runtime_payload: dict[str, Any] = {}
_watcher_pid: int = 0
BUSY_UPDATE_STATES = {
    "checking",
    "downloading",
    "extracting",
    "backup",
    "applying",
    "stopping",
    "restarting",
    "rollback",
    "launching",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_app_version(root: Path = ROOT) -> str:
    version_file = root / "VERSION"
    try:
        value = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    return value or "0.0.0-dev"


def _json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_update_status(root: Path = ROOT) -> dict[str, Any]:
    payload = _json_file(root / STATUS_FILE_NAME)
    payload.setdefault("timestamp", "")
    payload.setdefault("state", "idle")
    payload.setdefault("message", "not checked yet")
    payload.setdefault("phase", "idle")
    payload.setdefault("repo", os.getenv("UPDATER_GITHUB_REPO", updater.GITHUB_REPO))
    payload["local_version"] = read_app_version(root)
    return payload


def write_runtime_info(host: str, port: int, root: Path = ROOT) -> dict[str, Any]:
    mode = "exe" if getattr(sys, "frozen", False) else "python"
    payload: dict[str, Any] = {
        "timestamp": now_iso(),
        "host": host,
        "port": int(port),
        "backend_pid": os.getpid(),
        "backend_mode": mode,
        "backend_executable": str(Path(sys.executable).resolve()) if mode == "exe" else "",
        "backend_script": str((root / "app.py").resolve()) if mode == "python" else "",
        "python_executable": str(Path(sys.executable).resolve()) if mode == "python" else "",
        "app_version": read_app_version(root),
    }
    (root / RUNTIME_FILE_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _runtime_payload.clear()
    _runtime_payload.update(payload)
    return payload


def current_runtime(root: Path = ROOT) -> dict[str, Any]:
    if _runtime_payload:
        return dict(_runtime_payload)
    payload = _json_file(root / RUNTIME_FILE_NAME)
    if payload:
        return payload
    return {
        "port": int(os.getenv("PORT", "8000")),
        "backend_pid": os.getpid(),
        "backend_mode": "exe" if getattr(sys, "frozen", False) else "python",
        "backend_executable": str(Path(sys.executable).resolve()) if getattr(sys, "frozen", False) else "",
        "backend_script": str((root / "app.py").resolve()),
        "python_executable": str(Path(sys.executable).resolve()),
        "app_version": read_app_version(root),
    }


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                output = (proc.stdout or "").strip()
                if not output or "no tasks are running" in output.lower():
                    return False
                return str(pid) in output
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_lock_pid(root: Path = ROOT) -> int:
    try:
        raw = (root / LOCK_FILE_NAME).read_text(encoding="utf-8").strip()
        return int(raw or "0")
    except Exception:
        return 0


def _terminate_pid(pid: int) -> None:
    if pid <= 0 or not is_pid_running(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass


def wait_for_update_lock_release(root: Path = ROOT, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pid = _read_lock_pid(root)
        if pid <= 0 or not is_pid_running(pid):
            return True
        time.sleep(0.25)
    return False


def stop_update_watcher(root: Path = ROOT) -> None:
    global _watcher_pid
    lock_pid = _read_lock_pid(root)
    for pid in {lock_pid, _watcher_pid}:
        if pid > 0 and pid != os.getpid():
            _terminate_pid(pid)
    _watcher_pid = 0
    wait_for_update_lock_release(root)


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    flags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    flags |= subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return flags


def _copy_updater_exe_for_sidecar(root: Path = ROOT) -> Path:
    source = root / "updater.exe"
    if not source.exists():
        raise FileNotFoundError("updater.exe is missing")
    sidecar_dir = root / SIDECAR_DIR_NAME
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar = sidecar_dir / f"updater-{int(time.time())}.exe"
    shutil.copy2(source, sidecar)
    return sidecar


def _updater_command(root: Path = ROOT) -> list[str]:
    if (root / "updater.exe").exists():
        return [str(_copy_updater_exe_for_sidecar(root))]
    script = root / "updater.py"
    return [str(Path(sys.executable).resolve()), str(script)]


def _runtime_args(root: Path = ROOT) -> list[str]:
    runtime = current_runtime(root)
    args = [
        "--work-dir",
        str(root),
        "--backend-pid",
        str(int(runtime.get("backend_pid") or os.getpid())),
        "--port",
        str(int(runtime.get("port") or os.getenv("PORT", "8000"))),
        "--backend-mode",
        str(runtime.get("backend_mode") or ("exe" if getattr(sys, "frozen", False) else "python")),
        "--repo",
        os.getenv("UPDATER_GITHUB_REPO", updater.GITHUB_REPO),
    ]
    if runtime.get("backend_executable"):
        args.extend(["--backend-executable", str(runtime["backend_executable"])])
    if runtime.get("backend_script"):
        args.extend(["--backend-script", str(runtime["backend_script"])])
    if runtime.get("python_executable"):
        args.extend(["--python-executable", str(runtime["python_executable"])])
    return args


def _popen_detached(command: list[str], root: Path = ROOT) -> subprocess.Popen[Any]:
    kwargs: dict[str, Any] = {
        "cwd": str(root),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = _creation_flags()
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def launch_update_watcher(root: Path = ROOT) -> int:
    global _watcher_pid
    if _read_lock_pid(root) > 0 and is_pid_running(_read_lock_pid(root)):
        return _read_lock_pid(root)
    command = _updater_command(root) + ["--watch", "--interval-hours", os.getenv(AUTO_UPDATE_INTERVAL_ENV, "24")]
    command.extend(_runtime_args(root))
    process = _popen_detached(command, root)
    _watcher_pid = int(process.pid)
    return _watcher_pid


def launch_update_once(root: Path = ROOT) -> int:
    stop_update_watcher(root)
    command = _updater_command(root) + ["--restore-watch"]
    command.extend(_runtime_args(root))
    process = _popen_detached(command, root)
    return int(process.pid)


def maybe_start_auto_update(root: Path = ROOT) -> None:
    if os.getenv(AUTO_UPDATE_ENV, "").strip() in {"0", "false", "False", "no"}:
        return
    if not getattr(sys, "frozen", False) and os.getenv(AUTO_UPDATE_ENV, "").strip() not in {"1", "true", "True", "yes"}:
        return
    try:
        launch_update_watcher(root)
    except Exception:
        return


def check_latest_update(root: Path = ROOT) -> dict[str, Any]:
    repo = os.getenv("UPDATER_GITHUB_REPO", updater.GITHUB_REPO)
    local_version = read_app_version(root)
    current = read_update_status(root)
    reset_at = int(current.get("github_rate_limit_reset") or 0)
    has_github_token = bool(
        os.getenv("UPDATER_GITHUB_TOKEN", "").strip()
        or os.getenv("GITHUB_TOKEN", "").strip()
    )
    if (
        current.get("state") == "error"
        and reset_at > int(time.time())
        and not has_github_token
    ):
        return current

    try:
        result = updater.inspect_latest_release(repo, local_version)
        state = "update_available" if result.get("update_available") else "idle"
        message = "new release found" if result.get("update_available") else "already up-to-date"
        updater.write_phase_status(root, state, message, "completed", result)
        return read_update_status(root)
    except updater.GitHubRateLimitError as exc:
        extra: dict[str, Any] = {"repo": repo, "local_version": local_version}
        if exc.reset_epoch:
            extra["github_rate_limit_reset"] = exc.reset_epoch
        if exc.reset_at:
            extra["github_rate_limit_reset_at"] = exc.reset_at
        updater.write_phase_status(root, "error", str(exc), "failed", extra)
        return read_update_status(root)
    except Exception as exc:
        updater.write_phase_status(root, "error", f"update check failed: {exc}", "failed", {"repo": repo})
        return read_update_status(root)


def require_update_admin_token(token: str | None) -> None:
    expected = os.getenv(UPDATE_ADMIN_TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="UPDATE_ADMIN_TOKEN is not configured")
    if not token or token.strip() != expected:
        raise HTTPException(status_code=403, detail="invalid update token")


def trigger_update(token: str | None, root: Path = ROOT) -> dict[str, Any]:
    require_update_admin_token(token)
    status = read_update_status(root)
    if status.get("state") in BUSY_UPDATE_STATES and status.get("phase") != "sleeping":
        raise HTTPException(status_code=409, detail="update is already running")
    pid = launch_update_once(root)
    updater.write_phase_status(
        root,
        "launching",
        "update sidecar started",
        "launching",
        {"repo": os.getenv("UPDATER_GITHUB_REPO", updater.GITHUB_REPO), "sidecar_pid": pid},
    )
    return read_update_status(root)
