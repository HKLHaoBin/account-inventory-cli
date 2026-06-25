"""Tests for the cloud-mode local client."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import cloud_app
import cloud_config


def _patch_config_dir(tmp_path: Path):
    return mock.patch("cloud_config._config_dir", return_value=tmp_path)


def test_import_cloud_app_does_not_create_local_database() -> None:
    import database as db_module

    before = (
        set(db_module._DATA_DIR.glob("*"))
        if db_module._DATA_DIR.exists()
        else set()
    )
    assert cloud_app.app is not None
    after = (
        set(db_module._DATA_DIR.glob("*"))
        if db_module._DATA_DIR.exists()
        else set()
    )
    assert after == before


def test_cloud_config_save_and_load() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            saved = cloud_config.save_config("https://example.com/")
            assert saved.cloud_api_base_url == "https://example.com"
            assert saved.configured is True
            assert saved.remote_access_token is None

            saved_with_token = cloud_config.save_config(
                "https://example.com/",
                remote_access_token="remote-secret",
            )
            assert saved_with_token.remote_access_token == "remote-secret"

            loaded = cloud_config.load_config()
            assert loaded.cloud_api_base_url == "https://example.com"
            assert loaded.remote_access_token == "remote-secret"
            assert cloud_config.is_configured() is True

            payload = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
            assert payload["cloudApiBaseUrl"] == "https://example.com"
            assert payload["remoteAccessToken"] == "remote-secret"


def test_cloud_config_preserves_token_when_not_provided() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            cloud_config.save_config(
                "https://example.com/",
                remote_access_token="keep-me",
            )
            saved = cloud_config.save_config("https://remote.test/")
            assert saved.remote_access_token == "keep-me"


def test_cloud_config_clears_token() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config(
                "https://example.com/",
                remote_access_token="remote-secret",
            )
            saved = cloud_config.save_config(
                "https://example.com/",
                remote_access_token="",
            )
            assert saved.remote_access_token is None
            payload = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
            assert "remoteAccessToken" not in payload


def test_cloud_load_config_without_token_field() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"cloudApiBaseUrl": "https://legacy.example"}, ensure_ascii=False),
            encoding="utf-8",
        )
        with _patch_config_dir(config_dir):
            loaded = cloud_config.load_config()
            assert loaded.cloud_api_base_url == "https://legacy.example"
            assert loaded.remote_access_token is None


def test_cloud_api_dashboard_is_not_proxied() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config(
                "https://cloud.example",
                remote_access_token="remote-secret",
            )

            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.get("/api/dashboard")
            assert response.status_code == 404


def test_cloud_local_credentials_endpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config(
                "https://cloud.example",
                remote_access_token="remote-secret",
            )

            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.get("/local/credentials")
            assert response.status_code == 200
            assert response.json() == {
                "remoteAccessToken": "remote-secret",
                "cloudApiBaseUrl": "https://cloud.example",
                "configured": True,
            }

            config_response = client.get("/local/config")
            assert config_response.status_code == 200
            config_body = config_response.json()
            assert "remoteAccessToken" not in config_body
            assert "remote-secret" not in config_response.text


def test_cloud_runtime_update_status_is_local() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config("https://cloud.example")

            from fastapi.testclient import TestClient

            with mock.patch(
                "cloud_app.updater_runtime.read_update_status",
                return_value={"state": "idle", "phase": "idle"},
            ) as read_status:
                client = TestClient(cloud_app.app)
                response = client.get("/api/runtime/update-status")

            assert response.status_code == 200
            assert response.json() == {"state": "idle", "phase": "idle"}
            read_status.assert_called_once()


def test_cloud_clipboard_ignore_is_local() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.post(
                "/api/clipboard/ignore",
                json={"text": "skip----pw"},
            )

            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert cloud_app._ignored_clipboard_text == "skip----pw"


def test_cloud_local_config_endpoints() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.get("/local/config")
            assert response.status_code == 200
            assert response.json() == {
                "cloudApiBaseUrl": None,
                "configured": False,
                "remoteAccessTokenConfigured": False,
            }

            response = client.put(
                "/local/config",
                json={"cloudApiBaseUrl": "https://remote.test/"},
            )
            assert response.status_code == 200
            assert response.json() == {
                "cloudApiBaseUrl": "https://remote.test",
                "configured": True,
                "remoteAccessTokenConfigured": False,
            }

            response = client.put(
                "/local/config",
                json={
                    "cloudApiBaseUrl": "https://remote.test/",
                    "remoteAccessToken": "remote-secret",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["remoteAccessTokenConfigured"] is True
            assert "remoteAccessToken" not in body
            assert "remote-secret" not in response.text


def test_cloud_local_config_test_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config(
                "https://remote.test",
                remote_access_token="remote-secret",
            )
            fake_response = mock.Mock()
            fake_response.status_code = 200
            fake_response.text = '{"database":{"name":"main"}}'

            from fastapi.testclient import TestClient

            with mock.patch(
                "cloud_app.requests.get",
                return_value=fake_response,
            ) as get_mock:
                client = TestClient(cloud_app.app)
                response = client.post("/local/config/test")

            assert response.status_code == 200
            assert response.json()["ok"] is True
            get_mock.assert_called_once_with(
                "https://remote.test/api/dashboard",
                timeout=10,
                headers={"X-Remote-Access-Token": "remote-secret"},
            )


def test_cloud_local_config_test_requires_configuration() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.post("/local/config/test")
            assert response.status_code == 428


def test_cloud_config_rejects_non_http_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.put(
                "/local/config",
                json={"cloudApiBaseUrl": "example.com"},
            )
            assert response.status_code == 400
            assert "http://" in response.json()["detail"]

            cleared = client.put("/local/config", json={"cloudApiBaseUrl": "  "})
            assert cleared.status_code == 200
            assert cleared.json()["configured"] is False


def test_cloud_load_config_ignores_invalid_stored_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"cloudApiBaseUrl": "example.com"}, ensure_ascii=False),
            encoding="utf-8",
        )
        with _patch_config_dir(config_dir):
            loaded = cloud_config.load_config()
            assert loaded.cloud_api_base_url is None
            assert loaded.configured is False


def test_cloud_local_config_with_invalid_stored_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"cloudApiBaseUrl": "ftp://bad.example"}, ensure_ascii=False),
            encoding="utf-8",
        )
        with _patch_config_dir(config_dir):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.get("/local/config")
            assert response.status_code == 200
            assert response.json() == {
                "cloudApiBaseUrl": None,
                "configured": False,
                "remoteAccessTokenConfigured": False,
            }


def test_cloud_packaged_frontend_static_path() -> None:
    import frontend_static

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "web" / "out"
        out_dir.mkdir(parents=True)
        index = out_dir / "index.html"
        index.write_text("home", encoding="utf-8")

        resolved = frontend_static.frontend_file_for_path(out_dir, "")
        assert resolved == index.resolve()


def test_frontend_file_for_path_relative_web_out_dir() -> None:
    import os

    import frontend_static

    with tempfile.TemporaryDirectory() as tmp:
        original = os.getcwd()
        try:
            os.chdir(tmp)
            out_rel = Path("web/out")
            out_rel.mkdir(parents=True)
            index = out_rel / "index.html"
            index.write_text("home", encoding="utf-8")

            resolved = frontend_static.frontend_file_for_path(Path("web/out"), "")
            assert resolved == (Path("web/out") / "index.html").resolve()
            assert resolved.is_absolute()
        finally:
            os.chdir(original)
