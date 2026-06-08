"""Persistent configuration for the cloud-mode local client."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloudConfig:
    cloud_api_base_url: str | None

    @property
    def configured(self) -> bool:
        return bool(self.cloud_api_base_url)


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "AccountInventoryCloud"
    return Path(__file__).resolve().parent / ".cloud-config"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def normalize_cloud_api_base_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return ""
    normalized = normalized.rstrip("/")
    lowered = normalized.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise ValueError("服务地址必须以 http:// 或 https:// 开头")
    return normalized


def load_config() -> CloudConfig:
    path = _config_path()
    if not path.is_file():
        return CloudConfig(cloud_api_base_url=None)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CloudConfig(cloud_api_base_url=None)

    raw_url = payload.get("cloudApiBaseUrl")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return CloudConfig(cloud_api_base_url=None)

    try:
        normalized = normalize_cloud_api_base_url(raw_url)
    except ValueError:
        return CloudConfig(cloud_api_base_url=None)

    return CloudConfig(cloud_api_base_url=normalized or None)


def save_config(url: str) -> CloudConfig:
    normalized = normalize_cloud_api_base_url(url)
    config = CloudConfig(cloud_api_base_url=normalized or None)
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {"cloudApiBaseUrl": config.cloud_api_base_url}
    _config_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config


def is_configured() -> bool:
    return load_config().configured
