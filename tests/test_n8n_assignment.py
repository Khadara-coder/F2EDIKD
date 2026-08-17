"""n8n proxy submissions use the same ADV assignment and business logs as UI."""

from __future__ import annotations

import copy

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient

import server
import src.file2edi.router as router_mod
import src.file2edi.store as store_mod
from tests.test_order_reprocess import _engine_ok


class _ProxyStore:
    def __init__(self) -> None:
        self.review: dict | None = None
        self.events: list[dict] = []

    def load_order_review(self, order_id: str):
        return None

    def save_order_review(self, review: dict) -> None:
        self.review = copy.deepcopy(review)

    def log_business_event(self, **payload):
        self.events.append(payload)
        return payload


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    async def _noop_init_postgres_db():
        return None

    monkeypatch.setattr(server, "_init_postgres_db", _noop_init_postgres_db)
    with TestClient(server.app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_n8n_proxy_assigns_adv_and_writes_business_log(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    store = _ProxyStore()
    result = _engine_ok()
    result["pdf_hash"] = "ord-n8n"
    result["pdf_storage_path"] = "/app/data/intake/proxy-ord-n8n.pdf"

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    monkeypatch.setattr(server, "_APP_REQUIRE_AUTH", False)
    monkeypatch.setattr(server, "_local_process_and_respond", lambda *a, **k: result)
    monkeypatch.setattr(server, "_resolve_processing_actor", lambda *a, **k: "n8n")
    monkeypatch.setattr(server, "_init_db", lambda: None)
    monkeypatch.setattr(server, "_upsert_conversion", lambda *a, **k: None)
    monkeypatch.setattr(server, "_emit_conversion_callback", lambda *a, **k: None)
    monkeypatch.setattr(
        router_mod,
        "_resolve_adv_username_from_soldto",
        lambda soldto, current_store: "lex1tc",
    )

    response = client.post(
        "/api/proxy/convert",
        files={"file": ("order.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"source": "n8n"},
    )

    assert response.status_code == 200, response.text
    assert store.review is not None
    assert store.review["order"]["source"] == "n8n"
    assert store.review["order"]["assignedTo"] == "lex1tc"
    assert len(store.events) == 1
    event = store.events[0]
    assert event["action"] == "upload.extract_direct"
    assert event["order_id"] == "ord-n8n"
    assert event["details"]["source"] == "n8n"
    assert event["details"]["soldto"] == "15021919"
    assert event["details"]["assignedTo"] == "lex1tc"
