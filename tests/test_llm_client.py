"""Tests for src/llm_client.py — direct REST Databricks client."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_response(payload: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock() if status == 200 else MagicMock(side_effect=Exception(f"HTTP {status}"))
    return resp


def _chat_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _reasoning_response(text: str) -> dict:
    return {
        "choices": [{
            "message": {
                "content": [
                    {"type": "reasoning", "summary": [{"type": "summary_text", "text": "internal"}]},
                    {"type": "text", "text": text},
                ]
            }
        }]
    }


# ── _text_from_content ────────────────────────────────────────────────────────

class TestTextFromContent:
    def test_plain_string(self):
        from src.llm_client import _text_from_content
        assert _text_from_content("hello") == "hello"

    def test_list_with_text_block(self):
        from src.llm_client import _text_from_content
        blocks = [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking..."}]},
            {"type": "text", "text": "answer"},
        ]
        assert _text_from_content(blocks) == "answer"

    def test_list_reasoning_only_fallback(self):
        from src.llm_client import _text_from_content
        blocks = [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "step1"}]},
        ]
        result = _text_from_content(blocks)
        assert "step1" in result

    def test_non_string_non_list(self):
        from src.llm_client import _text_from_content
        assert _text_from_content(42) == "42"


# ── _invocation_url ───────────────────────────────────────────────────────────

class TestInvocationUrl:
    def test_builds_url_correctly(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://myworkspace.azuredatabricks.net")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        url = llm_client._invocation_url("my-model")
        assert url == "https://myworkspace.azuredatabricks.net/serving-endpoints/my-model/invocations"

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://myworkspace.azuredatabricks.net/")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        url = llm_client._invocation_url("ep")
        assert "//" not in url.split("https://")[1]

    def test_empty_host_returns_empty(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        assert llm_client._invocation_url("ep") == ""


# ── _auth_headers ─────────────────────────────────────────────────────────────

class TestAuthHeaders:
    def test_bearer_token_when_env_set(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapiABCDEF")
        from src import llm_client
        headers = llm_client._auth_headers()
        assert headers["Authorization"] == "Bearer dapiABCDEF"
        assert headers["Content-Type"] == "application/json"

    def test_no_token_falls_through_to_sdk(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_TOKEN", "")
        mock_ws = MagicMock()
        mock_ws.config.authenticate.return_value = {"Authorization": "Bearer oauth-token"}
        with patch("databricks.sdk.WorkspaceClient", return_value=mock_ws):
            from src import llm_client
            headers = llm_client._auth_headers()
            assert "Authorization" in headers

    def test_sdk_failure_returns_content_type_only(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_TOKEN", "")
        with patch("databricks.sdk.WorkspaceClient", side_effect=ImportError("no sdk")):
            from src import llm_client
            headers = llm_client._auth_headers()
            assert "Content-Type" in headers


# ── _predict ──────────────────────────────────────────────────────────────────

class TestPredict:
    def test_successful_prediction(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        mock_resp = _mock_response(_chat_response("Paris"))
        with patch("requests.post", return_value=mock_resp) as mock_post:
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client._predict("my-model", [{"role": "user", "content": "capitale?"}], 100)

        assert result == "Paris"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "serving-endpoints/my-model/invocations" in call_kwargs[0][0]
        body = call_kwargs[1]["json"]
        assert body["messages"][0]["content"] == "capitale?"
        assert body["max_tokens"] == 100

    def test_reasoning_model_response(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        mock_resp = _mock_response(_reasoning_response("final answer"))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client._predict("gpt-oss-120b", [{"role": "user", "content": "q"}], 500)

        assert result == "final answer"

    def test_empty_host_returns_none(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        result = llm_client._predict("model", [], 100)
        assert result is None

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        with patch("requests.post", side_effect=Exception("connection refused")):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client._predict("model", [], 100)

        assert result is None

    def test_auth_error_header_returns_none(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "")
        with patch("databricks.sdk.WorkspaceClient", side_effect=ImportError("no sdk")):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client._predict("model", [], 100)

        assert result is None


# ── llm_call ──────────────────────────────────────────────────────────────────

class TestLlmCall:
    def test_returns_text_on_success(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
        monkeypatch.setenv("DATABRICKS_MODEL_ENDPOINT", "my-model")

        mock_resp = _mock_response(_chat_response("Bonjour"))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_call("Dis bonjour")

        assert result == "Bonjour"

    def test_fallback_when_primary_fails(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
        monkeypatch.setenv("DATABRICKS_MODEL_ENDPOINT", "primary-model")

        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            if "primary-model" in url:
                raise Exception("primary down")
            return _mock_response(_chat_response("fallback answer"))

        with patch("requests.post", side_effect=side_effect):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_call("question")

        assert result == "fallback answer"
        assert call_count[0] == 2

    def test_with_system_message(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        mock_resp = _mock_response(_chat_response("ok"))
        with patch("requests.post", return_value=mock_resp) as mock_post:
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            llm_client.llm_call("user prompt", system="You are helpful")

        body = mock_post.call_args[1]["json"]
        assert body["messages"][0] == {"role": "system", "content": "You are helpful"}
        assert body["messages"][1]["role"] == "user"

    def test_returns_none_when_both_fail(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        result = llm_client.llm_call("question")
        assert result is None


# ── llm_extract_json ──────────────────────────────────────────────────────────

class TestLlmExtractJson:
    def test_parses_plain_json(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        mock_resp = _mock_response(_chat_response('{"order": "12345"}'))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_extract_json("extract order number")

        assert result == {"order": "12345"}

    def test_strips_markdown_fences(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        raw = '```json\n{"key": "value"}\n```'
        mock_resp = _mock_response(_chat_response(raw))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_extract_json("extract")

        assert result == {"key": "value"}

    def test_extracts_embedded_json_object(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        raw = 'Here is the result: {"x": 1} as requested.'
        mock_resp = _mock_response(_chat_response(raw))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_extract_json("extract")

        assert result == {"x": 1}

    def test_returns_none_on_unparseable(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "https://host.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")

        mock_resp = _mock_response(_chat_response("désolé, je ne peux pas répondre"))
        with patch("requests.post", return_value=mock_resp):
            from src import llm_client
            import importlib
            importlib.reload(llm_client)
            result = llm_client.llm_extract_json("extract")

        assert result is None

    def test_returns_none_when_llm_unavailable(self, monkeypatch):
        monkeypatch.setenv("DATABRICKS_HOST", "")
        from src import llm_client
        import importlib
        importlib.reload(llm_client)
        result = llm_client.llm_extract_json("extract")
        assert result is None
