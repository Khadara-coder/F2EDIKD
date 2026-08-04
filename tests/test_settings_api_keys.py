"""API keys must survive settings sanitize/load/save."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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


def test_authenticated_repo_url_embeds_token(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "sync_masterdata_repo.py"
    spec = importlib.util.spec_from_file_location("sync_masterdata_repo", script)
    assert spec and spec.loader
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)

    monkeypatch.setenv("MASTERDATA_GIT_TOKEN", "secret-token")
    url = sync._authenticated_repo_url(
        "https://github.boschdevcloud.com/RSR1DY/masterdata.git"
    )
    assert url.startswith("https://x-access-token:secret-token@github.boschdevcloud.com/")
