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
    if re.search(r"RemoteDisconnected|Connection aborted|ConnectionReset", text, re.I):
        hint = (
            "n8n a fermé la connexion HTTP pendant le sync. "
            "Le webhook doit répondre immédiatement (responseMode=onReceived) - "
            "réimportez n8n_masterdata_github_sync_raw.json puis activez le workflow. "
            "Un run manuel dans n8n ne teste pas ce lien webhook."
        )
        return f"Webhook n8n connexion coupée: {url or 'URL manquante'}. {hint}"
    if re.search(r"timed out|Read timed out|ConnectTimeout", text, re.I):
        hint = (
            "Timeout app → n8n. Vérifiez n8n sur :5678 et webhook actif. "
            "En Docker, le relay localhost (N8N_LOCALHOST_RELAY) doit être actif. "
            "Le webhook doit être en responseMode=onReceived (ACK rapide)."
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


def _origin_from_webhook_url(webhook_url: str) -> str:
    parsed = urlparse((webhook_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def probe_n8n_connectivity(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fast connectivity check (n8n health), not a full masterdata sync.

    The production webhook often keeps the HTTP request open until the workflow
    finishes. A short POST to that URL therefore times out even when n8n is up
    and Synchroniser (120s) succeeds. Probe ``/healthz`` on the same origin instead.
    """
    import requests

    cfg = resolve_config(config)
    url = str(cfg.get("webhookUrl") or "").strip()
    if not url:
        return {"status": "disconnected", "message": "URL webhook n8n manquante", "webhookUrl": ""}

    origin = _origin_from_webhook_url(url)
    if not origin:
        return {"status": "disconnected", "message": f"URL webhook n8n invalide: {url}", "webhookUrl": url}

    health_url = f"{origin}/healthz"
    try:
        health = requests.get(health_url, timeout=5)
    except Exception as exc:
        return {
            "status": "disconnected",
            "message": format_webhook_error(exc, url),
            "webhookUrl": url,
            "healthUrl": health_url,
        }

    if health.status_code >= 500:
        return {
            "status": "disconnected",
            "message": f"n8n healthz HTTP {health.status_code} - {health_url}",
            "webhookUrl": url,
            "healthUrl": health_url,
        }

    auth_note = "clé auth présente" if _auth_token() else "clé auth absente (MASTERDATA_N8N_WEBHOOK_KEY)"
    return {
        "status": "connected",
        "message": (
            f"n8n joignable (healthz HTTP {health.status_code}) - {url}. "
            f"Sync complète via Synchroniser (timeout {cfg.get('timeoutSeconds')}s). {auth_note}."
        ),
        "webhookUrl": url,
        "healthUrl": health_url,
    }


def _file2edi_public_base() -> str:
    return (
        os.environ.get("FILE2EDI_PUBLIC_URL")
        or os.environ.get("EDIFACT_API_BASE")
        or os.environ.get("APP_PUBLIC_URL")
        or "http://host.docker.internal:8000"
    ).strip().rstrip("/")


def _connection_dropped_early(exc: BaseException) -> bool:
    text = str(exc)
    return bool(
        re.search(r"RemoteDisconnected|Connection aborted|Connection reset|Remote end closed", text, re.I)
    )


def trigger_masterdata_sync_workflow(
    config: dict[str, Any] | None = None,
    *,
    actor: str = "operator",
    reason: str = "manual",
) -> dict[str, Any]:
    """POST the configured n8n webhook.

    Expected n8n setup: Webhook ``responseMode=onReceived`` so HTTP returns at once
    while the workflow continues (GitHub → File2EDI import → reload-cache).

    If n8n still uses ``lastNode``, it may close the HTTP connection mid-run
    (RemoteDisconnected) even though the workflow keeps going - treat that as
    ``async`` trigger started, not as hard failure.
    """
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
        "file2ediApiBase": _file2edi_public_base(),
    }
    # ACK should be fast with onReceived; keep a moderate read timeout for legacy lastNode.
    connect_timeout = 10
    read_timeout = min(90, int(cfg["timeoutSeconds"]))
    log.info(
        "Triggering n8n masterdata sync webhook: %s (timeout=%s/%ss)",
        cfg["webhookUrl"],
        connect_timeout,
        read_timeout,
    )
    try:
        resp = requests.post(
            cfg["webhookUrl"],
            headers=headers,
            json=body,
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout as exc:
        # Workflow likely still running under lastNode - n8n will call reload-cache.
        log.warning("n8n webhook read timeout (treating as async start): %s", exc)
        return {
            "ok": True,
            "async": True,
            "assumed_started": True,
            "webhookUrl": cfg["webhookUrl"],
            "message": (
                "Timeout en attendant la réponse n8n - le workflow a probablement démarré. "
                "Passez le webhook en responseMode=onReceived (réimport JSON). "
                "Les données seront mises à jour quand n8n appellera reload-cache."
            ),
        }
    except requests.ConnectionError as exc:
        if _connection_dropped_early(exc):
            log.warning(
                "n8n closed HTTP early after accept (treating as async start): %s",
                exc,
            )
            return {
                "ok": True,
                "async": True,
                "assumed_started": True,
                "webhookUrl": cfg["webhookUrl"],
                "message": (
                    "Connexion webhook fermée avant la réponse finale. "
                    "Le workflow n8n tourne souvent quand même - vérifiez l'exécution dans n8n. "
                    "Corrigez: Webhook → Respond Immediately (onReceived), réimportez "
                    "n8n_masterdata_github_sync_raw.json et activez le workflow."
                ),
            }
        raise RuntimeError(format_webhook_error(exc, cfg["webhookUrl"])) from exc
    except Exception as exc:
        raise RuntimeError(format_webhook_error(exc, cfg["webhookUrl"])) from exc

    text = (resp.text or "").strip()
    payload: Any
    try:
        payload = resp.json() if text else {}
    except Exception:
        payload = {"raw": text[:500]}

    if resp.status_code >= 400:
        detail = payload if isinstance(payload, dict) else {"raw": text[:300]}
        raise RuntimeError(f"Webhook n8n HTTP {resp.status_code}: {detail}")

    # onReceived often returns an empty/minimal body; work continues in n8n.
    base = {
        "ok": True,
        "async": True,
        "status_code": resp.status_code,
        "webhookUrl": cfg["webhookUrl"],
        "message": (
            "Workflow n8n déclenché. Import GitHub + reload-cache en cours "
            "(suivez l'exécution dans n8n, puis rafraîchissez Données maîtres)."
        ),
    }
    if isinstance(payload, dict) and payload:
        # Preserve aggregator message if n8n still uses lastNode and finished in time.
        merged = {**base, **payload}
        if payload.get("synced") or payload.get("files") or "cache_reloaded" in payload:
            merged["async"] = False
            if not merged.get("message"):
                merged["message"] = base["message"]
        return merged
    if payload and not isinstance(payload, dict):
        return {**base, "message": str(payload)}
    return base
