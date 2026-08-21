"""Strict unique ship-to matching + review rematch."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engines.shipto_scoring import match_shipto_strict, score_shipto_candidates
from src.file2edi.store import File2EdiStore


ISERBA_MD = {
    "partners_by_soldto": {
        "15015760": [
            {
                "id": "15015760",
                "name": "ISERBA",
                "street": "HQ",
                "city": "LYON",
                "postal": "69000",
                "country": "FR",
            },
            {
                "id": "15018599",
                "name": ".ISERBA (OUL)",
                "street": "8-10 AVENUE EUGENE HENAFF",
                "city": "VAULX-EN-VELIN",
                "postal": "69120",
                "country": "FR",
            },
            {
                "id": "15018600",
                "name": ".ISERBA (STQ)",
                "street": "1 RUE AUTRE",
                "city": "SAINT-QUENTIN",
                "postal": "02100",
                "country": "FR",
            },
        ],
    },
    "customers_by_id": {
        "15015760": {"id": "15015760", "postal": "69000", "name": "ISERBA"},
    },
    "salesorders_by_kunnr": {},
}


def test_match_shipto_strict_iserba_postal_street():
    hit = match_shipto_strict(
        "15015760",
        ISERBA_MD,
        street="8-10 AVENUE EUGENE HENAFF",
        postal="69120",
    )
    assert hit is not None
    assert hit["shipto_id"] == "15018599"
    assert hit["reason"] == "EXACT_UNIQUE_ADDRESS"


def test_match_shipto_strict_iserba_agency_and_postal():
    hit = match_shipto_strict(
        "15015760",
        ISERBA_MD,
        name=".ISERBA (OUL)",
        postal="69120",
    )
    assert hit is not None
    assert hit["shipto_id"] == "15018599"
    assert "AGENCY" in hit["reason"] or "NAME" in hit["reason"]


def test_match_shipto_strict_ambiguous_name_without_postal():
    hit = match_shipto_strict(
        "15015760",
        ISERBA_MD,
        name="ISERBA",
    )
    assert hit is None


def test_match_shipto_strict_empty_fields():
    assert match_shipto_strict("15015760", ISERBA_MD) is None


def test_score_shipto_candidates_accepts_exact_unique_from_text():
    text = """
    Adresse de livraison
    .ISERBA (OUL)
    8-10 AVENUE EUGENE HENAFF
    69120 VAULX-EN-VELIN
    """
    result = score_shipto_candidates(text, "15015760", ISERBA_MD, soldto_confidence=90)
    assert result.decision == "ACCEPTED"
    assert result.shipto_confidence >= 90
    assert result.best_candidate is not None
    assert result.best_candidate.shipto_id == "15018599"


def _review_with_empty_shipto(order_id: str) -> dict:
    return {
        "order": {
            "orderId": order_id,
            "uploadId": f"upl-{order_id}",
            "fileName": f"{order_id}.pdf",
            "clientName": ".ISERBA (OUL)",
            "customerOrderNumber": "PO-ISERBA",
            "documentReference": "PO-ISERBA",
            "orderDate": "2026-08-05",
            "requestedDeliveryDate": "2026-08-10",
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
            "rejectionMessage": "DELIVERY_ADDRESS_INVALID",
            "createdAt": "2026-08-21T10:00:00+00:00",
            "updatedAt": "2026-08-21T10:00:00+00:00",
        },
        "partners": [
            {
                "partnerId": f"p-soldto-{order_id}",
                "orderId": order_id,
                "partnerFunction": "soldto",
                "partnerCode": "15015760",
                "partnerName": "ISERBA",
                "addressLine1": "",
                "postalCode": "",
                "city": "",
                "country": "FR",
                "confidence": 90,
            },
            {
                "partnerId": f"p-shipto-{order_id}",
                "orderId": order_id,
                "partnerFunction": "shipto",
                "partnerCode": "",
                "partnerName": ".ISERBA (OUL)",
                "addressLine1": "",
                "postalCode": "",
                "city": "",
                "country": "FR",
                "confidence": 0,
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
                "requestedDate": "2026-08-10",
                "confidence": 100,
                "status": "OK",
                "manuallyEdited": False,
            }
        ],
        "anomalies": [
            {
                "anomalyId": f"{order_id}-DELIVERY_ADDRESS_INVALID",
                "orderId": order_id,
                "severity": "error",
                "fieldName": "DELIVERY_ADDRESS_INVALID",
                "message": "Adresse de livraison invalide",
                "status": "Bloquante",
                "createdAt": "2026-08-21T10:00:00+00:00",
            }
        ],
    }


def test_update_partner_address_rematch_fills_code_and_closes_anomaly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    order_id = "ord-iserba"
    store.save_order_review(_review_with_empty_shipto(order_id))
    monkeypatch.setattr(
        "app.masterdata.get_master_data",
        lambda: ISERBA_MD,
    )

    review = store.update_partner(
        f"p-shipto-{order_id}",
        {
            "addressLine1": "8-10 AVENUE EUGENE HENAFF",
            "postalCode": "69120",
            "city": "VAULX-EN-VELIN",
            "editSource": "manual",
        },
    )
    assert review is not None
    shipto = next(p for p in review["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == "15018599"
    anomaly = next(
        a for a in review["anomalies"] if a["fieldName"] == "DELIVERY_ADDRESS_INVALID"
    )
    assert anomaly["status"] == "Corrigée"


def test_update_partner_ambiguous_address_keeps_empty_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    order_id = "ord-ambig"
    store.save_order_review(_review_with_empty_shipto(order_id))
    monkeypatch.setattr("app.masterdata.get_master_data", lambda: ISERBA_MD)

    review = store.update_partner(
        f"p-shipto-{order_id}",
        {"city": "LYON", "editSource": "manual"},
    )
    shipto = next(p for p in review["partners"] if p["partnerFunction"] == "shipto")
    assert not (shipto.get("partnerCode") or "").strip()
    anomaly = next(
        a for a in review["anomalies"] if a["fieldName"] == "DELIVERY_ADDRESS_INVALID"
    )
    assert anomaly["status"] == "Bloquante"


def test_update_partner_manual_valid_code_closes_anomaly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = File2EdiStore(str(tmp_path / "f2e.db"), str(tmp_path / "intake"))
    order_id = "ord-manual-code"
    store.save_order_review(_review_with_empty_shipto(order_id))
    monkeypatch.setattr("app.masterdata.get_master_data", lambda: ISERBA_MD)

    review = store.update_partner(
        f"p-shipto-{order_id}",
        {"partnerCode": "15018599", "editSource": "manual"},
    )
    shipto = next(p for p in review["partners"] if p["partnerFunction"] == "shipto")
    assert shipto["partnerCode"] == "15018599"
    anomaly = next(
        a for a in review["anomalies"] if a["fieldName"] == "DELIVERY_ADDRESS_INVALID"
    )
    assert anomaly["status"] == "Corrigée"
