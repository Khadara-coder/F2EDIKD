"""Shared LLM client for the EDIFACT Generator.

Direct REST calls to a Databricks Model Serving endpoint.
Databricks is a remote LLM provider here, not the application runtime.

Auth: DATABRICKS_TOKEN env var -> Bearer token
      Optional local-dev fallback: databricks-sdk WorkspaceClient OAuth

Handles the gpt-oss-120b *reasoning model* response format:
  content is a list of blocks:
    {"type": "reasoning", "summary": [...]}  ← internal thinking (skip)
    {"type": "text",      "text": "..."}     ← actual answer (extract this)

Public API:
    llm_call(prompt, system, max_tokens, endpoint) → Optional[str]
    llm_extract_json(prompt, system, max_tokens, endpoint) → Optional[dict]
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

log = logging.getLogger("edifact.llm_client")

FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def _primary_endpoint() -> str:
    return os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")


def _databricks_host() -> str:
    return os.environ.get("DATABRICKS_HOST", "").rstrip("/")


def _invocation_url(endpoint: str) -> str:
    host = _databricks_host()
    if not host:
        return ""
    return f"{host}/serving-endpoints/{endpoint}/invocations"


def _workspace_auth_headers() -> dict:
    """Return OAuth headers from databricks-sdk when no PAT token is configured.

    The SDK is intentionally optional: production VM deployments should prefer
    DATABRICKS_TOKEN, while developers may use a Databricks CLI profile.
    """
    try:
        from databricks.sdk import WorkspaceClient
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip()
        w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        return dict(w.config.authenticate())
    except Exception as exc:
        return {"_auth_error": str(exc)}


def _auth_headers() -> dict:
    token = os.environ.get("DATABRICKS_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers = _workspace_auth_headers()
    headers["Content-Type"] = "application/json"
    if "_auth_error" in headers:
        log.warning("LLM auth unavailable (set DATABRICKS_TOKEN): %s", headers["_auth_error"])
    return headers


# ── Core helpers ──────────────────────────────────────────────────────────────

def _text_from_content(content) -> str:
    """Extract answer text from a reasoning-model response content block."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                for s in block.get("summary", []):
                    if s.get("type") == "summary_text":
                        parts.append(s.get("text", ""))
        return " ".join(parts)
    return str(content)


def _predict(endpoint: str, messages: list, max_tokens: int) -> Optional[str]:
    """Single endpoint prediction via direct REST. Returns text or None."""
    url = _invocation_url(endpoint)
    if not url:
        log.warning("LLM: DATABRICKS_HOST not set - cannot call endpoint %s", endpoint)
        return None

    import requests

    headers = _auth_headers()
    if "_auth_error" in headers:
        log.warning("LLM auth error: %s", headers["_auth_error"])
        return None

    body = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 1,  # required for reasoning models (gpt-oss-120b)
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        return _text_from_content(raw)
    except Exception as exc:
        log.warning("LLM predict failed (endpoint=%s): %s", endpoint, exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def llm_call(
    prompt: str,
    system: str = "",
    max_tokens: int = 1500,
    endpoint: str | None = None,
) -> Optional[str]:
    """Call the LLM endpoint and return raw text.

    Tries ``endpoint`` (default DATABRICKS_MODEL_ENDPOINT) first, then FALLBACK_ENDPOINT.
    Returns None if both fail or DATABRICKS_HOST is not configured.
    """
    primary = endpoint or _primary_endpoint()
    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    result = _predict(primary, messages, max_tokens)
    if result is not None:
        return result

    if primary != FALLBACK_ENDPOINT:
        log.info("LLM primary failed, trying fallback %s", FALLBACK_ENDPOINT)
        result = _predict(FALLBACK_ENDPOINT, messages, max_tokens)

    return result


def llm_extract_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 1500,
    endpoint: str | None = None,
) -> Optional[dict | list]:
    """Call LLM and parse the response as JSON.

    Strips markdown fences if present.  Returns None on parse failure.
    """
    raw = llm_call(prompt, system=system, max_tokens=max_tokens, endpoint=endpoint)
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    log.debug("llm_extract_json: JSON parse failed; raw=%s", cleaned[:200])
    return None
