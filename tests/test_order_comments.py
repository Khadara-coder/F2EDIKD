"""Order review comments persistence."""
from __future__ import annotations

from pathlib import Path

from src.file2edi.store import File2EdiStore


def _minimal_review(order_id: str, upload_id: str) -> dict:
    return {
        "order": {
            "orderId": order_id,
            "uploadId": upload_id,
            "fileName": "a.pdf",
            "clientName": "Client",
            "customerOrderNumber": "PO-1",
            "documentReference": "PO-1",
            "orderDate": "2026-08-10",
            "requestedDeliveryDate": "2026-08-11",
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": 10,
            "globalConfidence": 100,
            "status": "Revue requise",
            "reviewRequired": True,
            "lineCount": 0,
            "createdAt": "2026-08-10T10:00:00+00:00",
            "updatedAt": "2026-08-10T10:00:00+00:00",
        },
        "partners": [],
        "lines": [],
        "anomalies": [
            {
                "anomalyId": "an-1",
                "orderId": order_id,
                "severity": "warning",
                "fieldName": "ORDER_DATE_INVALID",
                "message": "Date invalide",
                "status": "Ouverte",
                "createdAt": "2026-08-10T10:00:00+00:00",
            }
        ],
    }


def test_add_order_comment_history_and_anomaly_link(tmp_path: Path):
    store = File2EdiStore(str(tmp_path / "t.db"), str(tmp_path / "intake"))
    store.save_order_review(_minimal_review("ord-1", "upl-1"))

    review = store.add_order_comment("ord-1", "Vérifier le SOLD-TO", actor="adv1")
    assert review is not None
    assert len(review["comments"]) == 1
    assert review["comments"][0]["body"] == "Vérifier le SOLD-TO"
    assert review["comments"][0]["actor"] == "adv1"
    assert not review["comments"][0].get("anomalyId")

    review = store.add_order_comment(
        "ord-1",
        "Date corrigée sur le PDF",
        actor="adv1",
        anomaly_id="an-1",
    )
    assert len(review["comments"]) == 2
    assert review["comments"][1]["anomalyId"] == "an-1"

    unknown = store.add_order_comment("missing", "x", actor="adv1")
    assert unknown is None

    empty = store.add_order_comment("ord-1", "   ", actor="adv1")
    assert empty is None
