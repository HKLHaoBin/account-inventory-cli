"""Tests for the cloud-mode local client."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import httpx

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

            loaded = cloud_config.load_config()
            assert loaded.cloud_api_base_url == "https://example.com"
            assert cloud_config.is_configured() is True

            payload = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
            assert payload["cloudApiBaseUrl"] == "https://example.com"


def test_cloud_proxy_requires_configuration() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            from fastapi.testclient import TestClient

            client = TestClient(cloud_app.app)
            response = client.get("/api/dashboard")
            assert response.status_code == 428
            assert "请先配置数据库服务地址" in response.text


def test_cloud_proxy_forwards_request() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config("https://cloud.example")

            fake_response = httpx.Response(
                200,
                json={"inventoryCount": 3},
                headers={"content-type": "application/json"},
            )
            fake_client = mock.AsyncMock()
            fake_client.request = mock.AsyncMock(return_value=fake_response)
            fake_client.__aenter__ = mock.AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = mock.AsyncMock(return_value=None)

            from fastapi.testclient import TestClient

            with mock.patch("cloud_app.httpx.AsyncClient", return_value=fake_client):
                client = TestClient(cloud_app.app)
                response = client.post(
                    "/api/inbound/preview?dry=1",
                    json={"text": "user----pass"},
                )

            assert response.status_code == 200
            assert response.json()["inventoryCount"] == 3
            fake_client.request.assert_awaited_once()
            call = fake_client.request.await_args
            assert call.args[0] == "POST"
            assert call.args[1] == "https://cloud.example/api/inbound/preview?dry=1"
            assert b"user----pass" in call.kwargs["content"]


def test_cloud_clipboard_ignore_is_local() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with _patch_config_dir(Path(tmp)):
            from fastapi.testclient import TestClient

            fake_client = mock.AsyncMock()
            fake_client.request = mock.AsyncMock()
            fake_client.__aenter__ = mock.AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = mock.AsyncMock(return_value=None)

            with mock.patch("cloud_app.httpx.AsyncClient", return_value=fake_client):
                client = TestClient(cloud_app.app)
                response = client.post(
                    "/api/clipboard/ignore",
                    json={"text": "skip----pw"},
                )

            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert cloud_app._ignored_clipboard_text == "skip----pw"
            fake_client.request.assert_not_awaited()


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
            }

            response = client.put(
                "/local/config",
                json={"cloudApiBaseUrl": "https://remote.test/"},
            )
            assert response.status_code == 200
            assert response.json() == {
                "cloudApiBaseUrl": "https://remote.test",
                "configured": True,
            }


def test_cloud_local_config_test_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config("https://remote.test")
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
            }


def test_cloud_proxy_strips_encoding_headers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        with _patch_config_dir(config_dir):
            cloud_config.save_config("https://cloud.example")

            fake_response = mock.Mock()
            fake_response.status_code = 200
            fake_response.content = b'{"ok": true}'
            fake_response.headers = httpx.Headers(
                {
                    "content-type": "application/json",
                    "content-encoding": "gzip",
                }
            )
            fake_client = mock.AsyncMock()
            fake_client.request = mock.AsyncMock(return_value=fake_response)
            fake_client.__aenter__ = mock.AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = mock.AsyncMock(return_value=None)

            from fastapi.testclient import TestClient

            with mock.patch("cloud_app.httpx.AsyncClient", return_value=fake_client):
                client = TestClient(
                    cloud_app.app,
                    headers={"Accept-Encoding": "gzip, deflate, br"},
                )
                response = client.get("/api/dashboard")

            assert response.status_code == 200
            assert response.json() == {"ok": True}
            assert "content-encoding" not in {
                key.lower() for key in response.headers.keys()
            }

            call = fake_client.request.await_args
            forwarded_headers = {
                key.lower(): value for key, value in call.kwargs["headers"].items()
            }
            assert "accept-encoding" not in forwarded_headers


def test_cloud_packaged_frontend_static_path() -> None:
    import frontend_static

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "web" / "out"
        out_dir.mkdir(parents=True)
        index = out_dir / "index.html"
        index.write_text("home", encoding="utf-8")

        resolved = frontend_static.frontend_file_for_path(out_dir, "")
        assert resolved == index.resolve()
