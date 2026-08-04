"""Tests for n8n masterdata webhook trigger helper."""

from __future__ import annotations

from src.masterdata_n8n import resolve_config, trigger_masterdata_sync_workflow


def test_resolve_config_clamps_timeout():
    cfg = resolve_config({"webhookUrl": " http://n8n/test ", "timeoutSeconds": 1})
    assert cfg["webhookUrl"] == "http://n8n/test"
    assert cfg["timeoutSeconds"] == 5


def test_trigger_posts_webhook(monkeypatch):
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
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setenv("MASTERDATA_N8N_WEBHOOK_KEY", "secret")
    monkeypatch.setattr("requests.post", fake_post)

    out = trigger_masterdata_sync_workflow(
        {"enabled": True, "webhookUrl": "http://localhost:5678/webhook/masterdata-sync"},
        actor="admin",
        reason="manual_ui",
    )
    assert out["ok"] is True
    assert out["synced"] == 4
    assert captured["url"].endswith("/webhook/masterdata-sync")
    assert captured["headers"]["x-api-key"] == "secret"
    assert captured["json"]["actor"] == "admin"
