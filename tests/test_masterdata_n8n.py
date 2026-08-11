"""Tests for n8n masterdata webhook trigger helper."""

from __future__ import annotations

from src.masterdata_n8n import resolve_config, trigger_masterdata_sync_workflow


def test_resolve_config_keeps_localhost(monkeypatch):
    monkeypatch.delenv("MASTERDATA_N8N_WEBHOOK_URL", raising=False)
    cfg = resolve_config({"webhookUrl": "http://localhost:5678/webhook/masterdata-sync"})
    assert cfg["webhookUrl"] == "http://localhost:5678/webhook/masterdata-sync"


def test_resolve_config_env_override(monkeypatch):
    monkeypatch.setenv(
        "MASTERDATA_N8N_WEBHOOK_URL",
        "https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod",
    )
    cfg = resolve_config({"webhookUrl": "http://localhost:5678/webhook/other"})
    assert cfg["webhookUrl"] == "https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod"


def test_resolve_config_clamps_timeout():
    cfg = resolve_config({"webhookUrl": " http://n8n/test ", "timeoutSeconds": 1})
    assert cfg["webhookUrl"] == "http://n8n/test"
    assert cfg["timeoutSeconds"] == 5


def test_resolve_config_rewrites_legacy_bosch_prod_path(monkeypatch):
    monkeypatch.delenv("MASTERDATA_N8N_WEBHOOK_URL", raising=False)
    cfg = resolve_config({
        "webhookUrl": "https://i1-d.n8n.bosch.com/webhook/masterdata-sync",
    })
    assert cfg["webhookUrl"] == "https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod"


def test_resolve_config_keeps_prod_path(monkeypatch):
    monkeypatch.delenv("MASTERDATA_N8N_WEBHOOK_URL", raising=False)
    cfg = resolve_config({
        "webhookUrl": "https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod",
    })
    assert cfg["webhookUrl"] == "https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod"


def test_trigger_posts_configured_url(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = '{"ok": true, "synced": 4, "message": "done"}'

        def json(self):
            return {"ok": True, "synced": 4, "message": "done"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp()

    monkeypatch.setenv("MASTERDATA_N8N_WEBHOOK_KEY", "secret")
    monkeypatch.delenv("MASTERDATA_N8N_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("requests.post", fake_post)

    out = trigger_masterdata_sync_workflow(
        {"enabled": True, "webhookUrl": "http://localhost:5678/webhook/masterdata-sync"},
        actor="admin",
        reason="manual_ui",
    )
    assert out["ok"] is True
    assert captured["url"] == "http://localhost:5678/webhook/masterdata-sync"
    assert captured["headers"]["x-api-key"] == "secret"
