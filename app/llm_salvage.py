"""LLM salvage extraction when the deterministic PDF pipeline raises an exception.

Strategy:
1. Recover text (partial buffer, OCR retry, native retry)
2. LLM extract header + order lines + sold-to/ship-to resolution
3. Auto-fill partners only when masterdata validates codes AND match score >= 95
4. Return a reviewable API response (never hard-reject if salvage produced lines)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("edifact.llm_salvage")

PARTNER_AUTO_FILL_MIN_SCORE = 95
MIN_SALVAGE_TEXT_LEN = 30


def recover_pdf_text(payload: bytes, partial_text: str = "") -> tuple[str, str]:
    """Best-effort text recovery. Returns (text, method)."""
    cleaned = (partial_text or "").strip()
    if len(cleaned) >= MIN_SALVAGE_TEXT_LEN:
        return cleaned, "partial"

    try:
        from app.pdf_reader import pdf_pages_to_text
        from app.ocr import ocr_layout_callback
        import fitz

        doc = fitz.open(stream=payload, filetype="pdf")
        page_count = doc.page_count
        doc.close()
        if page_count <= 0:
            return "", "none"

        selection = ",".join(str(i) for i in range(1, min(page_count + 1, 21)))
        pages = pdf_pages_to_text(payload, selection, ocr_with_layout=ocr_layout_callback())
        text = "\n".join(p["text"] for p in pages if p.get("text")).strip()
        if len(text) >= MIN_SALVAGE_TEXT_LEN:
            return text, "ocr_retry"
    except Exception as exc:
        logger.debug("salvage OCR retry failed: %s", exc)

    try:
        from app.pdf_reader import pdf_pages_to_text

        pages = pdf_pages_to_text(payload, "1-20", ocr_with_layout=None)
        text = "\n".join(p["text"] for p in pages if p.get("text")).strip()
        if len(text) >= MIN_SALVAGE_TEXT_LEN:
            return text, "native_retry"
    except Exception as exc:
        logger.debug("salvage native retry failed: %s", exc)

    return "", "none"


def _validate_partners_in_masterdata(soldto: str, shipto: str, master_data: dict) -> dict[str, bool]:
    soldto = str(soldto or "").strip()
    shipto = str(shipto or "").strip()
    customers = master_data.get("customers_by_id") or {}
    partners_by_soldto = master_data.get("partners_by_soldto") or {}
    soldto_ok = bool(soldto and soldto in customers)
    shipto_ok = False
    if soldto_ok and shipto:
        if shipto == soldto:
            shipto_ok = True
        else:
            shipto_ok = any(str(p.get("id") or "") == shipto for p in partners_by_soldto.get(soldto, []))
    return {"soldto_valid": soldto_ok, "shipto_valid": shipto_ok, "both_valid": soldto_ok and shipto_ok}


def _partner_address_from_masterdata(soldto: str, shipto: str, master_data: dict) -> tuple[dict, dict]:
    customers = master_data.get("customers_by_id") or {}
    partners_by_soldto = master_data.get("partners_by_soldto") or {}
    soldto_row = customers.get(soldto) or {}
    shipto_row = soldto_row
    if shipto and shipto != soldto:
        for partner in partners_by_soldto.get(soldto, []):
            if str(partner.get("id") or "") == shipto:
                shipto_row = partner
                break
    delivery = {
        "street": str(shipto_row.get("street") or ""),
        "postal_code": str(shipto_row.get("postal") or ""),
        "city": str(shipto_row.get("city") or ""),
        "country": str(shipto_row.get("country") or "FR"),
    }
    detected = {
        "name": str(shipto_row.get("name") or soldto_row.get("name") or ""),
        "street": delivery["street"],
        "postal_code": delivery["postal_code"],
        "city": delivery["city"],
        "raw": ", ".join(filter(None, [delivery["street"], delivery["postal_code"], delivery["city"]])),
        "statut": "LLM_SALVAGE",
    }
    return delivery, detected


def salvage_with_llm(
    payload: bytes,
    filename: str,
    *,
    partial_text: str = "",
    original_error: str = "",
    elapsed_s: float = 0.0,
    pdf_hash: str = "",
) -> dict[str, Any] | None:
    """Attempt LLM salvage. Returns API response dict or None if unsalvageable."""
    text, recovery_method = recover_pdf_text(payload, partial_text=partial_text)
    if not text:
        return None

    try:
        from app.engines.llm_resolver import llm_extract, llm_resolve
        from app.engines.llm_orderlines import llm_extract_orderlines
        from app.masterdata import get_master_data
    except Exception as exc:
        logger.warning("salvage imports failed: %s", exc)
        return None

    master_data = get_master_data()
    llm_header = None
    try:
        llm_header = llm_extract(text)
    except Exception as exc:
        logger.debug("salvage llm_extract failed: %s", exc)

    order_lines: list[dict] = []
    try:
        order_lines = llm_extract_orderlines(text) or []
    except Exception as exc:
        logger.debug("salvage llm_extract_orderlines failed: %s", exc)

    if not order_lines and not (llm_header or {}).get("numero_commande"):
        return None

    soldto = ""
    shipto = ""
    partner_confidence = 0
    partner_score = 0
    partner_path = ""
    partners_auto_filled = False

    try:
        llm_partner = llm_resolve(text, master_data, pre_extracted=llm_header)
        if llm_partner.get("resolved"):
            candidate_soldto = str(llm_partner.get("soldto") or "").strip()
            candidate_shipto = str(llm_partner.get("shipto") or "").strip()
            partner_score = int(llm_partner.get("score") or 0)
            partner_confidence = int(llm_partner.get("confidence") or 0)
            partner_path = str(llm_partner.get("path") or "")
            validation = _validate_partners_in_masterdata(candidate_soldto, candidate_shipto, master_data)
            if validation["both_valid"] and partner_score >= PARTNER_AUTO_FILL_MIN_SCORE:
                soldto = candidate_soldto
                shipto = candidate_shipto
                partners_auto_filled = True
    except Exception as exc:
        logger.debug("salvage llm_resolve failed: %s", exc)

    po_number = str((llm_header or {}).get("numero_commande") or "").strip() or None
    order_date = (llm_header or {}).get("date_commande")
    delivery_date = (llm_header or {}).get("date_livraison_souhaitee")

    delivery_address = {"street": "", "postal_code": "", "city": "", "country": "FR"}
    detected_address = {"name": "", "street": "", "postal_code": "", "city": "", "raw": "", "statut": "LLM_SALVAGE"}
    customer_name = str((llm_header or {}).get("nom_client") or "").strip()

    if partners_auto_filled:
        delivery_address, detected_address = _partner_address_from_masterdata(soldto, shipto, master_data)
        customer_name = str((master_data.get("customers_by_id") or {}).get(soldto, {}).get("name") or customer_name)
    elif llm_header:
        addr = (llm_header.get("adresse_livraison") or {}) if isinstance(llm_header.get("adresse_livraison"), dict) else {}
        delivery_address = {
            "street": str(addr.get("rue") or ""),
            "postal_code": str(addr.get("code_postal") or ""),
            "city": str(addr.get("ville") or ""),
            "country": "FR",
        }
        detected_address = {
            "name": customer_name,
            "street": delivery_address["street"],
            "postal_code": delivery_address["postal_code"],
            "city": delivery_address["city"],
            "raw": ", ".join(filter(None, [customer_name, delivery_address["street"], delivery_address["postal_code"], delivery_address["city"]])),
            "statut": "LLM_SALVAGE_DETECTED",
        }

    line_confidence = 75 if order_lines else 0
    customer_conf = partner_confidence if partners_auto_filled else (50 if customer_name else 0)
    global_conf = min(customer_conf or 50, line_confidence or 50) if order_lines else (customer_conf or 0)

    warnings: list[dict] = [{
        "code": "EXTRACTION_LLM_SALVAGE",
        "message": "Extraction deterministe en echec — donnees recuperees par fallback IA (revue obligatoire).",
        "severity": "warning",
        "details": {
            "original_error": original_error,
            "recovery_method": recovery_method,
            "partners_auto_filled": partners_auto_filled,
            "partner_score": partner_score,
            "partner_path": partner_path,
        },
    }]
    if not partners_auto_filled and (soldto or shipto or customer_name):
        warnings.append({
            "code": "PARTNER_UNRESOLVED",
            "message": "Sold-to / Ship-to non valides automatiquement — saisie manuelle requise.",
            "severity": "warning",
            "details": {},
        })

    return {
        "status": "OK",
        "filename": filename,
        "pdf_hash": pdf_hash,
        "cached": False,
        "processing_time_s": round(elapsed_s, 1),
        "salvage": True,
        "salvage_source": "llm",
        "salvage_recovery_method": recovery_method,
        "order": {
            "po_number": po_number,
            "order_date": order_date,
            "delivery_date": delivery_date,
        },
        "customer": {
            "soldto": soldto or None,
            "shipto": shipto or None,
            "name": customer_name or "-",
            "confidence": customer_conf,
            "soldto_confidence": partner_confidence if partners_auto_filled else 0,
            "shipto_confidence": partner_confidence if partners_auto_filled else 0,
            "disambiguation": f"LLM_SALVAGE:{partner_path}" if partner_path else "LLM_SALVAGE",
            "delivery_address": delivery_address,
            "detected_address": detected_address,
        },
        "lines": {
            "count": len(order_lines),
            "items": order_lines,
            "confidence": line_confidence,
        },
        "confidence": global_conf,
        "rejection": {
            "decision": "REVIEW_REQUIRED",
            "reason": "EXTRACTION_LLM_SALVAGE",
            "blocking_count": 0,
            "warning_count": len(warnings),
            "details": warnings,
        },
        "edifact": {"generated": False, "message": None, "warnings": [], "errors": None},
        "error": original_error or None,
    }
