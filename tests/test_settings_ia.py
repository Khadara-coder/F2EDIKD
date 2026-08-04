"""Tests for IA-related settings endpoints:
  POST /api/settings/ai-test
  PUT  /api/settings/databricks-token
  (both registered in src/file2edi/router.py)
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.file2edi.router as router_mod


class FakeSettingsStore:
    def __init__(self):
        self.settings: dict = {}

    def load_app_settings(self) -> dict:
        return dict(self.settings)

    def save_app_settings(self, payload: dict) -> dict:
        self.settings.update(payload or {})
        return dict(self.settings)


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp_path_factory.mktemp("settings")

    # Provide a minimal server stub so remaining router `import server as srv`
    # paths resolve without loading the real server.py.
    previous = sys.modules.get("server")
    stub = ModuleType("server")
    stub._ensure_admin = MagicMock(return_value=("test-admin@bosch.com", "admin"))
    stub._apply_runtime_databricks_config = MagicMock()
    stub._test_sftp = MagicMock(return_value=(True, "ok"))
    sys.modules["server"] = stub
    router_mod.get_store = lambda: FakeSettingsStore()

    application = FastAPI()
    application.include_router(router_mod.create_router(), prefix="/api")
    yield application
    if previous is not None:
        sys.modules["server"] = previous
    else:
        sys.modules.pop("server", None)


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


# ── POST /api/settings/ai-test ────────────────────────────────────────────────

class TestAiTest:
    def test_missing_host_returns_error(self, client):
        resp = client.post("/api/settings/ai-test", json={
            "host": "",
            "token": "dapi123",
            "modelEndpoint": "databricks-gpt-oss-120b",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "DATABRICKS_HOST" in body["message"]

    def test_connection_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.post", return_value=mock_resp):
            resp = client.post("/api/settings/ai-test", json={
                "host": "https://myworkspace.azuredatabricks.net",
                "token": "dapiABC",
                "modelEndpoint": "databricks-gpt-oss-120b",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "databricks-gpt-oss-120b" in body["message"]

    def test_connection_http_error(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("requests.post", return_value=mock_resp):
            resp = client.post("/api/settings/ai-test", json={
                "host": "https://myworkspace.azuredatabricks.net",
                "token": "wrong-token",
                "modelEndpoint": "databricks-gpt-oss-120b",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "401" in body["message"]

    def test_connection_timeout(self, client):
        import requests as _requests
        with patch("requests.post", side_effect=_requests.exceptions.Timeout("timed out")):
            resp = client.post("/api/settings/ai-test", json={
                "host": "https://myworkspace.azuredatabricks.net",
                "token": "dapi123",
                "modelEndpoint": "ep",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "15s" in body["message"]

    def test_connection_error(self, client):
        import requests as _requests
        with patch("requests.post", side_effect=_requests.exceptions.ConnectionError("unreachable")):
            resp = client.post("/api/settings/ai-test", json={
                "host": "https://unreachable.example.com",
                "token": "dapi123",
                "modelEndpoint": "ep",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "unreachable.example.com" in body["message"]

    def test_uses_env_token_if_payload_empty(self, client, monkeypatch):
        monkeypatch.setenv("DATABRICKS_TOKEN", "env-token")
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.post("/api/settings/ai-test", json={
                "host": "https://myworkspace.azuredatabricks.net",
                "token": "",
                "modelEndpoint": "ep",
            })

        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers.get("Authorization") == "Bearer env-token"

    def test_bearer_token_sent_in_header(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.post("/api/settings/ai-test", json={
                "host": "https://myworkspace.azuredatabricks.net",
                "token": "dapiXYZ",
                "modelEndpoint": "ep",
            })

        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers.get("Authorization") == "Bearer dapiXYZ"
        call_url = mock_post.call_args[0][0]
        assert "serving-endpoints/ep/invocations" in call_url


# ── PUT /api/settings/databricks-token ───────────────────────────────────────

class TestDatabricksToken:
    def test_sets_env_var(self, client, monkeypatch):
        import os
        resp = client.put("/api/settings/databricks-token", json={"token": "dapi-new-token"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert os.environ.get("DATABRICKS_TOKEN") == "dapi-new-token"

    def test_empty_token_rejected(self, client):
        resp = client.put("/api/settings/databricks-token", json={"token": ""})
        assert resp.status_code == 400

    def test_missing_token_key_rejected(self, client):
        resp = client.put("/api/settings/databricks-token", json={})
        assert resp.status_code == 400

    def test_whitespace_only_rejected(self, client):
        resp = client.put("/api/settings/databricks-token", json={"token": "   "})
        assert resp.status_code == 400


class TestSftpSettings:
    def test_put_settings_applies_sftp_runtime_env(self, client, monkeypatch):
        import os

        for key in ("SFTP_HOST", "SFTP_USERNAME", "SFTP_REMOTE_DIR", "SFTP_PORT"):
            monkeypatch.delenv(key, raising=False)

        resp = client.put("/api/settings", json={
            "sftpConfig": {
                "host": "sftp.example.test",
                "port": 2222,
                "username": "sap-user",
                "remotePath": "/inbox/edi",
            }
        })

        assert resp.status_code == 200
        assert os.environ.get("SFTP_HOST") == "sftp.example.test"
        assert os.environ.get("SFTP_USERNAME") == "sap-user"
        assert os.environ.get("SFTP_REMOTE_DIR") == "/inbox/edi"
        assert os.environ.get("SFTP_PORT") == "2222"

    def test_sftp_connector_test_applies_incoming_config_before_test(self, client, monkeypatch):
        import os

        captured = {}

        def fake_test_sftp():
            captured.update({
                "host": os.environ.get("SFTP_HOST"),
                "username": os.environ.get("SFTP_USERNAME"),
                "remote": os.environ.get("SFTP_REMOTE_DIR"),
                "port": os.environ.get("SFTP_PORT"),
            })
            return True, "ok"

        monkeypatch.setattr(router_mod, "test_connection_from_env", fake_test_sftp)
        for key in ("SFTP_HOST", "SFTP_USERNAME", "SFTP_REMOTE_DIR", "SFTP_PORT"):
            monkeypatch.delenv(key, raising=False)

        resp = client.post("/api/settings/test-connector/sftp", json={
            "sftpConfig": {
                "host": "sftp.preview.test",
                "port": "2201",
                "username": "preview-user",
                "remotePath": "/preview",
            }
        })

        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"
        assert captured == {
            "host": "sftp.preview.test",
            "username": "preview-user",
            "remote": "/preview",
            "port": "2201",
        }


def test_postgres_url_normalization_accepts_sqlalchemy_driver():
    from src.file2edi.store import _normalize_postgres_url

    assert (
        _normalize_postgres_url("postgresql+psycopg://edifact:secret@postgres:5432/edifact")
        == "postgresql://edifact:secret@postgres:5432/edifact"
    )
    assert (
        _normalize_postgres_url("postgres://edifact:secret@postgres:5432/edifact")
        == "postgresql://edifact:secret@postgres:5432/edifact"
    )
