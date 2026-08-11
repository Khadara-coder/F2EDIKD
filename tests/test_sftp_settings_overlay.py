"""SFTP settings: env (.env.local) must surface in GET /api/settings UI."""

from __future__ import annotations

from src.file2edi.router import overlay_sftp_config_from_env


def test_overlay_replaces_legacy_inbox_even_if_env_polluted(monkeypatch):
    """A prior UI test may have set SFTP_REMOTE_DIR=/inbox — still normalize to /."""
    monkeypatch.setenv("SFTP_REMOTE_DIR", "/inbox")
    monkeypatch.setenv("SFTP_HOST", "sftp.intranet.bosch.com")
    out = overlay_sftp_config_from_env({"remotePath": "/inbox"})
    assert out["remotePath"] == "/"


def test_overlay_fills_empty_ui_from_env(monkeypatch):
    monkeypatch.setenv("SFTP_ENABLED", "true")
    monkeypatch.setenv("SFTP_HOST", "sftp.intranet.bosch.com")
    monkeypatch.setenv("SFTP_USERNAME", "sftp_vtb_edipushbot")
    monkeypatch.setenv("SFTP_REMOTE_DIR", "/")
    monkeypatch.setenv("SFTP_PORT", "22")
    monkeypatch.setenv("SFTP_PASSWORD", "secret")

    out = overlay_sftp_config_from_env({
        "enabled": False,
        "host": "",
        "port": 22,
        "username": "",
        "remotePath": "/inbox",
        "fileNamePattern": "ORDERS_{orderId}.edi",
    })
    assert out["enabled"] is True
    assert out["host"] == "sftp.intranet.bosch.com"
    assert out["username"] == "sftp_vtb_edipushbot"
    assert out["remotePath"] == "/"
    assert out["hasPassword"] is True


def test_overlay_keeps_explicit_ui_host(monkeypatch):
    monkeypatch.setenv("SFTP_HOST", "from-env.example")
    monkeypatch.setenv("SFTP_USERNAME", "env-user")
    monkeypatch.delenv("SFTP_PASSWORD", raising=False)

    out = overlay_sftp_config_from_env({
        "enabled": True,
        "host": "ui.example",
        "port": 2222,
        "username": "ui-user",
        "remotePath": "/custom",
    })
    assert out["host"] == "ui.example"
    assert out["username"] == "ui-user"
    assert out["remotePath"] == "/custom"
    assert out["port"] == 2222
    assert out["hasPassword"] is False


def test_api_settings_app_settings_includes_env_sftp(monkeypatch):
    import server

    monkeypatch.setenv("SFTP_ENABLED", "true")
    monkeypatch.setenv("SFTP_HOST", "sftp.intranet.bosch.com")
    monkeypatch.setenv("SFTP_USERNAME", "sftp_vtb_edipushbot")
    monkeypatch.setenv("SFTP_REMOTE_DIR", "/")
    monkeypatch.setenv("SFTP_PASSWORD", "x")

    class _Store:
        def load_app_settings(self):
            return {}

    monkeypatch.setattr(
        "src.file2edi.store.get_store",
        lambda: _Store(),
        raising=False,
    )
    # api_settings imports get_store inside the function
    monkeypatch.setattr(
        server,
        "_masterdata_stats",
        lambda: {},
        raising=False,
    )
    monkeypatch.setattr(
        server,
        "_runtime_databricks_config",
        lambda: {
            "api_base_url": "",
            "model_endpoint": "",
            "catalog": "",
            "schema": "",
        },
        raising=False,
    )
    monkeypatch.setattr(server, "get_storage_mode", lambda: {"persistent": True}, raising=False)

    body = server.api_settings()
    sftp = (body.get("app_settings") or {}).get("sftpConfig") or {}
    assert sftp.get("host") == "sftp.intranet.bosch.com"
    assert sftp.get("username") == "sftp_vtb_edipushbot"
    assert sftp.get("remotePath") == "/"
    assert sftp.get("enabled") is True
    assert sftp.get("hasPassword") is True
    assert body.get("sftp", {}).get("configured") is True
