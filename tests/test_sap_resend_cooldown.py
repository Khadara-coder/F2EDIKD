"""Unit tests for SAP resend cooldown helpers."""
from datetime import datetime, timedelta, timezone

from src.file2edi.router import (
    _format_cooldown_mmss,
    _sap_resend_cooldown_info,
    _with_sap_resend_cooldown,
)


def test_format_cooldown_mmss():
    assert _format_cooldown_mmss(0) == "0:00"
    assert _format_cooldown_mmss(65) == "1:05"
    assert _format_cooldown_mmss(300) == "5:00"


def test_cooldown_active_when_recently_sent(monkeypatch):
    monkeypatch.setenv("SAP_RESEND_COOLDOWN_SECONDS", "300")
    sent_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    info = _sap_resend_cooldown_info({"sapSentAt": sent_at.isoformat()})
    assert info["active"] is True
    assert 230 <= info["remainingSeconds"] <= 240
    assert info["cooldownSeconds"] == 300
    assert info["resendAvailableAt"]


def test_cooldown_inactive_after_window(monkeypatch):
    monkeypatch.setenv("SAP_RESEND_COOLDOWN_SECONDS", "300")
    sent_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    info = _sap_resend_cooldown_info({"sapSentAt": sent_at.isoformat()})
    assert info["active"] is False
    assert info["remainingSeconds"] == 0


def test_cooldown_disabled_when_zero(monkeypatch):
    monkeypatch.setenv("SAP_RESEND_COOLDOWN_SECONDS", "0")
    sent_at = datetime.now(timezone.utc).isoformat()
    info = _sap_resend_cooldown_info({"sapSentAt": sent_at})
    assert info["active"] is False
    assert info["remainingSeconds"] == 0


def test_with_sap_resend_cooldown_attaches_payload(monkeypatch):
    monkeypatch.setenv("SAP_RESEND_COOLDOWN_SECONDS", "120")
    sent_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    review = _with_sap_resend_cooldown({"order": {"sapSentAt": sent_at.isoformat(), "status": "Envoyé SAP"}})
    assert "sapResendCooldown" in review["order"]
    assert review["order"]["sapResendCooldown"]["active"] is True
