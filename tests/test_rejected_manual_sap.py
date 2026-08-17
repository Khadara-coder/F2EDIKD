"""ADV/admin can treat a system-rejected order and send it to SAP."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient

import server
import src.file2edi.router as router_mod
import src.file2edi.store as store_mod
import src.sftp_delivery as sftp_delivery
from src.file2edi.router import _mandatory_review_errors, _require_mutable_order
from src.file2edi.store import File2EdiStore


def _complete_rejected_review(order_id: str, upload_id: str) -> dict:
    return {
        "order": {
            "orderId": order_id,
            "uploadId": upload_id,
            "fileName": f"{order_id}.pdf",
            "clientName": "Client Test",
            "customerOrderNumber": "PO-167658",
            "documentReference": "PO-167658",
            "orderDate": "2024-02-15",
            "requestedDeliveryDate": "2024-02-20",
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": 10,
            "globalConfidence": 0,
            "status": "Rejeté",
            "reviewRequired": True,
            "lineCount": 1,
            "rejectionMessage": "PDF_PARSE_FAILURE",
            "createdAt": "2026-08-17T10:00:00+00:00",
            "updatedAt": "2026-08-17T10:00:00+00:00",
        },
        "partners": [
            {
                "partnerId": f"p-soldto-{order_id}",
                "orderId": order_id,
                "partnerFunction": "soldto",
                "partnerCode": "15019903",
                "partnerName": "Client Test",
                "addressLine1": "Rue Test",
                "postalCode": "02400",
                "city": "ETAMPES",
                "country": "FR",
                "confidence": 100,
            },
            {
                "partnerId": f"p-shipto-{order_id}",
                "orderId": order_id,
                "partnerFunction": "shipto",
                "partnerCode": "15019903",
                "partnerName": "Client Test",
                "addressLine1": "Rue Test",
                "postalCode": "02400",
                "city": "ETAMPES",
                "country": "FR",
                "confidence": 100,
            },
        ],
        "lines": [
            {
                "lineId": f"ln-{order_id}-1",
                "orderId": order_id,
                "lineNumber": 1,
                "boschArticle": "7736504816",
                "customerArticle": "",
                "designation": "Article",
                "quantity": 1,
                "unit": "PCE",
                "unitPrice": 10,
                "amount": 10,
                "requestedDate": "2024-02-20",
                "confidence": 100,
                "status": "Corrigé manuellement",
                "manuallyEdited": True,
            }
        ],
        "anomalies": [],
    }


def test_mandatory_errors_do_not_block_rejected_status():
    review = _complete_rejected_review("ord-rej", "upl-rej")
    assert _mandatory_review_errors(review) == []


def test_rejected_order_remains_mutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_complete_rejected_review("ord-rej", "upl-rej"))
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    loaded = _require_mutable_order("ord-rej")
    assert loaded["order"]["status"] == "Rejeté"


def test_rejected_order_can_generate_then_mark_sent(tmp_path: Path):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_complete_rejected_review("ord-rej", "upl-rej"))
    store.mark_edifact_generated("ord-rej", "ORDERS_ord-rej.tst", "UNB+TEST'\nUNZ+1+1'", actor="adv")
    after_gen = store.load_order_review("ord-rej")
    assert after_gen["order"]["status"] == "Généré"
    store.mark_sftp_delivery("ord-rej", True, "/edi/in/ORDERS_ord-rej.tst", sent_by="adv")
    after_send = store.load_order_review("ord-rej")
    assert after_send["order"]["status"] == "Envoyé SAP"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    async def _noop_init_postgres_db():
        return None

    monkeypatch.setattr(server, "_init_postgres_db", _noop_init_postgres_db)
    with TestClient(server.app, raise_server_exceptions=False) as tc:
        yield tc


def test_adv_can_generate_edifact_for_rejected_order(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    tmp_path: Path,
):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_complete_rejected_review("ord-rej", "upl-rej"))

    async def fake_generate(cid, req):
        return {
            "generated": True,
            "tst_filename": "ORDERS_ord-rej.tst",
            "edifact_content": "UNB+TEST'\nUNZ+1+1'",
        }

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    monkeypatch.setattr(server, "_APP_REQUIRE_AUTH", False)
    monkeypatch.setattr(router_mod.engine_bridge, "generate_edifact", fake_generate)
    monkeypatch.setattr(router_mod.engine_bridge, "init_db", lambda: None)
    monkeypatch.setattr(router_mod.engine_bridge, "load_conversion", lambda cid: {"id": cid})

    response = client.post("/api/orders/ord-rej/generate-edifact")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    loaded = store.load_order_review("ord-rej")
    assert loaded["order"]["status"] == "Généré"


def test_adv_can_send_rejected_order_to_sap(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    tmp_path: Path,
):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    store.save_order_review(_complete_rejected_review("ord-rej", "upl-rej"))
    store.mark_edifact_generated("ord-rej", "ORDERS_ord-rej.tst", "UNB+TEST'\nUNZ+1+1'", actor="adv")

    def fake_upload_tst(local_path, tst_filename, sftp_cfg):
        return SimpleNamespace(
            success=True,
            tst_filename=tst_filename,
            remote_path=f"{sftp_cfg.remote_dir}/{tst_filename}",
            file_size=local_path.stat().st_size,
            attempts=1,
            error_reason="",
        )

    monkeypatch.setattr(store_mod, "get_store", lambda: store)
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    monkeypatch.setattr(sftp_delivery, "upload_tst", fake_upload_tst)
    monkeypatch.setattr(server, "_APP_REQUIRE_AUTH", False)
    monkeypatch.setenv("SFTP_HOST", "sftp.example.test")
    monkeypatch.setenv("SFTP_USERNAME", "sap-user")
    monkeypatch.setenv("SFTP_PASSWORD", "secret")
    monkeypatch.setenv("SFTP_REMOTE_DIR", "/edi/in")

    response = client.post("/api/orders/ord-rej/send-sap", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True
    loaded = store.load_order_review("ord-rej")
    assert loaded["order"]["status"] == "Envoyé SAP"
