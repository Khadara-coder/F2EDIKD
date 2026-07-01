"""Map engine responses ↔ React frontend contract."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_from_engine(result: dict) -> str:
    rej = result.get("rejection") or {}
    decision = (rej.get("decision") or "").upper()
    conf = int(result.get("customer", {}).get("confidence") or 0)
    if decision == "REJECTED":
        return "Rejeté"
    if decision == "REVIEW_REQUIRED" or conf < 90:
        return "Revue requise"
    if result.get("edifact", {}).get("generated"):
        return "Généré"
    return "À revoir"


def engine_to_order_review(order_id: str, upload_id: str, result: dict) -> dict:
    """Build OrderReview JSON from _local_process_and_respond result."""
    order = result.get("order") or {}
    cust = result.get("customer") or {}
    lines_data = result.get("lines") or {}
    rej = result.get("rejection") or {}
    edi = result.get("edifact") or {}
    addr = cust.get("delivery_address") or {}
    det = cust.get("detected_address") or {}

    conf = int(cust.get("confidence") or 0)
    status = _status_from_engine(result)
    order_date = order.get("order_date")
    invalid_date = not order_date or str(order_date).lower() in ("invalid date", "none", "")

    line_items = lines_data.get("lignes") or lines_data.get("items") or []
    parsed_lines = []
    total = 0.0
    for i, ln in enumerate(line_items, start=1):
        if isinstance(ln, dict):
            qty = float(ln.get("Quantite") or ln.get("quantity") or ln.get("qty") or 0)
            price = float(ln.get("Prix unitaire") or ln.get("unit_price") or ln.get("price") or 0)
            amount = float(ln.get("Montant") or ln.get("amount") or qty * price)
            art = str(ln.get("Article Bosch") or ln.get("bosch_article") or ln.get("matnr") or "")
            line_status = "OK"
            line_conf = int(ln.get("Confiance") or ln.get("confidence") or 90)
            if "?" in art or line_conf < 80:
                line_status = "À vérifier"
            parsed_lines.append({
                "lineId": ln.get("line_id") or f"ln-{order_id}-{i}",
                "orderId": order_id,
                "lineNumber": i,
                "customerReference": str(ln.get("Reference client") or ln.get("customer_reference") or ""),
                "boschArticle": art,
                "designation": str(ln.get("Designation") or ln.get("designation") or ""),
                "quantity": qty,
                "unit": str(ln.get("Unite") or ln.get("unit") or "PCE"),
                "unitPrice": price,
                "amount": amount,
                "confidence": line_conf,
                "status": line_status,
                "comment": ln.get("comment"),
            })
            total += amount

    partners = [
        {
            "partnerId": f"p-soldto-{order_id}",
            "orderId": order_id,
            "partnerFunction": "soldto",
            "partnerCode": str(cust.get("soldto") or cust.get("name") or ""),
            "partnerName": str(cust.get("name") or cust.get("soldto") or ""),
            "addressLine1": addr.get("street") or det.get("street") or "",
            "postalCode": addr.get("postal_code") or det.get("postal_code") or "",
            "city": addr.get("city") or det.get("city") or "",
            "country": addr.get("country") or "FR",
            "confidence": int(cust.get("soldto_confidence") or conf),
        },
        {
            "partnerId": f"p-shipto-{order_id}",
            "orderId": order_id,
            "partnerFunction": "shipto",
            "partnerCode": str(cust.get("shipto") or det.get("name") or ""),
            "partnerName": str(det.get("name") or cust.get("shipto") or ""),
            "addressLine1": det.get("street") or addr.get("street") or "",
            "postalCode": det.get("postal_code") or "",
            "city": det.get("city") or "",
            "country": "FR",
            "confidence": int(cust.get("shipto_confidence") or conf),
        },
        {
            "partnerId": f"p-billto-{order_id}",
            "orderId": order_id,
            "partnerFunction": "billto",
            "partnerCode": str(cust.get("soldto") or cust.get("name") or ""),
            "partnerName": str(cust.get("name") or ""),
            "addressLine1": addr.get("street") or "",
            "postalCode": addr.get("postal_code") or "",
            "city": addr.get("city") or "",
            "country": "FR",
            "confidence": conf,
        },
        {
            "partnerId": f"p-payer-{order_id}",
            "orderId": order_id,
            "partnerFunction": "payer",
            "partnerCode": str(cust.get("soldto") or cust.get("name") or ""),
            "partnerName": str(cust.get("name") or ""),
            "addressLine1": addr.get("street") or "",
            "postalCode": addr.get("postal_code") or "",
            "city": addr.get("city") or "",
            "country": "FR",
            "confidence": conf,
        },
    ]

    anomalies = []
    seen_anomaly_ids: set[str] = set()

    def _add_anomaly(entry: dict) -> None:
        aid = entry["anomalyId"]
        if aid in seen_anomaly_ids:
            suffix = 2
            while f"{aid}-{suffix}" in seen_anomaly_ids:
                suffix += 1
            aid = f"{aid}-{suffix}"
            entry = {**entry, "anomalyId": aid}
        seen_anomaly_ids.add(aid)
        anomalies.append(entry)

    for i, d in enumerate(rej.get("details") or []):
        sev = "error" if d.get("severity") == "blocking" else "warning"
        code = d.get("code") or f"rej-{i}"
        _add_anomaly({
            "anomalyId": f"{order_id}-{code}",
            "orderId": order_id,
            "severity": sev,
            "fieldName": d.get("code"),
            "message": d.get("message") or d.get("code") or "",
            "status": "Bloquante" if sev == "error" else "Ouverte",
            "createdAt": _now(),
        })
    if invalid_date:
        _add_anomaly({
            "anomalyId": f"an-date-{order_id}",
            "orderId": order_id,
            "severity": "error",
            "fieldName": "orderDate",
            "message": "La date de commande extraite n'est pas valide",
            "status": "Ouverte",
            "createdAt": _now(),
        })

    trace_steps = [
        {"id": "1", "label": "PDF reçu", "status": "completed", "timestamp": _now()},
        {"id": "2", "label": "Extraction OCR", "status": "completed"},
        {"id": "3", "label": "Mapping client", "status": "completed"},
        {"id": "4", "label": "Contrôles métier", "status": "completed"},
        {"id": "5", "label": "Revue manuelle", "status": "current" if status in ("Revue requise", "À revoir") else "completed"},
        {"id": "6", "label": "Génération EDIFACT", "status": "completed" if edi.get("generated") else "pending"},
        {"id": "7", "label": "Export SFTP", "status": "pending"},
    ]

    return {
        "order": {
            "orderId": order_id,
            "uploadId": upload_id,
            "fileName": result.get("filename") or "",
            "clientName": str(cust.get("name") or "—"),
            "customerOrderNumber": str(order.get("po_number") or ""),
            "documentReference": str(order.get("document_reference") or order.get("po_number") or ""),
            "orderDate": None if invalid_date else order_date,
            "requestedDeliveryDate": order.get("delivery_date"),
            "currency": "EUR",
            "incoterm": "DAP",
            "deliveryMode": "Messagerie",
            "messageType": "ORDERS",
            "vendor": "CM1",
            "totalAmount": total or 0,
            "globalConfidence": conf,
            "status": status,
            "reviewRequired": conf < 90 or status == "Revue requise",
            "lineCount": len(parsed_lines),
            "createdAt": _now(),
            "updatedAt": _now(),
        },
        "partners": partners,
        "lines": parsed_lines,
        "anomalies": anomalies,
        "traceability": trace_steps,
        "edifactReady": bool(edi.get("generated") or edi.get("message")),
        "pdfUrl": None,
        "_engine_result": result,
    }


def engine_to_extraction_preview(upload_id: str, order_id: str, result: dict, file_size: int, page_count: int = 3) -> dict:
    review = engine_to_order_review(order_id, upload_id, result)
    o = review["order"]
    cust = result.get("customer") or {}
    det = cust.get("detected_address") or {}
    steps = [
        {"id": "1", "label": "Extraction du texte", "status": "completed"},
        {"id": "2", "label": "Détection des informations clés", "status": "completed"},
        {"id": "3", "label": "Structuration des données", "status": "completed"},
        {"id": "4", "label": "Validation automatique", "status": "completed"},
        {"id": "5", "label": "Aperçu du résultat", "status": "current"},
        {"id": "6", "label": "Revue manuelle", "status": "pending"},
        {"id": "7", "label": "Génération EDIFACT", "status": "pending"},
    ]
    unique_arts = len({ln["boschArticle"] for ln in review["lines"]})
    return {
        "uploadId": upload_id,
        "orderId": order_id,
        "fileName": o["fileName"],
        "fileSize": file_size,
        "pageCount": page_count,
        "detectedAt": _now(),
        "clientName": o["clientName"],
        "clientCode": o["customerOrderNumber"],
        "deliveryAddress": det.get("raw") or "",
        "customerOrderNumber": o["customerOrderNumber"],
        "orderDate": o["orderDate"],
        "lineCount": o["lineCount"],
        "uniqueArticles": unique_arts,
        "totalAmount": o["totalAmount"],
        "currency": o["currency"],
        "steps": steps,
    }


def dashboard_metrics_from_db(orders: list[dict]) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    today_orders = [o for o in orders if (o.get("created_at") or "")[:10] == today]
    def cnt(status: str) -> int:
        return sum(1 for o in today_orders if o.get("status") == status)
    generated = cnt("Généré")
    review = cnt("Revue requise") + cnt("À revoir") + cnt("À vérifier")
    rejected = cnt("Rejeté")
    partial = cnt("Partiel")
    duplicates = cnt("Doublon")
    sftp_failed = cnt("SFTP échoué")
    total = len(today_orders) or 1
    return {
        "today": len(today_orders),
        "generated": generated,
        "reviewRequired": review,
        "rejected": rejected,
        "partial": partial,
        "duplicates": duplicates,
        "sftpFailed": sftp_failed,
        "total": len(today_orders),
        "statusDistribution": [
            {"label": "Générés", "count": generated, "percent": round(100 * generated / total), "color": "bg-emerald-500"},
            {"label": "Revue requise", "count": review, "percent": round(100 * review / total), "color": "bg-amber-500"},
            {"label": "Partiels", "count": partial, "percent": round(100 * partial / total), "color": "bg-violet-500"},
            {"label": "Rejetés", "count": rejected, "percent": round(100 * rejected / total), "color": "bg-red-500"},
        ],
        "processingFlow": {
            "pdfReceived": len(today_orders),
            "edifactGenerated": generated,
            "manualValidations": review,
            "sftpExports": generated,
        },
    }
