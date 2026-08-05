"""Trigger an external n8n workflow to refresh masterdata from GitHub."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

log = logging.getLogger("edifact.masterdata_n8n")

# From inside the API container, localhost:5678 is the container itself — not host n8n.
# Prefer host.docker.internal (published host port). Stacks stay separate; HTTP only.
DEFAULT_WEBHOOK_URL = "http://host.docker.internal:5678/webhook/masterdata-sync"


def default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "webhookUrl": DEFAULT_WEBHOOK_URL,
        "authHeader": "x-api-key",
        "timeoutSeconds": 120,
    }


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("IN_DOCKER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _docker_safe_webhook_url(url: str) -> str:
    """Rewrite localhost/127.0.0.1 webhook targets when the API runs in Docker."""
    raw = (url or "").strip()
    if not raw:
        return raw
    env_url = (os.environ.get("MASTERDATA_N8N_WEBHOOK_URL") or "").strip()
    if env_url:
        return env_url
    if not _running_in_docker():
        return raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1"}:
        return raw
    # Keep path/query; swap host so the published n8n port on the Docker host is reachable.
    netloc = "host.docker.internal"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    elif parsed.scheme == "https":
        netloc = f"{netloc}:443"
    else:
        netloc = f"{netloc}:80"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def resolve_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = default_config()
    if isinstance(raw, dict):
        for key in cfg:
            if key in raw and raw.get(key) is not None:
                cfg[key] = raw.get(key)
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["webhookUrl"] = _docker_safe_webhook_url(str(cfg.get("webhookUrl") or "").strip())
    cfg["authHeader"] = str(cfg.get("authHeader") or "x-api-key").strip() or "x-api-key"
    try:
        cfg["timeoutSeconds"] = max(5, min(600, int(cfg.get("timeoutSeconds") or 120)))
    except (TypeError, ValueError):
        cfg["timeoutSeconds"] = 120
    return cfg


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
