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
        anomaly["fieldName"] == "DELIVERY_DATE_INVALID"
        and "date de livraison" in anomaly["message"].lower()
        for anomaly in review["anomalies"]
    )


def test_engine_review_drops_order_level_delivery_date_when_line_exists():
    result = {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "hash-dd",
        "order": {"po_number": "PO-123", "order_date": "2026-08-04"},
        "customer": {"soldto": "15019903", "shipto": "15019903", "name": "Client Test", "confidence": 100},
        "rejection": {
            "decision": "REJECT",
            "details": [
                {
                    "code": "DELIVERY_DATE_INVALID",
                    "severity": "blocking",
                    "message": "Date de livraison invalide (ordre)",
                },
            ],
        },
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

    review = engine_to_order_review("hash-dd", "upl-1", result)
    delivery = [
        a for a in review["anomalies"]
        if a.get("fieldName") == "DELIVERY_DATE_INVALID"
    ]
    assert len(delivery) == 1
    assert delivery[0].get("lineId")
    assert "Ligne" in delivery[0]["message"]


def test_global_confidence_is_capped_by_line_quality():
    result = {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "hash-weak-line",
        "order": {"po_number": "PO-123", "order_date": "2026-08-04"},
        "customer": {"soldto": "15019903", "shipto": "15019903", "name": "Client Test", "confidence": 100},
        "lines": {
            "items": [
                {
                    "code_article": "7735500779",
                    "description": "BALLON ECS",
                    "quantite": 1,
                    "prix_unitaire_ht": "",
                    "montant_ligne_ht": "",
                }
            ]
        },
    }

    review = engine_to_order_review("hash-weak-line", "upl-1", result)

    assert review["order"]["globalConfidence"] == 70
    assert review["order"]["status"] == "Revue requise"
    assert review["lines"][0]["confidence"] == 70


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


def test_shipto_address_change_rematches_existing_code_to_unique_masterdata_partner(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-shipto-rematch"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {"15019903": {"id": "15019903", "name": "Client Test"}},
        "partners_by_soldto": {
            "15019903": [
                {"id": "15019904", "name": "Depot Lyon", "street": "10 RUE A", "postal": "69000", "city": "LYON", "country": "FR"},
                {"id": "15019905", "name": "Depot Paris", "street": "20 RUE B", "postal": "75000", "city": "PARIS", "country": "FR"},
            ]
        },
    })

    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"addressLine1": "20 RUE B", "postalCode": "75000", "city": "PARIS", "editSource": "manual"},
    )

    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == "15019905"
    assert shipto["partnerName"] == "Depot Paris"
    assert shipto["postalCode"] == "75000"
    assert not updated["anomalies"]


def test_shipto_address_change_without_unique_match_creates_blocking_anomaly(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-shipto-ambiguous"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {"15019903": {"id": "15019903", "name": "Client Test"}},
        "partners_by_soldto": {
            "15019903": [
                {"id": "15019904", "name": "Depot A", "street": "10 RUE A", "postal": "69000", "city": "LYON", "country": "FR"},
                {"id": "15019905", "name": "Depot B", "street": "20 RUE B", "postal": "69000", "city": "LYON", "country": "FR"},
            ]
        },
    })

    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"postalCode": "69000", "city": "LYON", "editSource": "manual"},
    )

    anomaly = next(a for a in updated["anomalies"] if a["fieldName"] == "SHIPTO_MASTERDATA_MISMATCH")
    assert anomaly["status"] == "Bloquante"


def test_soldto_change_propagates_billing_and_revalidates_shipto(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-soldto-propagation"
    review = _review(order_id)
    review["partners"][1].update({
        "partnerCode": "OLD",
        "partnerName": "New Depot",
        "addressLine1": "20 RUE B",
        "postalCode": "75000",
        "city": "PARIS",
    })
    review["partners"].extend([
        {
            "partnerId": f"p-billto-{order_id}", "orderId": order_id, "partnerFunction": "billto",
            "partnerCode": "OLD", "partnerName": "Old", "addressLine1": "Old street",
            "postalCode": "00000", "city": "OLD", "country": "FR", "confidence": 100,
        },
        {
            "partnerId": f"p-payer-{order_id}", "orderId": order_id, "partnerFunction": "payer",
            "partnerCode": "OLD", "partnerName": "Old", "addressLine1": "Old street",
            "postalCode": "00000", "city": "OLD", "country": "FR", "confidence": 100,
        },
    ])
    store.save_order_review(review)
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {
            "15019904": {"id": "15019904", "name": "New Customer", "street": "1 RUE C", "postal": "69000", "city": "LYON", "country": "FR"},
        },
        "partners_by_soldto": {
            "15019904": [
                {"id": "15019905", "name": "New Depot", "street": "20 RUE B", "postal": "75000", "city": "PARIS", "country": "FR"},
            ]
        },
    })

    updated = store.update_partner(
        f"p-soldto-{order_id}",
        {"partnerCode": "15019904", "editSource": "manual"},
    )

    by_function = {p["partnerFunction"]: p for p in updated["partners"]}
    assert by_function["soldto"]["partnerName"] == "New Customer"
    assert by_function["billto"]["partnerCode"] == "15019904"
    assert by_function["payer"]["partnerCode"] == "15019904"
    assert by_function["shipto"]["partnerCode"] == "15019905"


def test_order_number_change_refreshes_duplicate_anomaly(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-po-duplicate-refresh"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "salesorders_by_bstnk": {"PO-999": {"VBELN": "500009"}},
    })

    updated = store.update_order_header(order_id, {"customerOrderNumber": "PO-999"})

    anomaly = next(a for a in updated["anomalies"] if a["fieldName"] == "PO_NUMBER_DUPLICATE")
    assert anomaly["severity"] == "warning"
    assert anomaly["status"] == "Ouverte"


def test_add_lines_bulk_appends_numbered_lines(tmp_path):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-bulk"
    store.save_order_review(_review(order_id))

    updated = store.add_lines_bulk(order_id, [
        {"boschArticle": "111", "quantity": 2, "unitPrice": 5},
        {"boschArticle": "222", "quantity": 1, "unitPrice": 10},
    ])

    assert updated is not None
    assert len(updated["lines"]) == 3
    assert updated["lines"][1]["lineNumber"] == 2
    assert updated["lines"][1]["boschArticle"] == "111"
    assert updated["lines"][2]["lineNumber"] == 3
    assert updated["lines"][2]["boschArticle"] == "222"
    assert updated["lines"][1]["status"] == "Corrigé manuellement"
