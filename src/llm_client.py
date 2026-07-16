"""Shared LLM client for the EDIFACT Generator.

Uses ``mlflow.deployments.get_deploy_client("databricks")`` — the idiomatic
pattern inside Databricks Apps / notebooks.  This replaces the direct-HTTP
``requests.post`` approach that required explicit auth headers.

Handles the gpt-oss-120b *reasoning model* response format:
  content is a list of blocks;
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
from typing import Any, Optional

log = logging.getLogger("edifact.llm_client")

# ── Endpoint constants ────────────────────────────────────────────────────────
FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def _primary_endpoint() -> str:
    return os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")

# Lazy-init mlflow client (safe if not in Databricks context)
_client: Any = None

def _get_client() -> Any | None:
    global _client
    if _client is not None:
        return _client
    try:
        import mlflow.deployments
        _client = mlflow.deployments.get_deploy_client("databricks")
        return _client
    except Exception as exc:
        log.warning("mlflow.deployments client unavailable: %s", exc)
        return None


# ── Core helpers ──────────────────────────────────────────────────────────────

def _text_from_content(content: Any) -> str:
    """Extract answer text from a reasoning-model response content block.

    gpt-oss-120b returns a list:
      [{"type": "reasoning", ...}, {"type": "text", "text": "..."}]
    Standard models return a plain string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Prefer explicit text block
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        # Fall back: join reasoning summaries (debugging only)
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                for s in block.get("summary", []):
                    if s.get("type") == "summary_text":
                        parts.append(s.get("text", ""))
        return " ".join(parts)
    return str(content)


def _predict(endpoint: str, messages: list[dict], max_tokens: int) -> Optional[str]:
    """Single endpoint prediction, returns text or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.predict(
            endpoint=endpoint,
            inputs={
                "messages":   messages,
                "max_tokens": max_tokens,
                "temperature": 1,   # required for reasoning models (gpt-oss-120b)
            },
        )
        raw = resp["choices"][0]["message"]["content"]
        return _text_from_content(raw)
    except Exception as exc:
        log.warning("LLM predict failed (endpoint=%s): %s", endpoint, exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def llm_call(
    prompt:     str,
    system:     str = "",
    max_tokens: int = 1500,
    endpoint:   str | None = None,
) -> Optional[str]:
    """Call the LLM endpoint and return raw text.

    Tries ``endpoint`` (default current DATABRICKS_MODEL_ENDPOINT) first, then FALLBACK_ENDPOINT.
    Returns None if both fail or client unavailable.
    """
    primary = endpoint or _primary_endpoint()
    messages: list[dict] = []
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
    prompt:     str,
    system:     str = "",
    max_tokens: int = 1500,
    endpoint:   str | None = None,
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
        # Try to find embedded JSON object/array
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    log.debug("llm_extract_json: JSON parse failed; raw=%s", cleaned[:200])
    return None
