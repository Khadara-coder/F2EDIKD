"""AI provider configuration status for health badges and diagnostics."""

from __future__ import annotations

import os
from typing import Any


def get_ai_configuration_status(persisted_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return whether the selected AI provider has runtime credentials/config.

    Does not call the provider — only checks local env/settings presence.
    """
    persisted: dict[str, Any]
    if persisted_settings is not None:
        persisted = persisted_settings if isinstance(persisted_settings, dict) else {}
        provider = str(
            persisted.get("aiProvider")
            or os.environ.get("AI_PROVIDER")
            or "databricks"
        ).strip().lower() or "databricks"
    else:
        try:
            from src.file2edi.store import get_store

            persisted = get_store().load_app_settings() or {}
            provider = str(
                persisted.get("aiProvider")
                or os.environ.get("AI_PROVIDER")
                or "databricks"
            ).strip().lower() or "databricks"
        except Exception:
            persisted = {}
            provider = str(os.environ.get("AI_PROVIDER") or "databricks").strip().lower() or "databricks"

    detail = ""
    configured = False
    if provider == "openai":
        configured = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        detail = "OPENAI_API_KEY" if configured else "OPENAI_API_KEY manquant"
    elif provider == "ollama":
        cfg = persisted.get("ollamaConfig") if isinstance(persisted, dict) else {}
        if not isinstance(cfg, dict):
            cfg = {}
        base = str(
            cfg.get("baseUrl")
            or os.environ.get("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        ).strip()
        configured = bool(base)
        detail = base if configured else "URL Ollama manquante"
    elif provider == "custom":
        cfg = persisted.get("customAiConfig") if isinstance(persisted, dict) else {}
        if not isinstance(cfg, dict):
            cfg = {}
        base = str(
            cfg.get("baseUrl")
            or os.environ.get("CUSTOM_LLM_BASE_URL")
            or ""
        ).strip()
        token = str(
            os.environ.get("CUSTOM_LLM_API_KEY")
            or os.environ.get("CUSTOM_LLM_TOKEN")
            or os.environ.get("CUSTOM_LLM_AUTH_TOKEN")
            or ""
        ).strip()
        configured = bool(base and token)
        detail = "URL + token" if configured else "URL ou token custom manquant"
    else:
        provider = "databricks"
        configured = bool(os.environ.get("DATABRICKS_TOKEN", "").strip())
        detail = "DATABRICKS_TOKEN" if configured else "DATABRICKS_TOKEN manquant"

    return {
        "ok": configured,
        "configured": configured,
        "provider": provider,
        "detail": detail,
        "mockMode": os.environ.get("MOCK_MODE", "").strip().lower() in {"1", "true", "yes", "on"},
    }


def build_system_health_payload(proxy_health: dict[str, Any]) -> dict[str, Any]:
    """Normalize proxy health into the React Header badge contract."""
    from src.runtime_status import get_db_backend, is_postgres_strict

    ai = get_ai_configuration_status()
    return {
        "api": "connected" if proxy_health.get("api", {}).get("ok") else "disconnected",
        "database": "connected" if proxy_health.get("database", {}).get("ok") else "disconnected",
        "csv": "connected" if proxy_health.get("masterdata", {}).get("ok") else "disconnected",
        "sftp": "connected" if proxy_health.get("sftp_configured") else "disconnected",
        "ai": "connected" if ai.get("configured") else "disconnected",
        "aiProvider": ai.get("provider"),
        "aiDetail": ai.get("detail"),
        "databaseBackend": get_db_backend(),
        "postgresStrict": is_postgres_strict(),
    }
