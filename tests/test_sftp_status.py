"""Unit tests for SFTP env status helpers."""

from __future__ import annotations

from src.sftp_delivery import (
    is_configured_from_env,
    status_from_env,
    test_connection_from_env as probe_sftp_connection,
)


def test_is_configured_from_env(monkeypatch):
    monkeypatch.delenv("SFTP_HOST", raising=False)
    assert is_configured_from_env() is False
    monkeypatch.setenv("SFTP_HOST", "sftp.example.test")
    assert is_configured_from_env() is True


def test_status_from_env_masks_no_secrets(monkeypatch):
    monkeypatch.setenv("SFTP_HOST", "sftp.example.test")
    monkeypatch.setenv("SFTP_USERNAME", "sap")
    monkeypatch.setenv("SFTP_REMOTE_DIR", "/in")
    monkeypatch.setenv("SFTP_PASSWORD", "secret")
    status = status_from_env()
    assert status["configured"] is True
    assert status["host"] == "sftp.example.test"
    assert "secret" not in str(status.values())
    assert status["auth_mode"] == "password"


def test_probe_without_host(monkeypatch):
    monkeypatch.delenv("SFTP_HOST", raising=False)
    ok, msg = probe_sftp_connection()
    assert ok is False
    assert "SFTP_HOST" in msg
