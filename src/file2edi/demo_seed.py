"""Seed demo Rexel order for UI development / empty database."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

DEMO_ORDER_ID = "ord-rexel-026545008"
DEMO_UPLOAD_ID = "upl-rexel-001"
DEMO_FILE_NAME = "Rexel_BOT_CM1_4513_CDE_026545008.PDF"


def _minimal_pdf_bytes(title: str = "BON DE COMMANDE CLIENT - REXEL") -> bytes:
    """Tiny valid PDF for demo preview when no real file is bundled."""
    stream = f"BT /F1 14 Tf 50 750 Td ({title}) Tj ET"
    stream_bytes = stream.encode("latin-1", errors="replace")
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n",
        f"4 0 obj<</Length {len(stream_bytes)}>>stream\n".encode(),
        stream_bytes + b"\nendstream endobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
        b"xref\n0 6\n0000000000 65535 f \n",
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF\n",
    ]
    return b"".join(parts)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_demo_review() -> dict:
    return {
        "order": {
            "orderId": DEMO_ORDER_ID,
            "uploadId": DEMO_UPLOAD_ID,
            "fileName": DEMO_FILE_NAME,
            "clientName": "Rexel",
            "customerOrderNumber": "026545008",
            "documentReference": "15021368",
            "orderDate": None,
            "requestedDeliveryDate": "2026-07-05",
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": 2340.0,
            "globalConfidence": 89,
            "status": "Revue requise",
            "reviewRequired": True,
            "lineCount": 5,
            "createdAt": _now(),
            "updatedAt": _now(),
        },
        "partners": [
            {"partnerId": "p-soldto-1", "orderId": DEMO_ORDER_ID, "partnerFunction": "soldto",
             "partnerCode": "REXEL FRANCE", "partnerName": "REXEL FRANCE",
             "addressLine1": "5 Rue des Entrepreneurs", "postalCode": "69120",
             "city": "Vaulx-en-Velin", "country": "FR", "confidence": 96},
            {"partnerId": "p-shipto-1", "orderId": DEMO_ORDER_ID, "partnerFunction": "shipto",
             "partnerCode": "CHANTIER LYON PART-DIEU", "partnerName": "CHANTIER LYON PART-DIEU",
             "addressLine1": "12 Rue de la République", "postalCode": "69003",
             "city": "Lyon", "country": "FR", "confidence": 96},
            {"partnerId": "p-billto-1", "orderId": DEMO_ORDER_ID, "partnerFunction": "billto",
             "partnerCode": "REXEL FRANCE", "partnerName": "REXEL FRANCE",
             "addressLine1": "5 Rue des Entrepreneurs", "postalCode": "69120",
             "city": "Vaulx-en-Velin", "country": "FR", "confidence": 95},
            {"partnerId": "p-payer-1", "orderId": DEMO_ORDER_ID, "partnerFunction": "payer",
             "partnerCode": "REXEL FRANCE", "partnerName": "REXEL FRANCE",
             "addressLine1": "5 Rue des Entrepreneurs", "postalCode": "69120",
             "city": "Vaulx-en-Velin", "country": "FR", "confidence": 95},
        ],
        "lines": [
            {"lineId": "ln-1", "orderId": DEMO_ORDER_ID, "lineNumber": 1,
             "customerReference": "8716142345678", "boschArticle": "7736501437",
             "designation": "Junkers Cerapur Comfort ZWB 24-1 DE 23",
             "quantity": 2, "unit": "PCE", "unitPrice": 450, "amount": 900,
             "confidence": 95, "status": "OK"},
            {"lineId": "ln-2", "orderId": DEMO_ORDER_ID, "lineNumber": 2,
             "customerReference": "8716142345685", "boschArticle": "7736501444",
             "designation": "Junkers Cerapur Comfort ZWB 28-1 DE 23",
             "quantity": 1, "unit": "PCE", "unitPrice": 520, "amount": 520,
             "confidence": 92, "status": "OK"},
            {"lineId": "ln-3", "orderId": DEMO_ORDER_ID, "lineNumber": 3,
             "customerReference": "BGL 25-550", "boschArticle": "BGL 25-550 ?",
             "designation": "Kit de raccordement", "quantity": 3, "unit": "PCE",
             "unitPrice": 180, "amount": 540, "confidence": 72, "status": "À vérifier",
             "comment": "Article partiellement reconnu"},
            {"lineId": "ln-4", "orderId": DEMO_ORDER_ID, "lineNumber": 4,
             "customerReference": "8716142345701", "boschArticle": "7736501451",
             "designation": "Thermostat d'ambiance CR10", "quantity": 5, "unit": "PCE",
             "unitPrice": 76, "amount": 380, "confidence": 94, "status": "OK"},
            {"lineId": "ln-5", "orderId": DEMO_ORDER_ID, "lineNumber": 5,
             "customerReference": "PORT", "boschArticle": "PORTSFAB",
             "designation": "Frais de port fournisseur", "quantity": 1, "unit": "PCE",
             "unitPrice": 0, "amount": 0, "confidence": 100, "status": "OK"},
        ],
        "anomalies": [
            {"anomalyId": "an-1", "orderId": DEMO_ORDER_ID, "severity": "error",
             "fieldName": "orderDate",
             "message": "La date de commande extraite n'est pas valide",
             "status": "Ouverte", "createdAt": _now()},
            {"anomalyId": "an-2", "orderId": DEMO_ORDER_ID, "lineId": "ln-3",
             "severity": "warning", "fieldName": "boschArticle",
             "message": "Ligne 3 : article Bosch à confirmer (BGL 25-550 ?)",
             "status": "Ouverte", "createdAt": _now()},
            {"anomalyId": "an-3", "orderId": DEMO_ORDER_ID, "severity": "info",
             "fieldName": "deliveryAddress",
             "message": "Adresse de livraison détectée avec forte confiance (96 %)",
             "status": "Corrigée", "createdAt": _now()},
        ],
        "traceability": [
            {"id": "1", "label": "PDF reçu", "status": "completed", "timestamp": _now()},
            {"id": "2", "label": "Extraction OCR", "status": "completed"},
            {"id": "3", "label": "Mapping client", "status": "completed"},
            {"id": "4", "label": "Contrôles métier", "status": "completed"},
            {"id": "5", "label": "Revue manuelle", "status": "current"},
            {"id": "6", "label": "Génération EDIFACT", "status": "pending"},
            {"id": "7", "label": "Export SFTP", "status": "pending"},
        ],
        "edifactReady": True,
    }


def seed_demo_orders(store) -> None:
    """Insert demo Rexel order + sample PDF if not already present."""
    intake_pdf = store.intake_dir / f"{DEMO_UPLOAD_ID}.pdf"
    if not intake_pdf.exists():
        intake_pdf.write_bytes(_minimal_pdf_bytes())

    existing = store.load_order_review(DEMO_ORDER_ID)
    if existing and store.get_pdf_path_for_order(DEMO_ORDER_ID):
        return

    if not existing:
        review = build_demo_review()
    else:
        review = existing

    store.save_upload_with_id(DEMO_UPLOAD_ID, DEMO_FILE_NAME, intake_pdf.stat().st_size, str(intake_pdf))
    review["order"]["pdfPath"] = str(intake_pdf)
    review["order"]["uploadId"] = DEMO_UPLOAD_ID
    store.save_order_review(review)


def refresh_demo_pdf(store) -> None:
    """Re-attach PDF to demo order (e.g. after schema migration)."""
    intake_pdf = store.intake_dir / f"{DEMO_UPLOAD_ID}.pdf"
    if not intake_pdf.exists():
        intake_pdf.write_bytes(_minimal_pdf_bytes())
    store.ensure_order_pdf(DEMO_ORDER_ID)
