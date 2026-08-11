"""Trigger an external n8n workflow to refresh masterdata from GitHub."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

log = logging.getLogger("edifact.masterdata_n8n")

# Configure the same style of URL locally and in prod (hostname swap only).
# Local Docker: http://localhost:5678/... works via n8n_localhost_relay (no URL rewrite).
# Prod: https://i1-d.n8n.bosch.com/webhook/masterdata-sync-prod
DEFAULT_WEBHOOK_URL = "http://localhost:5678/webhook/masterdata-sync"
PROD_WEBHOOK_PATH = "/webhook/masterdata-sync-prod"
LEGACY_WEBHOOK_PATH = "/webhook/masterdata-sync"


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "webhookUrl": DEFAULT_WEBHOOK_URL,
        "authHeader": "x-api-key",
        "timeoutSeconds": 120,
    }


def normalize_webhook_url(url: str) -> str:
    """Normalize for storage/UI: env override + Bosch prod path fix. No host rewrite."""
    env_url = (os.environ.get("MASTERDATA_N8N_WEBHOOK_URL") or "").strip()
    raw = env_url or (url or "").strip()
    if not raw:
        return raw

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    path_norm = path.rstrip("/") or ""
    last = path_norm.rsplit("/", 1)[-1] if path_norm else ""
    if last == "masterdata-sync" and ("n8n.bosch.com" in host or host.endswith(".n8n.bosch.com")):
        parsed = parsed._replace(path=PROD_WEBHOOK_PATH)

    return urlunparse(parsed)


def resolve_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = default_config()
    if isinstance(raw, dict):
        for key in cfg:
            if key in raw and raw.get(key) is not None:
                cfg[key] = raw.get(key)
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["webhookUrl"] = normalize_webhook_url(str(cfg.get("webhookUrl") or "").strip())
    cfg["authHeader"] = str(cfg.get("authHeader") or "x-api-key").strip() or "x-api-key"
    try:
        cfg["timeoutSeconds"] = max(5, min(600, int(cfg.get("timeoutSeconds") or 120)))
    except (TypeError, ValueError):
        cfg["timeoutSeconds"] = 120
    return cfg


def format_webhook_error(exc: BaseException, webhook_url: str = "") -> str:
    """User-facing error for n8n connectivity tests / sync."""
    text = str(exc)
    url = (webhook_url or "").strip()
    if re.search(r"NameResolutionError|Failed to resolve|Name or service not known", text, re.I):
        hint = (
            "DNS/réseau: l'API n'atteint pas n8n. "
            "Local: http://localhost:5678/... (relay Docker si besoin). "
            "Prod: https://…n8n.bosch.com/webhook/masterdata-sync-prod."
        )
        return f"Webhook n8n injoignable (DNS): {url or 'URL manquante'}. {hint}"
    if re.search(r"timed out|Read timed out|ConnectTimeout", text, re.I):
        hint = (
            "Timeout app → n8n. Vérifiez n8n sur :5678 et webhook actif. "
            "En Docker, le relay localhost (N8N_LOCALHOST_RELAY) doit être actif."
        )
        return f"Webhook n8n timeout: {url or 'URL manquante'}. {hint}"
    return f"Webhook n8n injoignable: {text}"


def _auth_token() -> str:
    return (
        os.environ.get("MASTERDATA_N8N_WEBHOOK_KEY")
        or os.environ.get("N8N_WEBHOOK_KEY")
        or os.environ.get("APP_API_KEYS", "").split(",")[0].strip()
        or ""
    ).strip()


def trigger_masterdata_sync_workflow(
    config: dict[str, Any] | None = None,
    *,
    actor: str = "operator",
    reason: str = "manual",
) -> dict[str, Any]:
    """POST the configured n8n webhook and return its JSON/text payload."""
    import requests

    cfg = resolve_config(config)
    if not cfg["enabled"]:
        raise RuntimeError("Sync n8n masterdata désactivée dans les paramètres admin")
    if not cfg["webhookUrl"]:
        raise RuntimeError("URL webhook n8n masterdata non configurée")

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = _auth_token()
    if token:
        headers[cfg["authHeader"]] = token

    body = {
        "action": "masterdata_sync",
        "reason": reason,
        "actor": actor,
        "source": "file2edi",
        "repo_url": os.environ.get(
            "MASTERDATA_REPO_URL",
            "https://github.boschdevcloud.com/RSR1DY/masterdata.git",
        ),
        "branch": os.environ.get("MASTERDATA_REPO_BRANCH", "main"),
    }
    log.info("Triggering n8n masterdata sync webhook: %s", cfg["webhookUrl"])
    resp = requests.post(
        cfg["webhookUrl"],
        headers=headers,
        json=body,
        timeout=cfg["timeoutSeconds"],
    )
    text = (resp.text or "").strip()
    payload: Any
    try:
        payload = resp.json() if text else {}
    except Exception:
        payload = {"raw": text[:500]}

    if resp.status_code >= 400:
        detail = payload if isinstance(payload, dict) else {"raw": text[:300]}
        raise RuntimeError(f"Webhook n8n HTTP {resp.status_code}: {detail}")

    if isinstance(payload, dict):
        return {
            "ok": True,
            "status_code": resp.status_code,
            "webhookUrl": cfg["webhookUrl"],
            **payload,
        }
    return {
        "ok": True,
        "status_code": resp.status_code,
        "webhookUrl": cfg["webhookUrl"],
        "message": str(payload),
    }
