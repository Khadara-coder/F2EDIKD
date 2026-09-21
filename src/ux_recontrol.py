"""Deterministic rechecks for user choices made in the ADV review UI."""
from __future__ import annotations

from src.rejection_catalog import normalize_code


def can_close_after_recontrol(code: str, review: dict) -> bool:
    """Return whether the current review objectively fixes *code*.

    A false result is intentional for technical and EDI issues: those need a
    dedicated regeneration or delivery check instead of a user click.
    """
    code = normalize_code(code)
    order = review.get("order") or {}
    partners = review.get("partners") or []
    lines = review.get("lines") or []
    soldto = next((p for p in partners if p.get("partnerFunction") == "soldto"), {})
    shipto = next((p for p in partners if p.get("partnerFunction") == "shipto"), {})

    if code == "ORDER_KEY_MISSING":
        return bool(str(order.get("customerOrderNumber") or "").strip())
    if code == "ORDER_DATE_INVALID":
        return bool(order.get("orderDate"))
    if code == "DELIVERY_DATE_INVALID":
        return bool(order.get("requestedDeliveryDate"))
    if code in {"SOLDTO_NOT_FOUND", "SOLDTO_AMBIGUOUS_MATCH"}:
        return bool(str(soldto.get("partnerCode") or "").strip())
    if code in {
        "NO_DELIVERY_ADDRESS", "SHIPTO_CANDIDATES_MISSING", "SHIPTO_NO_STRONG_MATCH",
        "SHIPTO_AMBIGUOUS_MATCH", "SHIPTO_SOLDTO_MISMATCH", "PARTNER_UNRESOLVED",
    }:
        return bool(str(shipto.get("partnerCode") or "").strip())
    if code in {"NO_LINE_ITEMS", "NO_VALID_ARTICLE"}:
        return bool(lines)
    if code in {"QUANTITY_MISSING", "ARTICLE_QUANTITY_INVALID"}:
        for line in lines:
            try:
                if float(line.get("quantity") or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False
    if code in {"ARTICLE_NOT_FOUND", "MATERIAL_STATUS_INVALID"}:
        return any(str(line.get("boschArticle") or "").strip() for line in lines)
    if code in {
        "EDIFACT_MISSING_BGM", "EDIFACT_MISSING_DTM_137", "EDIFACT_MISSING_NAD_BY",
        "EDIFACT_MISSING_NAD_DP", "EDIFACT_MISSING_LIN",
        "EDIFACT_LINE_INTEGRITY_MISMATCH", "EDIFACT_NAD_DP_MISMATCH",
    }:
        return bool(review.get("edifactReady"))
    if code in {"DELIVERY_SFTP_FAILED", "DELIVERY_EMAIL_FAILED"}:
        return bool(order.get("sapSentAt"))
    return False