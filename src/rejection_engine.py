"""Rejection engine — runs Esker-compatible checks on extracted order data.

Implements the 9 Esker rejection rules from FILE2EDI app/engines/rejection_engine.py,
adapted to work against both:
  • The FILE2EDI ``structured`` dict format
  • The src.engine_adapter ``order`` dict format

Every returned rejection dict has keys:
    code (str)       — matches a REJECTION_CATALOG key
    message (str)    — English short message for logging/API
    severity (str)   — "blocking" | "warning"
    details (dict)   — optional context

Public API:
    check_rejections(structured, master_data, materials) → list[dict]
    rejection_summary(rejections) → str
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .rejection_catalog import get as catalog_get

log = logging.getLogger("edifact.rejection_engine")

# ── Contract/non-order keywords ───────────────────────────────────────────────
_CONTRACT_KEYWORDS = frozenset([
    "contrat", "contract", "devis", "proforma", "quotation",
    "offre de prix", "appel d'offre", "appel d offre",
])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_rejections(
    structured: dict[str, Any],
    master_data: dict[str, Any] | None = None,
    materials: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run all rejection checks on an extracted document.

    Args:
        structured: Extraction result dict.  Supports both the FILE2EDI
                    ``structured`` shape (keys: document, adresses, lignes_commande)
                    and the legacy engine_adapter ``order`` shape
                    (keys: order_number, buyer_text, lines, raw_text).
        master_data: Optional loaded masterdata dict (customers, salesorders_by_bstnk).
        materials:   Optional dict article_code → material info.

    Returns:
        List of rejection dicts.  Empty list = document is valid.
    """
    rejections: list[dict[str, Any]] = []

    # ── normalise shape ──────────────────────────────────────────────────────
    # FILE2EDI shape
    document   = structured.get("document", {})
    adresses   = structured.get("adresses", {})
    lignes_obj = structured.get("lignes_commande", {})
    validated  = adresses.get("Adresse de livraison validee", {})

    # legacy engine_adapter shape fallback
    if not document and not adresses:
        document = {
            "Numero de commande": structured.get("order_number", ""),
            "raw_text":           structured.get("raw_text", ""),
        }
        validated = {
            "SOLDTO": structured.get("soldto", ""),
            "SHIPTO": structured.get("shipto", ""),
            "Confiance": structured.get("confidence", 0),
            "Statut": structured.get("shipto_status", ""),
        }
        lignes_obj = {"lignes": [
            {
                "code_article": ln.get("customer_article") or ln.get("article_code", ""),
                "quantite":     ln.get("quantity"),
                "prix_unitaire_ht": ln.get("unit_price"),
            }
            for ln in structured.get("lines", [])
        ]}

    # ── run checks ───────────────────────────────────────────────────────────
    rejections.extend(_check_delivery_address(validated))
    rejections.extend(_check_po_number(document))
    rejections.extend(_check_po_duplicate(document, master_data))
    rejections.extend(_check_customer(validated))
    if materials is None and master_data:
        materials = master_data.get("materials_by_id", {})
    rejections.extend(_check_line_items(lignes_obj, materials))
    rejections.extend(_check_document_type(document))

    if rejections:
        codes = [r["code"] for r in rejections]
        log.info("check_rejections: %d rejection(s): %s", len(rejections), codes)

    return rejections


def rejection_summary(rejections: list[dict[str, Any]]) -> str:
    """Return a short human-readable summary of the first blocking rejection."""
    blockers = [r for r in rejections if r.get("severity") == "blocking"]
    if blockers:
        r = blockers[0]
        entry = catalog_get(r["code"])
        return f"[{r['code']}] {entry.get('message_fr', r.get('message', ''))}"
    if rejections:
        r = rejections[0]
        entry = catalog_get(r["code"])
        return f"[{r['code']}] {entry.get('message_fr', r.get('message', ''))}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def _check_delivery_address(validated: dict) -> list[dict]:
    """Rules 1 & 2: delivery address presence and confidence."""
    shipto     = validated.get("SHIPTO", "")
    confidence = validated.get("Confiance", 0) or 0
    statut     = validated.get("Statut", "")

    if not shipto or shipto == "-":
        if "non identifie" in statut.lower() or not statut:
            return [{"code": "NO_DELIVERY_ADDRESS",
                     "message": "No delivery address detected",
                     "severity": "blocking",
                     "details": {"statut": statut}}]
        return [{"code": "DELIVERY_ADDRESS_INVALID",
                 "message": "Delivery address could not be matched to masterdata",
                 "severity": "blocking",
                 "details": {"statut": statut, "confiance": confidence}}]

    if 0 < confidence < 50:
        return [{"code": "DELIVERY_ADDRESS_INVALID",
                 "message": f"Delivery address confidence too low ({confidence}%)",
                 "severity": "blocking",
                 "details": {"shipto": shipto, "confiance": confidence}}]
    return []


def _check_po_number(document: dict) -> list[dict]:
    """Rule 6: PO number presence."""
    po = (document.get("Numero de commande") or document.get("order_number") or "").strip()
    if not po or po == "-":
        return [{"code": "PO_NUMBER_MISSING",
                 "message": "No purchase order number found",
                 "severity": "blocking",
                 "details": {}}]
    return []


def _check_po_duplicate(document: dict, master_data: dict | None) -> list[dict]:
    """Rule 7: PO number already in SAP sales order history."""
    if not master_data:
        return []
    po = (document.get("Numero de commande") or document.get("order_number") or "").strip()
    if not po or po == "-":
        return []
    sales = master_data.get("salesorders_by_bstnk", {})
    po_clean = po.split("/")[0].strip()
    if po_clean in sales:
        entry = sales[po_clean]
        so = (entry[0] if isinstance(entry, list) else entry) if entry else {}
        return [{"code": "PO_NUMBER_DUPLICATE",
                 "message": f"Order {po_clean!r} already in SAP (VBELN={so.get('VBELN','?') if isinstance(so, dict) else '?'})",
                 "severity": "warning",
                 "details": {"po": po_clean,
                              "vbeln": so.get("VBELN", "") if isinstance(so, dict) else "",
                              "kunnr": so.get("KUNNR", "") if isinstance(so, dict) else ""}}]
    return []


def _check_customer(validated: dict) -> list[dict]:
    """Rule 8: SOLDTO presence."""
    soldto = validated.get("SOLDTO", "")
    if not soldto or soldto == "-":
        return [{"code": "CUSTOMER_NOT_DEFINED",
                 "message": "No customer (SOLDTO) reference found in masterdata",
                 "severity": "blocking",
                 "details": {}}]
    return []


def _check_line_items(lignes: dict, materials: dict | None) -> list[dict]:
    """Rules 3–5: line items qty, price, article lookup."""
    rejections: list[dict] = []
    items = lignes.get("lignes", [])

    if not items:
        return [{"code": "NO_LINE_ITEMS",
                 "message": "No order line items found",
                 "severity": "warning",
                 "details": {}}]

    missing_qty, missing_price, not_found = [], [], []
    for item in items:
        num     = item.get("numero_ligne", "?")
        article = (item.get("code_article") or item.get("customer_article") or "").strip()
        qty     = item.get("quantite") or item.get("quantity")
        price   = item.get("prix_unitaire_ht") or item.get("unit_price")

        if qty is None or qty == "":
            missing_qty.append(str(num))
        if price is None or price == "":
            missing_price.append(str(num))
        if materials and article:
            article_key = re.sub(r"^EL[M]?\s*", "", article.upper()).strip()
            if article_key not in materials:
                not_found.append(article)

    if missing_qty:
        rejections.append({"code": "QUANTITY_MISSING",
                            "message": f"Quantity missing on line(s): {', '.join(missing_qty)}",
                            "severity": "blocking",
                            "details": {"lines": missing_qty}})
    if missing_price:
        rejections.append({"code": "PRICE_MISSING",
                           "message": f"Unit price missing on line(s): {', '.join(missing_price)}",
                           "severity": "blocking",
                           "details": {"lines": missing_price}})
    if not_found:
        rejections.append({"code": "ARTICLE_NOT_FOUND",
                           "message": f"Article(s) not in materials master: {not_found}",
                           "severity": "blocking",
                           "details": {"articles": not_found}})
    return rejections


def _check_document_type(document: dict) -> list[dict]:
    """Rule 9: document is not a purchase order."""
    raw = (document.get("raw_text") or document.get("Type document") or "").lower()
    if any(kw in raw for kw in _CONTRACT_KEYWORDS):
        return [{"code": "NOT_AN_ORDER",
                 "message": "Document appears to be a contract/quote/proforma, not a PO",
                 "severity": "blocking",
                 "details": {}}]
    return []
