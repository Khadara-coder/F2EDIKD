import json

from src.file2edi.mapper import engine_to_order_review
from src.file2edi.store import File2EdiStore


def _review(order_id: str = "ord-workflow") -> dict:
    return {
        "order": {
            "orderId": order_id,
            "uploadId": "upl-workflow",
            "fileName": "order.pdf",
            "clientName": "Client Test",
            "customerOrderNumber": "PO-123",
            "documentReference": "PO-123",
            "orderDate": "2026-08-04",
            "requestedDeliveryDate": "2026-08-05",
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": 10,
            "globalConfidence": 100,
            "status": "Généré",
            "reviewRequired": False,
            "lineCount": 1,
            "createdAt": "2026-08-04T09:00:00+00:00",
            "updatedAt": "2026-08-04T09:00:00+00:00",
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
                "lineId": "ln-workflow-1",
                "orderId": order_id,
                "lineNumber": 1,
                "customerReference": "",
                "boschArticle": "7735500779",
                "designation": "BALLON ECS",
                "quantity": 1,
                "unit": "PCE",
                "unitPrice": 10,
                "amount": 10,
                "confidence": 100,
                "status": "OK",
            }
        ],
        "anomalies": [],
    }


def test_engine_review_flags_invalid_line_delivery_date():
    result = {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "hash-1",
        "order": {"po_number": "PO-123", "order_date": "2026-08-04"},
        "customer": {"soldto": "15019903", "shipto": "15019903", "name": "Client Test", "confidence": 100},
        "lines": {
            "items": [
                {
                    "code_article": "7735500779",
                    "description": "BALLON ECS",
                    "quantite": 1,
                    "prix_unitaire_ht": 10,
                    "date_livraison": "32/26",
                }
            ]
        },
    }

    review = engine_to_order_review("hash-1", "upl-1", result)

    assert any(
        anomaly["fieldName"] == "deliveryDate"
        and "date de livraison extraite invalide" in anomaly["message"]
        for anomaly in review["anomalies"]
    )


def test_manual_line_update_invalidates_generated_edifact_and_tracks_corrections(tmp_path):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-workflow"
    store.save_order_review(_review(order_id))
    store.mark_edifact_generated(order_id, "ORDERS_TEST.tst", "UNB+TEST'\nUNZ+1+1'", actor="khadara")

    assert store.get_edifact_export(order_id) is not None

    updated = store.update_line("ln-workflow-1", {"quantity": 2})
    assert updated is not None

    assert store.get_edifact_export(order_id) is None
    assert updated["order"]["status"] == "À revoir"
    assert updated["order"]["reviewRequired"] is True

    conn = store._conn()
    row = conn.execute(
        "SELECT soldto, corrections_json FROM file2edi_orders WHERE order_id=?",
        [order_id],
    ).fetchone()
    conn.close()

    assert row["soldto"] == "15019903"
    snapshot = json.loads(row["corrections_json"])
    assert snapshot["lines"][0]["quantity"] == 2
    assert snapshot["lines"][0]["manuallyEdited"] is True
