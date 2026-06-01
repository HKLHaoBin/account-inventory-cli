from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import quote, unquote

import requests

if os.name == "nt":
    import msvcrt
else:
    import fcntl

GITHUB_REPO = os.getenv("UPDATER_GITHUB_REPO", "HKLHaoBin/account-inventory-cli")
GITHUB_RELEASE_LATEST_WEB = "https://github.com/{repo}/releases/latest"
GITHUB_RELEASE_DOWNLOAD_WEB = "https://github.com/{repo}/releases/download/{tag}/{asset}"
RELEASE_ZIP_NAME = "account-inventory-web-windows.zip"
RELEASE_SHA256_NAME = "account-inventory-web-windows.zip.sha256"
APP_EXE_NAME = "account-inventory-web.exe"
UPDATER_EXE_NAME = "updater.exe"

LOCK_FILE_NAME = ".updater.pid"
STATUS_FILE_NAME = ".updater.status.json"
RUNTIME_FILE_NAME = ".updater.runtime.json"
SIDECAR_DIR_NAME = ".updater-sidecar"
BACKUP_DIR = "data/updater-backups"

HOT_SINGLE_FILES = {"VERSION", "start-web.bat"}
LOCKED_SINGLE_FILES = {APP_EXE_NAME, UPDATER_EXE_NAME}
ALLOWED_SINGLE_FILES = HOT_SINGLE_FILES | LOCKED_SINGLE_FILES
ALLOWED_RESOURCE_DIRS = ("web/out",)
FORBIDDEN_PREFIXES = (
    ".git/",
    ".github/",
    ".next/",
    ".updater",
    "build/",
    "data/",
    "dist/",
    "release-package/",
    "web/node_modules/",
    "web/src/",
)
IO_RETRY_DELAY_MS = 500
IO_RETRY_MAX_ATTEMPTS = 6
DOWNLOAD_RETRY_MAX_ATTEMPTS = 5
DOWNLOAD_RETRY_BASE_DELAY_SECONDS = 2.0
DOWNLOAD_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

T = TypeVar("T")


@dataclass
class InstanceLock:
    path: Path
    file_obj: Any


@dataclass
class RuntimeContext:
    work_dir: Path
    port: int
    backend_pid: int
    backend_mode: str
    backend_executable: Optional[Path]
    backend_script: Optional[Path]
    python_executable: Optional[Path]
    app_version: str


@dataclass
class PreparedUpdate:
    repo: str
    latest_tag: str
    extract_path: Path
    backup_dir: Path
    summary: dict[str, Any]


class UpdateApplyError(RuntimeError):
    def __init__(self, message: str, new_backend_pid: int = 0):
        super().__init__(message)
        self.new_backend_pid = int(new_backend_pid)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def trace(work_dir: Path, stage: str, **extra: Any) -> None:
    payload: dict[str, Any] = {"timestamp": now_iso(), "stage": stage}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def write_status(work_dir: Path, state: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
    payload: dict[str, Any] = {
        "timestamp": now_iso(),
        "state": state,
        "message": message,
    }
    if extra:
        payload.update(extra)
    (work_dir / STATUS_FILE_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_phase_status(
    work_dir: Path,
    state: str,
    message: str,
    phase: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    payload = dict(extra or {})
    payload["phase"] = phase
    write_status(work_dir, state, message, payload)


def read_app_version(work_dir: Path) -> str:
    try:
        value = (work_dir / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    return value or "0.0.0-dev"


def parse_version(value: str) -> Optional[tuple[int, int, int]]:
    text = (value or "").strip()
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_remote_newer(local_version: str, remote_tag: str) -> bool:
    remote = parse_version(remote_tag)
    if remote is None:
        return False
    local = parse_version(local_version)
    if local is None:
        return True
    return remote > local


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


def acquire_single_instance_lock(work_dir: Path) -> Optional[InstanceLock]:
    lock_path = work_dir / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    file_obj = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            file_obj.seek(0)
            marker = file_obj.read(1)
            if not marker:
                file_obj.write("\0")
                file_obj.flush()
            file_obj.seek(0)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        file_obj.close()
        return None

    file_obj.seek(0)
    file_obj.truncate()
    file_obj.write(str(os.getpid()))
    file_obj.flush()
    return InstanceLock(path=lock_path, file_obj=file_obj)


def release_single_instance_lock(lock: Optional[InstanceLock]) -> None:
    if lock is None:
        return
    try:
        if os.name == "nt":
            lock.file_obj.seek(0)
            msvcrt.locking(lock.file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock.file_obj.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        lock.file_obj.close()
    except Exception:
        pass


def is_retryable_io_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        if exc.errno in {5, 13, 16, 26, 32, 33}:
            return True
        if getattr(exc, "winerror", None) in {5, 32, 33}:  # type: ignore[arg-type]
            return True
    return False


def retry_io(
    operation: str,
    func: Callable[[], T],
    *,
    work_dir: Optional[Path] = None,
    max_attempts: int = IO_RETRY_MAX_ATTEMPTS,
    delay_ms: int = IO_RETRY_DELAY_MS,
    trace_stage: str = "io:retry",
) -> T:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            result = func()
            if work_dir is not None and attempt > 1:
                trace(work_dir, f"{trace_stage}:ok", operation=operation, attempt=attempt)
            return result
        except Exception as exc:
            last_exc = exc
            can_retry = is_retryable_io_error(exc) and attempt < max_attempts
            if work_dir is not None:
                trace(
                    work_dir,
                    f"{trace_stage}:error",
                    operation=operation,
                    attempt=attempt,
                    retry=can_retry,
                    error=repr(exc),
                )
            if not can_retry:
                raise
            time.sleep(max(0.01, float(delay_ms) / 1000.0))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"retry failed without exception: {operation}")


def github_latest_release(repo: str, timeout: int = 20) -> dict[str, Any]:
    return github_latest_release_web(repo, timeout)


def github_latest_release_web(repo: str, timeout: int = 20) -> dict[str, Any]:
    url = GITHUB_RELEASE_LATEST_WEB.format(repo=repo.strip("/"))
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "account-inventory-updater",
    }
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    latest_url = str(getattr(response, "url", "") or url)
    tag = parse_github_release_tag_from_url(latest_url)
    if not tag:
        raise RuntimeError("could not resolve latest GitHub release tag")
    return github_release_from_tag(repo, tag, latest_url)


def parse_github_release_tag_from_url(url: str) -> str:
    match = re.search(r"/releases/tag/([^/?#]+)", url)
    return unquote(match.group(1)) if match else ""


def github_asset_download_url(repo: str, tag: str, asset_name: str) -> str:
    return GITHUB_RELEASE_DOWNLOAD_WEB.format(
        repo=repo.strip("/"),
        tag=quote(tag, safe=""),
        asset=quote(asset_name, safe=""),
    )


def github_release_from_tag(repo: str, tag: str, html_url: str = "") -> dict[str, Any]:
    return {
        "tag_name": tag,
        "name": "",
        "body": "",
        "published_at": "",
        "html_url": html_url,
        "assets": [
            {
                "name": RELEASE_ZIP_NAME,
                "browser_download_url": github_asset_download_url(repo, tag, RELEASE_ZIP_NAME),
            },
            {
                "name": RELEASE_SHA256_NAME,
                "browser_download_url": github_asset_download_url(repo, tag, RELEASE_SHA256_NAME),
            },
        ],
    }


def find_asset_url(release: dict[str, Any], asset_name: str) -> Optional[str]:
    for asset in release.get("assets") or []:
        if str(asset.get("name") or "") == asset_name:
            return asset.get("browser_download_url")
    return None


def release_summary(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_tag": str(release.get("tag_name") or ""),
        "release_title": str(release.get("name") or ""),
        "release_body": str(release.get("body") or ""),
        "release_published_at": str(release.get("published_at") or ""),
    }


def inspect_latest_release(repo: str, local_version: str) -> dict[str, Any]:
    release = github_latest_release(repo)
    summary = release_summary(release)
    latest_tag = str(release.get("tag_name") or "")
    zip_url = find_asset_url(release, RELEASE_ZIP_NAME)
    sha_url = find_asset_url(release, RELEASE_SHA256_NAME)
    update_available = is_remote_newer(local_version, latest_tag)
    return {
        "repo": repo,
        "local_version": local_version,
        "update_available": update_available,
        "assets_ready": bool(zip_url and sha_url),
        "release_zip_name": RELEASE_ZIP_NAME,
        "release_sha256_name": RELEASE_SHA256_NAME,
        **summary,
    }


def retry_delay_seconds(attempt: int) -> float:
    return DOWNLOAD_RETRY_BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))


def is_retryable_download_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = int(getattr(response, "status_code", 0) or 0)
        return status_code in DOWNLOAD_RETRY_STATUS_CODES
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.SSLError,
        ),
    )


def download_to(
    url: str,
    output_path: Path,
    timeout: int = 60,
    work_dir: Path | None = None,
    asset_name: str = "",
    max_attempts: int = DOWNLOAD_RETRY_MAX_ATTEMPTS,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = Path(f"{output_path}.part")
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        part_path.unlink(missing_ok=True)
        try:
            with requests.get(url, stream=True, timeout=timeout, allow_redirects=True) as response:
                response.raise_for_status()
                with part_path.open("wb") as fp:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            fp.write(chunk)
            part_path.replace(output_path)
            if work_dir is not None and attempt > 1:
                trace(work_dir, "download:ok", asset=asset_name or output_path.name, attempt=attempt)
            return
        except Exception as exc:
            part_path.unlink(missing_ok=True)
            retry = is_retryable_download_error(exc) and attempt < max(1, int(max_attempts))
            delay = retry_delay_seconds(attempt) if retry else 0
            if work_dir is not None:
                trace(
                    work_dir,
                    "download:error",
                    asset=asset_name or output_path.name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry=retry,
                    next_delay_seconds=delay,
                    error=repr(exc),
                )
            if not retry:
                raise
            time.sleep(delay)


def parse_sha256_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="ignore").strip()
    token = content.split()[0] if content else ""
    if not re.fullmatch(r"[a-fA-F0-9]{64}", token):
        raise ValueError("invalid sha256 file format")
    return token.lower()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            block = fp.read(1024 * 1024)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest().lower()


def normalize_rel_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_forbidden(rel_path: str) -> bool:
    rel = rel_path.strip("/")
    if rel in {LOCK_FILE_NAME, STATUS_FILE_NAME, RUNTIME_FILE_NAME}:
        return True
    return any(rel == prefix.strip("/") or rel.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def is_allowed(rel_path: str) -> bool:
    rel = rel_path.strip("/")
    if is_forbidden(rel):
        return False
    if rel in ALLOWED_SINGLE_FILES:
        return True
    return any(rel.startswith(f"{directory}/") for directory in ALLOWED_RESOURCE_DIRS)


def extract_release_root(extract_path: Path) -> Path:
    if (extract_path / "VERSION").exists() or (extract_path / APP_EXE_NAME).exists():
        return extract_path
    children = [item for item in extract_path.iterdir() if item.is_dir()]
    if len(children) == 1 and ((children[0] / "VERSION").exists() or (children[0] / APP_EXE_NAME).exists()):
        return children[0]
    return extract_path


def backup_targets(work_dir: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for rel in sorted(ALLOWED_SINGLE_FILES):
        src = work_dir / rel
        if src.exists() and src.is_file():
            dst = backup_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    for rel in ALLOWED_RESOURCE_DIRS:
        src = work_dir / rel
        if src.exists() and src.is_dir():
            dst = backup_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)


def apply_file_copy(src: Path, dst: Path, rel: str, work_dir: Path, stage: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    trace(work_dir, stage, action="copy:start", rel=rel, src=str(src), dst=str(dst))
    retry_io(f"copy {rel}", lambda: shutil.copy2(src, dst), work_dir=work_dir, trace_stage=stage)
    trace(work_dir, stage, action="copy:done", rel=rel)


def replace_file_atomically(src: Path, dst: Path, rel: str, work_dir: Path) -> None:
    temp_old = dst.with_name(f"{dst.name}.old.{int(time.time())}")
    renamed_old = False
    copied = False
    try:
        if dst.exists():
            retry_io(f"rename old {rel}", lambda: dst.rename(temp_old), work_dir=work_dir, trace_stage="apply:file")
            renamed_old = True
        apply_file_copy(src, dst, rel, work_dir, "apply:file")
        copied = True
    except Exception:
        if renamed_old and temp_old.exists():
            if dst.exists():
                retry_io(f"remove partial {rel}", lambda: dst.unlink(), work_dir=work_dir, trace_stage="rollback:file")
            retry_io(f"restore old {rel}", lambda: temp_old.rename(dst), work_dir=work_dir, trace_stage="rollback:file")
        raise
    finally:
        if copied and temp_old.exists() and dst.exists():
            retry_io(f"cleanup old {rel}", lambda: temp_old.unlink(), work_dir=work_dir, trace_stage="apply:file")


def replace_directory_from_stage(src_dir: Path, dst_dir: Path, rel: str, stage_root: Path, work_dir: Path) -> None:
    staged_dir = stage_root / rel
    staged_dir.parent.mkdir(parents=True, exist_ok=True)
    if staged_dir.exists():
        retry_io(f"cleanup stage {rel}", lambda: shutil.rmtree(staged_dir), work_dir=work_dir, trace_stage="apply:file")
    retry_io(f"copy stage {rel}", lambda: shutil.copytree(src_dir, staged_dir), work_dir=work_dir, trace_stage="apply:file")

    backup_old = stage_root / "old" / rel
    backup_old.parent.mkdir(parents=True, exist_ok=True)
    renamed_old = False
    try:
        if dst_dir.exists():
            retry_io(f"rename old dir {rel}", lambda: dst_dir.rename(backup_old), work_dir=work_dir, trace_stage="apply:file")
            renamed_old = True
        retry_io(f"deploy dir {rel}", lambda: shutil.copytree(staged_dir, dst_dir), work_dir=work_dir, trace_stage="apply:file")
    except Exception:
        if dst_dir.exists():
            retry_io(f"cleanup partial dir {rel}", lambda: shutil.rmtree(dst_dir), work_dir=work_dir, trace_stage="rollback:file")
        if renamed_old and backup_old.exists():
            retry_io(f"restore old dir {rel}", lambda: backup_old.rename(dst_dir), work_dir=work_dir, trace_stage="rollback:file")
        raise
    else:
        if renamed_old and backup_old.exists():
            retry_io(f"cleanup old dir backup {rel}", lambda: shutil.rmtree(backup_old), work_dir=work_dir, trace_stage="apply:file")


def apply_hot_targets(extracted_root: Path, work_dir: Path, stage_root: Path) -> list[str]:
    updated: list[str] = []
    for rel in sorted(HOT_SINGLE_FILES):
        src = extracted_root / rel
        if src.exists() and src.is_file() and is_allowed(rel):
            replace_file_atomically(src, work_dir / rel, rel, work_dir)
            updated.append(rel)

    for rel in ALLOWED_RESOURCE_DIRS:
        src_dir = extracted_root / rel
        if src_dir.exists() and src_dir.is_dir() and is_allowed(f"{rel}/index.html"):
            replace_directory_from_stage(src_dir, work_dir / rel, rel, stage_root, work_dir)
            updated.append(rel)
    return updated


def apply_locked_targets(extracted_root: Path, work_dir: Path) -> list[str]:
    updated: list[str] = []
    for rel in (APP_EXE_NAME, UPDATER_EXE_NAME):
        src = extracted_root / rel
        if src.exists() and src.is_file() and is_allowed(rel):
            replace_file_atomically(src, work_dir / rel, rel, work_dir)
            updated.append(rel)
    return updated


def count_skipped_files(extracted_root: Path) -> int:
    skipped = 0
    for src in extracted_root.rglob("*"):
        if not src.is_file():
            continue
        rel = normalize_rel_path(src, extracted_root)
        if not is_allowed(rel):
            skipped += 1
    return skipped


def restore_from_backup(backup_dir: Path, work_dir: Path) -> dict[str, Any]:
    restored: list[str] = []
    trace(work_dir, "rollback:start", backup_dir=str(backup_dir))

    for rel in sorted(ALLOWED_SINGLE_FILES):
        backup = backup_dir / rel
        dst = work_dir / rel
        if backup.exists() and backup.is_file():
            apply_file_copy(backup, dst, rel, work_dir, "rollback:file")
            restored.append(rel)
        elif dst.exists() and rel in LOCKED_SINGLE_FILES:
            retry_io(f"remove added {rel}", lambda d=dst: d.unlink(), work_dir=work_dir, trace_stage="rollback:file")

    for rel in ALLOWED_RESOURCE_DIRS:
        src_dir = backup_dir / rel
        dst_dir = work_dir / rel
        if not src_dir.exists() or not src_dir.is_dir():
            if dst_dir.exists():
                retry_io(f"remove newly created dir {rel}", lambda d=dst_dir: shutil.rmtree(d), work_dir=work_dir, trace_stage="rollback:file")
            continue
        if dst_dir.exists():
            retry_io(f"clear target dir for rollback {rel}", lambda d=dst_dir: shutil.rmtree(d), work_dir=work_dir, trace_stage="rollback:file")
        retry_io(f"restore dir {rel}", lambda s=src_dir, d=dst_dir: shutil.copytree(s, d), work_dir=work_dir, trace_stage="rollback:file")
        restored.append(rel)

    trace(work_dir, "rollback:done", restored_count=len(restored))
    return {"restored": restored, "restored_count": len(restored)}


def stop_backend_process(pid: int, wait_seconds: int = 25, work_dir: Optional[Path] = None) -> bool:
    if pid <= 0:
        return True

    def _trace(stage: str, **extra: Any) -> None:
        if work_dir is not None:
            trace(work_dir, stage, **extra)

    if not is_pid_running(pid):
        return True
    if os.name == "nt":
        _trace("backend:taskkill:start", pid=pid)
        result = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
        _trace(
            "backend:taskkill:result",
            pid=pid,
            returncode=result.returncode,
            stdout=(result.stdout or "").strip(),
            stderr=(result.stderr or "").strip(),
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    start = time.time()
    while time.time() - start < wait_seconds:
        if not is_pid_running(pid):
            return True
        time.sleep(0.5)

    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        return not is_pid_running(pid)
    return False


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_backend_detached(command: list[str], work_dir: Path) -> int:
    kwargs: dict[str, Any] = {
        "cwd": str(work_dir),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return int(process.pid)


def sync_runtime_context(ctx: RuntimeContext) -> None:
    runtime_file = ctx.work_dir / RUNTIME_FILE_NAME
    if not runtime_file.exists():
        ctx.app_version = read_app_version(ctx.work_dir)
        return
    try:
        payload = json.loads(runtime_file.read_text(encoding="utf-8"))
    except Exception:
        ctx.app_version = read_app_version(ctx.work_dir)
        return

    try:
        ctx.port = int(payload.get("port") or ctx.port)
    except Exception:
        pass
    try:
        ctx.backend_pid = int(payload.get("backend_pid") or ctx.backend_pid)
    except Exception:
        pass
    mode = str(payload.get("backend_mode") or "").strip()
    if mode in {"auto", "exe", "python"}:
        ctx.backend_mode = mode
    for field_name in ("backend_executable", "backend_script", "python_executable"):
        raw = str(payload.get(field_name) or "").strip()
        if raw:
            setattr(ctx, field_name, Path(raw).resolve())
    ctx.app_version = str(payload.get("app_version") or read_app_version(ctx.work_dir)).strip()


def resolve_restart_command(ctx: RuntimeContext) -> list[str]:
    if ctx.backend_mode == "exe":
        executable = ctx.backend_executable or (ctx.work_dir / APP_EXE_NAME)
        return [str(executable), str(ctx.port)]
    if ctx.backend_mode == "python":
        python_exec = ctx.python_executable or Path(sys.executable)
        backend_script = ctx.backend_script or (ctx.work_dir / "app.py")
        return [str(python_exec), str(backend_script), str(ctx.port)]

    fallback_exe = ctx.backend_executable or (ctx.work_dir / APP_EXE_NAME)
    if fallback_exe.exists():
        return [str(fallback_exe), str(ctx.port)]
    python_exec = ctx.python_executable or Path(sys.executable)
    backend_script = ctx.backend_script or (ctx.work_dir / "app.py")
    return [str(python_exec), str(backend_script), str(ctx.port)]


def verify_backend_restart(ctx: RuntimeContext, new_pid: int, restart_started_at: float, timeout_seconds: float = 12.0) -> tuple[bool, str, dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    runtime_seen = False
    while time.time() < deadline:
        if not is_pid_running(new_pid):
            return False, "backend process exited early", {"new_backend_pid": new_pid}
        runtime_file = ctx.work_dir / RUNTIME_FILE_NAME
        if runtime_file.exists():
            runtime_seen = True
            try:
                payload = json.loads(runtime_file.read_text(encoding="utf-8"))
                runtime_pid = int(payload.get("backend_pid") or 0)
                runtime_mtime = runtime_file.stat().st_mtime
            except Exception:
                runtime_pid = 0
                runtime_mtime = 0.0
            if runtime_pid == new_pid and runtime_mtime >= restart_started_at - 0.5:
                return True, "runtime file refreshed by new backend", {"new_backend_pid": new_pid, "runtime_pid": runtime_pid}
        if is_port_open(ctx.port):
            return True, "backend port is listening", {"new_backend_pid": new_pid, "port": ctx.port, "runtime_seen": runtime_seen}
        time.sleep(0.5)
    return False, "backend restart verification timed out", {"new_backend_pid": new_pid, "runtime_seen": runtime_seen, "port": ctx.port}


def prepare_update(ctx: RuntimeContext, repo: str, latest_tag: str, zip_url: str, sha_url: str, temp_root: Path, summary: dict[str, Any]) -> PreparedUpdate:
    zip_path = temp_root / RELEASE_ZIP_NAME
    sha_path = temp_root / RELEASE_SHA256_NAME
    extract_path = temp_root / "extract"

    trace(ctx.work_dir, "update:prepare", phase="downloading", zip_url=zip_url, sha_url=sha_url)
    write_phase_status(ctx.work_dir, "downloading", "downloading release assets", "downloading", {"repo": repo, "tag": latest_tag})
    for attempt in range(1, DOWNLOAD_RETRY_MAX_ATTEMPTS + 1):
        download_to(zip_url, zip_path, work_dir=ctx.work_dir, asset_name=RELEASE_ZIP_NAME)
        download_to(sha_url, sha_path, work_dir=ctx.work_dir, asset_name=RELEASE_SHA256_NAME)
        expected_sha = parse_sha256_file(sha_path)
        actual_sha = file_sha256(zip_path)
        if actual_sha == expected_sha:
            break
        zip_path.unlink(missing_ok=True)
        sha_path.unlink(missing_ok=True)
        retry = attempt < DOWNLOAD_RETRY_MAX_ATTEMPTS
        delay = retry_delay_seconds(attempt) if retry else 0
        trace(
            ctx.work_dir,
            "download:error",
            asset="sha256",
            attempt=attempt,
            max_attempts=DOWNLOAD_RETRY_MAX_ATTEMPTS,
            retry=retry,
            next_delay_seconds=delay,
            error="sha256 verification failed",
        )
        if not retry:
            raise RuntimeError("sha256 verification failed")
        time.sleep(delay)

    write_phase_status(ctx.work_dir, "extracting", "extracting update package", "extracting", {"repo": repo, "tag": latest_tag})
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_path)
    extracted_root = extract_release_root(extract_path)

    backup_dir = ctx.work_dir / BACKUP_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    write_phase_status(ctx.work_dir, "backup", "creating backup", "backing_up", {"repo": repo, "tag": latest_tag, "backup_dir": str(backup_dir)})
    backup_targets(ctx.work_dir, backup_dir)
    return PreparedUpdate(repo=repo, latest_tag=latest_tag, extract_path=extracted_root, backup_dir=backup_dir, summary=summary)


def apply_update(ctx: RuntimeContext, prepared: PreparedUpdate) -> dict[str, Any]:
    updated_targets: list[str] = []
    skipped_count = count_skipped_files(prepared.extract_path)
    with tempfile.TemporaryDirectory(prefix="account-inventory-stage-", dir=str(ctx.work_dir)) as stage_dir:
        write_phase_status(ctx.work_dir, "applying", "applying hot update files", "applying", {"repo": prepared.repo, "tag": prepared.latest_tag})
        updated_targets.extend(apply_hot_targets(prepared.extract_path, ctx.work_dir, Path(stage_dir)))

    locked_present = any((prepared.extract_path / rel).exists() for rel in LOCKED_SINGLE_FILES)
    if not locked_present:
        return {"updated_targets": updated_targets, "updated_count": len(updated_targets), "skipped_count": skipped_count, "restart_required": False}

    write_phase_status(ctx.work_dir, "stopping", "stopping current backend process", "stopping_backend", {"repo": prepared.repo, "tag": prepared.latest_tag, "backend_pid": ctx.backend_pid})
    stop_ok = stop_backend_process(ctx.backend_pid, work_dir=ctx.work_dir)
    if not stop_ok:
        raise RuntimeError("failed to stop backend process")
    if os.name == "nt":
        time.sleep(2.0)

    write_phase_status(ctx.work_dir, "applying", "applying executable update files", "applying", {"repo": prepared.repo, "tag": prepared.latest_tag})
    updated_targets.extend(apply_locked_targets(prepared.extract_path, ctx.work_dir))

    restart_command = resolve_restart_command(ctx)
    write_phase_status(ctx.work_dir, "restarting", "starting backend after applying update", "restarting", {"repo": prepared.repo, "tag": prepared.latest_tag, "restart_command": restart_command})
    restart_started_at = time.time()
    new_pid = start_backend_detached(restart_command, ctx.work_dir)
    verify_ok, verify_message, verify_extra = verify_backend_restart(ctx, new_pid, restart_started_at)
    if not verify_ok:
        raise UpdateApplyError(f"backend restart verification failed: {verify_message}", new_backend_pid=new_pid)
    ctx.backend_pid = new_pid

    return {
        "new_backend_pid": new_pid,
        "restart_command": restart_command,
        "restart_verify": verify_message,
        "updated_targets": updated_targets,
        "updated_count": len(updated_targets),
        "skipped_count": skipped_count,
        "restart_required": True,
        **verify_extra,
    }


def finalize_or_rollback(ctx: RuntimeContext, prepared: PreparedUpdate, apply_error: Optional[Exception], apply_extra: Optional[dict[str, Any]]) -> dict[str, Any]:
    if apply_error is None:
        extra = {"latest_tag": prepared.latest_tag, "repo": prepared.repo, **prepared.summary, **(apply_extra or {})}
        message = "update finished and backend restarted" if extra.get("restart_required") else "hot update finished"
        write_phase_status(ctx.work_dir, "updated", message, "completed", extra)
        return {"state": "updated", "message": message, "extra": extra}

    failed_new_pid = int(apply_error.new_backend_pid) if isinstance(apply_error, UpdateApplyError) else 0
    if failed_new_pid > 0:
        stop_ok = stop_backend_process(failed_new_pid, work_dir=ctx.work_dir)
        if not stop_ok:
            raise RuntimeError(f"rollback failed: unable to stop failed new backend pid={failed_new_pid}")
        if os.name == "nt":
            time.sleep(2.0)

    write_phase_status(ctx.work_dir, "rollback", f"update failed, rolling back: {apply_error}", "rollback", {"repo": prepared.repo, "tag": prepared.latest_tag})
    rollback_info = restore_from_backup(prepared.backup_dir, ctx.work_dir)

    if is_pid_running(ctx.backend_pid):
        old_pid = ctx.backend_pid
        verify_message = "existing backend process kept running"
        verify_extra: dict[str, Any] = {"backend_pid": old_pid}
    else:
        restart_command = resolve_restart_command(ctx)
        old_pid = start_backend_detached(restart_command, ctx.work_dir)
        verify_ok, verify_message, verify_extra = verify_backend_restart(ctx, old_pid, time.time())
        if not verify_ok:
            raise RuntimeError(f"update failed and rollback restart also failed: {apply_error}; rollback verify: {verify_message}")
        ctx.backend_pid = old_pid
    extra = {
        "repo": prepared.repo,
        "latest_tag": prepared.latest_tag,
        "rollback_reason": str(apply_error),
        "rollback_restart_verify": verify_message,
        "rolled_back_backend_pid": old_pid,
        **prepared.summary,
        **verify_extra,
        **rollback_info,
    }
    write_phase_status(ctx.work_dir, "rolled_back", "update failed and rollback recovered old version", "completed", extra)
    return {"state": "rolled_back", "message": "update failed and rollback recovered old version", "extra": extra}


def run_update_once(ctx: RuntimeContext, repo: str) -> dict[str, Any]:
    local_version = (ctx.app_version or "").strip() or read_app_version(ctx.work_dir)
    write_phase_status(ctx.work_dir, "checking", "checking latest release", "checking", {"repo": repo, "local_version": local_version})
    release = github_latest_release(repo)
    summary = release_summary(release)
    latest_tag = str(release.get("tag_name") or "")

    if not is_remote_newer(local_version, latest_tag):
        extra = {"repo": repo, "local_version": local_version, "update_available": False, "assets_ready": True, **summary}
        write_phase_status(ctx.work_dir, "idle", "already up-to-date", "completed", extra)
        return {"state": "idle", "message": "already up-to-date", "extra": extra}

    zip_url = find_asset_url(release, RELEASE_ZIP_NAME)
    sha_url = find_asset_url(release, RELEASE_SHA256_NAME)
    if not zip_url or not sha_url:
        raise RuntimeError("release assets are incomplete")
    summary_extra = {"repo": repo, "local_version": local_version, "update_available": True, "assets_ready": True, **summary}
    write_phase_status(ctx.work_dir, "checking", "new release found", "checking", summary_extra)

    with tempfile.TemporaryDirectory(prefix="account-inventory-update-") as temp_dir:
        prepared = prepare_update(ctx, repo, latest_tag, zip_url, sha_url, Path(temp_dir), summary_extra)
        apply_error: Optional[Exception] = None
        apply_extra: Optional[dict[str, Any]] = None
        try:
            apply_extra = apply_update(ctx, prepared)
        except Exception as exc:
            apply_error = exc
        return finalize_or_rollback(ctx, prepared, apply_error, apply_extra)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Account inventory updater sidecar")
    parser.add_argument("--watch", action="store_true", help="run forever and check updates every interval")
    parser.add_argument("--restore-watch", action="store_true", help="restart watcher after one-shot update")
    parser.add_argument("--interval-hours", type=float, default=24.0, help="watch mode check interval")
    parser.add_argument("--work-dir", default="", help="backend working directory")
    parser.add_argument("--backend-pid", type=int, default=0, help="current backend process pid")
    parser.add_argument("--port", type=int, default=8000, help="backend listen port")
    parser.add_argument("--backend-mode", choices=["auto", "exe", "python"], default="auto")
    parser.add_argument("--backend-executable", default="", help="path to backend executable")
    parser.add_argument("--backend-script", default="", help="path to app.py")
    parser.add_argument("--python-executable", default="", help="path to python executable")
    parser.add_argument("--repo", default=GITHUB_REPO, help="github repository in owner/repo format")
    return parser


def default_work_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_pyinstaller_temp_dir(path: Path) -> bool:
    return path.name.startswith("_MEI")


def validate_work_dir(work_dir: Path) -> None:
    if is_pyinstaller_temp_dir(work_dir):
        raise RuntimeError(f"refusing to update PyInstaller temp directory: {work_dir}")


def should_handoff_to_direct_sidecar(args: argparse.Namespace, work_dir: Path) -> bool:
    if args.work_dir:
        return False
    if not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    if executable.name.lower() != UPDATER_EXE_NAME:
        return False
    if executable.parent != work_dir:
        return False
    return executable.parent.name != SIDECAR_DIR_NAME


def build_direct_sidecar_command(args: argparse.Namespace, work_dir: Path, sidecar_exe: Path) -> list[str]:
    command = [str(sidecar_exe)]
    if args.watch:
        command.append("--watch")
    if args.restore_watch:
        command.append("--restore-watch")
    command.extend(
        [
            "--interval-hours",
            str(args.interval_hours),
            "--work-dir",
            str(work_dir),
            "--backend-pid",
            str(int(args.backend_pid)),
            "--port",
            str(int(args.port)),
            "--backend-mode",
            str(args.backend_mode),
            "--repo",
            str(args.repo),
        ]
    )
    if args.backend_executable:
        command.extend(["--backend-executable", str(args.backend_executable)])
    if args.backend_script:
        command.extend(["--backend-script", str(args.backend_script)])
    if args.python_executable:
        command.extend(["--python-executable", str(args.python_executable)])
    return command


def handoff_to_direct_sidecar(args: argparse.Namespace, work_dir: Path) -> int:
    sidecar_dir = work_dir / SIDECAR_DIR_NAME
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_exe = sidecar_dir / f"updater-direct-{int(time.time())}.exe"
    shutil.copy2(Path(sys.executable).resolve(), sidecar_exe)
    command = build_direct_sidecar_command(args, work_dir, sidecar_exe)
    trace(work_dir, "main:handoff", sidecar=str(sidecar_exe), work_dir=str(work_dir), command=command)
    completed = subprocess.run(command, cwd=str(work_dir))
    return int(completed.returncode)


def copy_updater_exe_for_sidecar(work_dir: Path) -> Optional[Path]:
    source = work_dir / UPDATER_EXE_NAME
    if not source.exists():
        return None
    sidecar_dir = work_dir / SIDECAR_DIR_NAME
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    target = sidecar_dir / f"updater-watch-{int(time.time())}.exe"
    shutil.copy2(source, target)
    return target


def resolve_watcher_command(ctx: RuntimeContext, repo: str, interval_hours: float) -> list[str]:
    updater_exe = copy_updater_exe_for_sidecar(ctx.work_dir)
    if updater_exe is not None:
        command = [str(updater_exe)]
    else:
        command = [str(ctx.python_executable or Path(sys.executable)), str(ctx.work_dir / "updater.py")]
    command.extend(
        [
            "--watch",
            "--interval-hours",
            str(interval_hours),
            "--work-dir",
            str(ctx.work_dir),
            "--backend-pid",
            str(ctx.backend_pid),
            "--port",
            str(ctx.port),
            "--backend-mode",
            ctx.backend_mode,
            "--repo",
            repo,
        ]
    )
    if ctx.backend_executable:
        command.extend(["--backend-executable", str(ctx.backend_executable)])
    if ctx.backend_script:
        command.extend(["--backend-script", str(ctx.backend_script)])
    if ctx.python_executable:
        command.extend(["--python-executable", str(ctx.python_executable)])
    return command


def maybe_restore_watch(ctx: RuntimeContext, repo: str, interval_hours: float) -> None:
    if not is_pid_running(ctx.backend_pid):
        return
    command = resolve_watcher_command(ctx, repo, interval_hours)
    try:
        start_backend_detached(command, ctx.work_dir)
    except Exception:
        pass


def main() -> int:
    args = build_parser().parse_args()
    work_dir = Path(args.work_dir).resolve() if args.work_dir else default_work_dir()
    validate_work_dir(work_dir)
    if should_handoff_to_direct_sidecar(args, work_dir):
        return handoff_to_direct_sidecar(args, work_dir)

    ctx = RuntimeContext(
        work_dir=work_dir,
        port=int(args.port),
        backend_pid=int(args.backend_pid),
        backend_mode=str(args.backend_mode),
        backend_executable=Path(args.backend_executable).resolve() if args.backend_executable else None,
        backend_script=Path(args.backend_script).resolve() if args.backend_script else None,
        python_executable=Path(args.python_executable).resolve() if args.python_executable else None,
        app_version=read_app_version(work_dir),
    )

    trace(work_dir, "main:start", pid=os.getpid(), watch=bool(args.watch), repo=str(args.repo))
    instance_lock = acquire_single_instance_lock(work_dir)
    if instance_lock is None:
        trace(work_dir, "lock:exists", pid=os.getpid())
        return 0

    interval_seconds = max(60, int(float(args.interval_hours) * 3600))
    try:
        while True:
            try:
                sync_runtime_context(ctx)
                result = run_update_once(ctx, str(args.repo))
                last_state = str(result.get("state") or "idle")
                last_message = str(result.get("message") or "")
                last_extra = dict(result.get("extra") or {})
            except Exception as exc:
                trace(work_dir, "error:exception", error=repr(exc))
                last_state = "error"
                last_message = f"update failed: {exc}"
                last_extra = {"repo": str(args.repo)}
                write_phase_status(work_dir, last_state, last_message, "failed", last_extra)

            if not args.watch:
                break
            sleep_seconds = interval_seconds
            write_phase_status(
                work_dir,
                last_state,
                last_message,
                "sleeping",
                {
                    **last_extra,
                    "repo": str(args.repo),
                    "loop_state": "sleeping",
                    "interval_seconds": interval_seconds,
                    "next_check_after_seconds": sleep_seconds,
                    "last_result_state": last_state,
                    "last_result_message": last_message,
                },
            )
            time.sleep(sleep_seconds)
    finally:
        release_single_instance_lock(instance_lock)

    if args.restore_watch and not args.watch:
        maybe_restore_watch(ctx, str(args.repo), float(args.interval_hours))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
