"""Admin reprocess endpoint: allowed for any order status."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient

import server
import src.file2edi.router as router_mod
import src.file2edi.store as store_mod


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    async def _noop_init_postgres_db():
        return None

    monkeypatch.setattr(server, "_init_postgres_db", _noop_init_postgres_db)
    with TestClient(server.app, raise_server_exceptions=False) as tc:
        yield tc


def _engine_ok() -> dict:
    return {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "ord-reprocess",
        "order": {"po_number": "PO-9", "order_date": "2026-02-15", "delivery_date": None},
        "customer": {
            "soldto": "15021919",
            "shipto": "15021919",
            "name": "SISCA",
            "confidence": 90,
            "delivery_address": {"street": "1 rue", "postal_code": "69000", "city": "LYON", "country": "FR"},
            "detected_address": {"name": "SISCA", "street": "1 rue", "postal_code": "69000", "city": "LYON", "raw": ""},
        },
        "lines": {"count": 1, "items": [{"bosch_article": "7736504816", "quantity": 1, "unit_price": 10}]},
        "rejection": {"decision": "OK", "reason": None, "blocking_count": 0, "warning_count": 0, "details": []},
        "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
        "error": None,
    }


def test_reprocess_rejects_adv_session(monkeypatch: pytest.MonkeyPatch, client: TestClient, tmp_path: Path):
    from tests.test_server_auth_session import FakeStore

    fake_store = FakeStore({
        "adv-session": {"username": "adv", "displayName": "ADV", "role": "adv"},
    })
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)

    response = client.post("/api/orders/ord-1/reprocess", cookies={"f2edi_session": "adv-session"})
    assert response.status_code == 403


def test_reprocess_admin_can_retry_rejected_order(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    tmp_path: Path,
):
    from src.file2edi.store import File2EdiStore
    from tests.test_file2edi_debt_fixes import _minimal_review

    intake = tmp_path / "intake"
    intake.mkdir()
    pdf = intake / "upl-reprocess.pdf"
    pdf.write_bytes(b"%PDF-1.3\n%\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")

    sqlite_store = File2EdiStore(str(tmp_path / "f2e.db"), str(intake))
    review = _minimal_review("ord-reprocess", "upl-reprocess", "Rejeté")
    review["order"]["pdfPath"] = str(pdf)
    sqlite_store.save_order_review(review)
    sqlite_store.save_upload_with_id("upl-reprocess", "order.pdf", pdf.stat().st_size, str(pdf), uploaded_by="khadara")

    def get_store():
        return sqlite_store

    monkeypatch.setattr(store_mod, "get_store", get_store)
    monkeypatch.setattr(router_mod, "get_store", get_store)
    monkeypatch.setattr(server, "_APP_REQUIRE_AUTH", False)
    monkeypatch.setattr(router_mod, "ensure_admin", lambda req=None, payload=None: ("admin", "admin"))
    monkeypatch.setattr(router_mod.engine_bridge, "process_pdf", lambda *a, **k: _engine_ok())
    monkeypatch.setattr(router_mod.engine_bridge, "resolve_processing_actor", lambda *a, **k: "admin")
    monkeypatch.setattr(router_mod.engine_bridge, "init_db", lambda: None)
    monkeypatch.setattr(router_mod.engine_bridge, "upsert_conversion", lambda *a, **k: None)
    monkeypatch.setattr(router_mod, "_resolve_adv_username_from_soldto", lambda soldto, store: "lex1tc")

    response = client.post("/api/orders/ord-reprocess/reprocess", cookies={"f2edi_session": "admin-session"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order"]["orderId"] == "ord-reprocess"
    loaded = sqlite_store.load_order_review("ord-reprocess")
    assert loaded["order"]["assignedTo"] == "lex1tc"
    conn = sqlite_store._conn()
    row = conn.execute(
        "SELECT sap_sent_at, rejection_message FROM file2edi_orders WHERE order_id=?",
        ["ord-reprocess"],
    ).fetchone()
    conn.close()
    assert not row["sap_sent_at"]
    assert not row["rejection_message"]
