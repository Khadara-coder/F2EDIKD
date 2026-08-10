"""Tests for SAP processing feedback (Envoyé SAP → Confirmé SAP)."""
from __future__ import annotations

from pathlib import Path

from src.file2edi.store import File2EdiStore
from src.sap_feedback import (
    STATUS_CONFIRMED,
    STATUS_SENT,
    find_sap_confirmation,
    normalize_po,
)


def test_normalize_po_strips_slash_suffix():
    assert normalize_po("ABC123 / L2") == "ABC123"


def test_find_confirmation_ignores_historical_duplicate():
    index = {
        "PO1": [
            {"bstnk": "PO1", "vbeln": "0001", "kunnr": "150", "erdat": "20240101", "erdat_date": __import__("datetime").date(2024, 1, 1)},
            {"bstnk": "PO1", "vbeln": "0002", "kunnr": "150", "erdat": "20260810", "erdat_date": __import__("datetime").date(2026, 8, 10)},
        ]
    }
    hit = find_sap_confirmation(
        customer_order_number="PO1",
        soldto="150",
        sap_sent_at="2026-08-10T08:00:00+00:00",
        salesorders_by_bstnk=index,
    )
    assert hit is not None
    assert hit["vbeln"] == "0002"


def test_find_confirmation_requires_po_match():
    assert find_sap_confirmation(
        customer_order_number="MISSING",
        soldto=None,
        sap_sent_at="2026-08-10T08:00:00+00:00",
        salesorders_by_bstnk={},
    ) is None


def test_mark_sap_confirmed_only_for_sent_orders(tmp_path: Path):
    store = File2EdiStore(str(tmp_path / "t.db"), str(tmp_path / "intake"))
    review = {
        "order": {
            "orderId": "ord-1",
            "uploadId": "upl-1",
            "fileName": "a.pdf",
            "clientName": "Client",
            "customerOrderNumber": "PO-42",
            "documentReference": "PO-42",
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
        "anomalies": [],
    }
    store.save_order_review(review)

    # Not sent yet → must refuse
    assert store.mark_sap_confirmed("ord-1", "0017388864") is False

    store.mark_sftp_delivery("ord-1", True, "/remote/x.tst", sent_by="adv1")
    awaiting = store.list_orders_awaiting_sap_feedback()
    assert len(awaiting) == 1
    assert awaiting[0]["status"] == STATUS_SENT

    assert store.mark_sap_confirmed("ord-1", "0017388864") is True
    loaded = store.load_order_review("ord-1")
    assert loaded["order"]["status"] == STATUS_CONFIRMED
    assert loaded["order"]["sapVbeln"] == "0017388864"
    assert loaded["order"]["sapConfirmedAt"]
    assert store.list_orders_awaiting_sap_feedback() == []

    # Already confirmed → refuse second confirm
    assert store.mark_sap_confirmed("ord-1", "0099999999") is False
