"""API keys must survive settings sanitize/load/save."""

from __future__ import annotations

from src.file2edi.store import _sanitize_settings_payload


def test_sanitize_preserves_api_keys():
    payload = {
        "currency": "EUR - Euro",
        "api_keys": [
            {
                "id": "key_abc",
                "name": "n8n",
                "key_hash": "deadbeef" * 8,
                "created_by": "admin",
                "created_at": "2026-01-01T00:00:00",
                "last_used_at": None,
            }
        ],
        "rbac_role_overrides": {"alice": "admin", "bob": "adv", "bad": "root"},
    }
    out = _sanitize_settings_payload(payload)
    assert out["api_keys"] == payload["api_keys"]
    assert out["rbac_role_overrides"] == {"alice": "admin", "bob": "adv"}


def test_sanitize_allows_empty_api_keys_list():
    out = _sanitize_settings_payload({"api_keys": []})
    assert out["api_keys"] == []
