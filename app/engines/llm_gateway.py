from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

from app.runtime import llm_enabled

logger = logging.getLogger(__name__)


def _parse_custom_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in re.split(r"[\n,]", raw or ""):
        chunk = part.strip()
        if not chunk or ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            headers[key] = value
    return headers


def _provider() -> str:
    p = (os.getenv("F2EDI_LLM_PROVIDER") or "databricks").strip().lower()
    if p in {"databricks", "openai", "ollama", "custom"}:
        return p
    return "databricks"


def _text_from_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text") or "")
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                for summary in block.get("summary", []):
                    if isinstance(summary, dict) and summary.get("type") == "summary_text":
                        parts.append(str(summary.get("text") or ""))
        return " ".join(parts)
    return str(content)


def _databricks_auth_headers(token: str) -> Optional[dict[str, str]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        return headers

    try:
        from databricks.sdk import WorkspaceClient

        profile = os.getenv("DATABRICKS_CONFIG_PROFILE", "").strip()
        w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        headers.update(w.config.authenticate())
        return headers
    except Exception as exc:
        logger.debug("Databricks SDK auth unavailable: %s", exc)
        return None


def _chat_databricks_http(prompt: str, max_tokens: int, endpoint: str) -> Optional[str]:
    """Call a Databricks Model Serving endpoint over HTTP.

    Databricks is treated as a remote LLM provider. The app itself runs on the
    VM/Docker stack, so no mlflow or Databricks runtime is required here.
    """
    host = os.getenv("DATABRICKS_HOST", "").strip().rstrip("/")
    if not host:
        return None

    headers = _databricks_auth_headers(os.getenv("DATABRICKS_TOKEN", "").strip())
    if headers is None:
        return None

    try:
        resp = requests.post(
            f"{host}/serving-endpoints/{endpoint}/invocations",
            headers=headers,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("Databricks HTTP LLM call failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _text_from_content(content).strip() or None
    except Exception as exc:
        logger.warning("Databricks HTTP LLM call error: %s", exc)
        return None


def _chat_databricks(prompt: str, max_tokens: int, endpoint: str, fallback_endpoint: str | None = None) -> Optional[str]:
    result = _chat_databricks_http(prompt, max_tokens, endpoint)
    if result is None and fallback_endpoint and fallback_endpoint != endpoint:
        return _chat_databricks_http(prompt, max_tokens, fallback_endpoint)
    return result


def _chat_openai_compatible(prompt: str, max_tokens: int) -> Optional[str]:
    base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/")
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not configured")
        return None
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning("OpenAI-compatible call failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        return str(body.get("choices", [{}])[0].get("message", {}).get("content", "")).strip() or None
    except Exception as exc:
        logger.warning("OpenAI-compatible provider unavailable: %s", exc)
        return None


def _chat_ollama(prompt: str) -> Optional[str]:
    base_url = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip().rstrip("/")
    model = (os.getenv("OLLAMA_MODEL") or "llama3.1").strip()
    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=60,
        )
        if resp.status_code >= 400:
            logger.warning("Ollama call failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        message = body.get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "").strip() or None
        return None
    except Exception as exc:
        logger.warning("Ollama provider unavailable: %s", exc)
        return None


def _chat_custom(prompt: str, max_tokens: int) -> Optional[str]:
    base_url = (os.getenv("CUSTOM_LLM_BASE_URL") or "").strip().rstrip("/")
    chat_path = (os.getenv("CUSTOM_LLM_CHAT_PATH") or "/v1/chat/completions").strip()
    model = (os.getenv("CUSTOM_LLM_MODEL") or "").strip()
    auth_header = (os.getenv("CUSTOM_LLM_AUTH_HEADER") or "Authorization").strip() or "Authorization"
    auth_scheme = (os.getenv("CUSTOM_LLM_AUTH_SCHEME") or "Bearer").strip()
    custom_headers_raw = (os.getenv("CUSTOM_LLM_EXTRA_HEADERS") or "").strip()
    token = (os.getenv("CUSTOM_LLM_API_KEY") or "").strip()

    if not base_url:
        logger.warning("CUSTOM_LLM_BASE_URL not configured")
        return None

    headers = {"Content-Type": "application/json"}
    if token:
        headers[auth_header] = f"{auth_scheme} {token}".strip()
    headers.update(_parse_custom_headers(custom_headers_raw))

    try:
        resp = requests.post(
            f"{base_url}{chat_path}",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning("Custom provider call failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        if isinstance(body, dict):
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                return str((choices[0] or {}).get("message", {}).get("content", "")).strip() or None
            message = body.get("message")
            if isinstance(message, dict):
                return str(message.get("content") or "").strip() or None
            if isinstance(body.get("content"), str):
                return str(body.get("content")).strip() or None
        return None
    except Exception as exc:
        logger.warning("Custom provider unavailable: %s", exc)
        return None


def chat_completion(
    prompt: str,
    max_tokens: int,
    databricks_endpoint: str,
    databricks_fallback_endpoint: str | None = None,
) -> Optional[str]:
    if not llm_enabled():
        return None

    provider = _provider()
    if provider == "databricks":
        return _chat_databricks(
            prompt,
            max_tokens=max_tokens,
            endpoint=databricks_endpoint,
            fallback_endpoint=databricks_fallback_endpoint,
        )
    if provider == "openai":
        return _chat_openai_compatible(prompt, max_tokens=max_tokens)
    if provider == "ollama":
        return _chat_ollama(prompt)
    if provider == "custom":
        return _chat_custom(prompt, max_tokens=max_tokens)
    return None


def provider_info() -> dict[str, str]:
    return {
        "provider": _provider(),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", ""),
        "openai_model": os.getenv("OPENAI_MODEL", ""),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", ""),
        "ollama_model": os.getenv("OLLAMA_MODEL", ""),
        "custom_base_url": os.getenv("CUSTOM_LLM_BASE_URL", ""),
        "custom_chat_path": os.getenv("CUSTOM_LLM_CHAT_PATH", ""),
    }
