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


def test_engine_review_ignores_garbled_line_level_delivery_date():
    """Delivery date is a document-level field; a stray per-line value must not
    raise a per-line anomaly."""
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

    assert not any(anomaly["fieldName"] == "DELIVERY_DATE_INVALID" for anomaly in review["anomalies"])


def test_engine_review_keeps_document_level_delivery_date_rejection():
    """An upstream document-level DELIVERY_DATE_INVALID rejection must surface
    as-is; it is no longer deduped in favour of a (removed) per-line anomaly."""
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
    assert not delivery[0].get("lineId")
    assert delivery[0]["message"] == "La date de livraison est manquante ou invalide."


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

    anomaly = next(a for a in updated["anomalies"] if a["fieldName"] == "SHIPTO_NO_STRONG_MATCH")
    assert anomaly["status"] == "Bloquante"


def test_clearing_soldto_code_clears_address_and_raises_anomaly(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-clear-soldto"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {"15019903": {"id": "15019903", "name": "Client Test"}},
        "partners_by_soldto": {"15019903": []},
    })

    updated = store.update_partner(
        f"p-soldto-{order_id}",
        {"partnerCode": "", "editSource": "manual"},
    )

    soldto = next(p for p in updated["partners"] if p["partnerFunction"] == "soldto")
    assert soldto["partnerCode"] == ""
    assert soldto["partnerName"] == ""
    assert soldto["addressLine1"] == ""
    assert updated["order"]["clientName"] == ""
    row = store._conn().execute("SELECT soldto FROM file2edi_orders WHERE order_id=?", [order_id]).fetchone()
    assert not row["soldto"]
    # Ship-to cannot stand without its Sold-to: it must be voided too.
    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == ""
    assert shipto["partnerName"] == ""
    assert shipto["addressLine1"] == ""
    assert any(a["fieldName"] == "SOLDTO_NOT_FOUND" and a["status"] == "Bloquante" for a in updated["anomalies"])
    assert any(a["fieldName"] == "SOLDTO_NOT_FOUND" and a["status"] == "Bloquante" for a in updated["anomalies"])


def test_soldto_change_voids_mismatched_shipto_but_keeps_order_number_and_dates(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-soldto-change-voids-shipto"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {
            "15019904": {"id": "15019904", "name": "New Customer", "street": "1 RUE C", "postal": "69000", "city": "LYON", "country": "FR"},
        },
        "partners_by_soldto": {"15019904": []},
    })

    updated = store.update_partner(
        f"p-soldto-{order_id}",
        {"partnerCode": "15019904", "editSource": "manual"},
    )

    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == ""
    assert shipto["partnerName"] == ""
    assert shipto["addressLine1"] == ""
    assert updated["order"]["clientName"] == ""
    # N° commande client is never part of the "vidage": it must survive the Sold-to change.
    assert updated["order"]["customerOrderNumber"] == "PO-123"
    # Dates are never part of the "vidage" either.
    assert updated["order"]["orderDate"] == "2026-08-04"
    assert updated["order"]["requestedDeliveryDate"] == "2026-08-05"
    assert any(a["fieldName"] == "SHIPTO_NO_STRONG_MATCH" and a["status"] == "Bloquante" for a in updated["anomalies"])



def test_clearing_shipto_code_clears_address_and_raises_anomaly(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-clear-shipto"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {"15019903": {"id": "15019903", "name": "Client Test"}},
        "partners_by_soldto": {"15019903": []},
    })

    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"partnerCode": "", "editSource": "manual"},
    )

    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == ""
    assert shipto["partnerName"] == ""
    assert shipto["addressLine1"] == ""
    assert updated["order"]["clientName"] == ""
    assert any(a["fieldName"] == "SHIPTO_NO_STRONG_MATCH" and a["status"] == "Bloquante" for a in updated["anomalies"])


def test_shipto_infers_unique_distinct_parent_soldto_when_soldto_empty(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-infer-soldto"
    review = _review(order_id)
    # Clear soldto initially
    review["partners"][0].update({"partnerCode": "", "partnerName": "", "addressLine1": "", "postalCode": "", "city": ""})
    review["partners"][1].update({"partnerCode": "", "partnerName": "", "addressLine1": "", "postalCode": "", "city": ""})
    store.save_order_review(review)

    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {
            "15015760": {"id": "15015760", "name": "ISERBA", "street": "303 RUE CHAT BOTTE", "postal": "01704", "city": "BEYNOST", "country": "FR"},
        },
        "partners_by_soldto": {
            "15015760": [
                {"id": "15018062", "name": ".ISERBA (AVI)", "street": "221 RUE LOUIS BRAILLE", "postal": "84310", "city": "MORIERES-LES-AVIGNON", "country": "FR"}
            ]
        },
        "partners_by_shipto": {
            "15018062": ["15015760"]
        },
    })

    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"partnerCode": "15018062", "editSource": "manual"},
    )

    soldto = next(p for p in updated["partners"] if p["partnerFunction"] == "soldto")
    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")

    # Both Sold-to and Ship-to are populated automatically
    assert soldto["partnerCode"] == "15015760"
    assert soldto["partnerName"] == "ISERBA"
    assert soldto["postalCode"] == "01704"
    assert shipto["partnerCode"] == "15018062"
    assert shipto["partnerName"] == ".ISERBA (AVI)"
    assert shipto["postalCode"] == "84310"

    # No blocking partner anomalies remain
    partner_blockers = [
        a for a in updated["anomalies"]
        if a.get("status") == "Bloquante" and a.get("fieldName") in ("SOLDTO_NOT_FOUND", "SHIPTO_SOLDTO_MISMATCH", "SHIPTO_NO_STRONG_MATCH")
    ]
    assert not partner_blockers


def test_shipto_does_not_infer_soldto_when_multiple_parents_or_same_code(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-no-infer-soldto"
    review = _review(order_id)
    # Clear soldto initially
    review["partners"][0].update({"partnerCode": "", "partnerName": "", "addressLine1": "", "postalCode": "", "city": ""})
    review["partners"][1].update({"partnerCode": "", "partnerName": "", "addressLine1": "", "postalCode": "", "city": ""})
    store.save_order_review(review)

    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {
            "15001000": {"id": "15001000", "name": "Client 1", "street": "Street 1", "postal": "75001", "city": "PARIS"},
            "15002000": {"id": "15002000", "name": "Client 2", "street": "Street 2", "postal": "75002", "city": "PARIS"},
        },
        "partners_by_soldto": {
            "15001000": [{"id": "15009999", "name": "Shared Depot", "street": "Rue X", "postal": "69000", "city": "LYON"}],
            "15002000": [{"id": "15009999", "name": "Shared Depot", "street": "Rue X", "postal": "69000", "city": "LYON"}],
        },
        "partners_by_shipto": {
            "15009999": ["15001000", "15002000"]
        },
    })

    # Setting shipto 15009999 which has 2 parents
    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"partnerCode": "15009999", "editSource": "manual"},
    )

    soldto = next(p for p in updated["partners"] if p["partnerFunction"] == "soldto")
    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")

    # Sold-to remains empty
    assert soldto["partnerCode"] == ""
    assert soldto["partnerName"] == ""
    assert shipto["partnerCode"] == "15009999"

    # SOLDTO_NOT_FOUND anomaly is raised
    assert any(a["fieldName"] == "SOLDTO_NOT_FOUND" and a["status"] == "Bloquante" for a in updated["anomalies"])


def test_shipto_from_another_soldto_family_is_blocked(tmp_path, monkeypatch):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-cross-family"
    store.save_order_review(_review(order_id))
    monkeypatch.setattr(store, "_load_masterdata_safe", lambda: {
        "customers_by_id": {"15019903": {"id": "15019903", "name": "Client Test"}},
        "partners_by_soldto": {
            "15019903": [{"id": "15019904", "name": "Depot A"}],
            "OTHER": [{"id": "99999999", "name": "Foreign Depot"}],
        },
    })

    updated = store.update_partner(
        f"p-shipto-{order_id}",
        {"partnerCode": "99999999", "editSource": "manual"},
    )

    anomaly = next(a for a in updated["anomalies"] if a["fieldName"] == "SHIPTO_SOLDTO_MISMATCH")
    assert anomaly["status"] == "Bloquante"
    # An explicitly selected Ship-to outside the Sold-to family must be voided,
    # consistent with every other mismatch/void path.
    shipto = next(p for p in updated["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == ""
    assert shipto["partnerName"] == ""
    assert shipto["addressLine1"] == ""
    assert updated["order"]["clientName"] == ""


def test_precise_partner_anomaly_replaces_generic_partner_unresolved():
    result = {
        "status": "OK",
        "filename": "order.pdf",
        "pdf_hash": "partner-dedupe",
        "order": {"po_number": "PO-1", "order_date": "2026-09-14"},
        "customer": {"soldto": "", "shipto": "", "confidence": 0},
        "lines": {"items": []},
        "rejection": {
            "decision": "REJECTED",
            "details": [
                {"code": "PARTNER_UNRESOLVED", "severity": "warning"},
                {"code": "SOLDTO_NOT_FOUND", "severity": "blocking"},
            ],
        },
    }

    review = engine_to_order_review("partner-dedupe", "upl-partner", result)
    codes = {a["fieldName"] for a in review["anomalies"]}
    assert "SOLDTO_NOT_FOUND" in codes
    assert "PARTNER_UNRESOLVED" not in codes


def test_partner_anomalies_are_collapsed_for_adv_and_resolved_together(tmp_path):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    review = _review("ord-partner-collapse")
    review["anomalies"] = [
        {
            "anomalyId": "partner-address",
            "orderId": "ord-partner-collapse",
            "severity": "error",
            "fieldName": "NO_DELIVERY_ADDRESS",
            "message": "adresse technique",
            "status": "Bloquante",
            "createdAt": "2026-08-04T09:00:00+00:00",
        },
        {
            "anomalyId": "partner-shipto",
            "orderId": "ord-partner-collapse",
            "severity": "error",
            "fieldName": "SHIPTO_NO_STRONG_MATCH",
            "message": "ship-to technique",
            "status": "Bloquante",
            "createdAt": "2026-08-04T09:00:01+00:00",
        },
        {
            "anomalyId": "partner-soldto",
            "orderId": "ord-partner-collapse",
            "severity": "error",
            "fieldName": "SOLDTO_NOT_FOUND",
            "message": "sold-to technique",
            "status": "Bloquante",
            "createdAt": "2026-08-04T09:00:02+00:00",
        },
    ]
    store.save_order_review(review)

    displayed = store.load_order_review("ord-partner-collapse", collapse_partner=True)
    assert displayed is not None
    partner_anomalies = [
        a for a in displayed["anomalies"]
        if a.get("uxGroup") == "Partenaire"
    ]
    assert len(partner_anomalies) == 1
    assert partner_anomalies[0]["message"] == "Génie n'a pas pu identifier le Sold-to"
    assert set(partner_anomalies[0]["relatedCodes"]) == {
        "NO_DELIVERY_ADDRESS", "SHIPTO_NO_STRONG_MATCH", "SOLDTO_NOT_FOUND",
    }

    updated = store.resolve_anomaly(
        partner_anomalies[0]["anomalyId"],
        "choice",
        outcome="confirm_and_recontrol",
        actor="adv1",
    )
    assert updated is not None
    assert all(a["status"] == "Corrigée" for a in updated["anomalies"])


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


def test_header_edits_are_tracked_as_manually_edited_fields(tmp_path):
    store = File2EdiStore(str(tmp_path / "file2edi.db"), str(tmp_path / "intake"))
    order_id = "ord-header-manual-flags"
    store.save_order_review(_review(order_id))

    updated = store.update_order_header(order_id, {"customerOrderNumber": "PO-999"})
    assert updated["order"]["manuallyEditedFields"] == ["customerOrderNumber"]

    updated = store.update_order_header(order_id, {"orderDate": "2026-08-06"})
    assert sorted(updated["order"]["manuallyEditedFields"]) == ["customerOrderNumber", "orderDate"]


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
