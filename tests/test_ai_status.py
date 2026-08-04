"""Unit tests for AI configuration health status."""

from __future__ import annotations

import os

from src.ai_status import get_ai_configuration_status


def test_databricks_configured_when_token_present(monkeypatch):
    monkeypatch.setenv("DATABRICKS_TOKEN", "secret-token")
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    status = get_ai_configuration_status({"aiProvider": "databricks"})
    assert status["configured"] is True
    assert status["provider"] == "databricks"


def test_databricks_missing_token(monkeypatch):
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    status = get_ai_configuration_status({"aiProvider": "databricks"})
    assert status["configured"] is False
    assert "manquant" in status["detail"]


def test_openai_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = get_ai_configuration_status({"aiProvider": "openai"})
    assert status["configured"] is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    status = get_ai_configuration_status({"aiProvider": "openai"})
    assert status["configured"] is True
    assert status["provider"] == "openai"


def test_ollama_defaults_to_local_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    status = get_ai_configuration_status({"aiProvider": "ollama", "ollamaConfig": {}})
    assert status["configured"] is True
    assert status["provider"] == "ollama"


def test_custom_requires_url_and_token(monkeypatch):
    for key in ("CUSTOM_LLM_BASE_URL", "CUSTOM_LLM_API_KEY", "CUSTOM_LLM_TOKEN", "CUSTOM_LLM_AUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    status = get_ai_configuration_status({"aiProvider": "custom", "customAiConfig": {}})
    assert status["configured"] is False
    monkeypatch.setenv("CUSTOM_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("CUSTOM_LLM_API_KEY", "tok")
    status = get_ai_configuration_status({"aiProvider": "custom", "customAiConfig": {}})
    assert status["configured"] is True
