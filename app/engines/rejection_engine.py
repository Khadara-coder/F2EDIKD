"""Rejection engine for LocateAnything.

Implements the 9 Esker rejection rules:
1. DELIVERY_ADDRESS_INVALID - Delivery address not found in masterdata
2. NO_DELIVERY_ADDRESS - No delivery address detected
3. ARTICLE_NOT_FOUND - Article number not in Materials masterdata
4. QUANTITY_MISSING - Quantity missing on a line item
5. PRICE_MISSING - Unit price missing on a line item
6. PO_NUMBER_MISSING - No PO/order number found
7. PO_NUMBER_DUPLICATE - PO number already exists in salesorders
8. CUSTOMER_NOT_DEFINED - Customer (SOLDTO) not found in masterdata
9. NOT_AN_ORDER - Document is not a purchase order

Each rule returns:
- code: rejection code (str)
- message: human-readable message for rejection email
- severity: "blocking" (= reject) or "warning" (= flag for review)
- details: additional context
"""

import logging
import re
from typing import Optional

from src.rejection_catalog import format_rejection_message

logger = logging.getLogger(__name__)


def check_rejections(
    structured: dict,
    master_data: dict = None,
    materials: dict = None,
) -> list[dict]:
    """Run all rejection checks on an extracted document.

    Args:
        structured: The full structured extraction result (from extraction.py)
        master_data: Loaded masterdata (customers, partners, salesorders)
        materials: dict of article_number -> material info (from 10564_Materials.csv)

    Returns:
        List of rejection dicts, each with: code, message, severity, details
        Empty list = document is valid.
    """
    rejections = []

    document = structured.get("document", {})
    adresses = structured.get("adresses", {})
    lignes = structured.get("lignes_commande", {})
    validated = adresses.get("Adresse de livraison validee", {})

    # --- Rule 1 & 2: Delivery address ---
    rejections.extend(_check_delivery_address(validated))

    # --- Rule 6: PO number ---
    rejections.extend(_check_po_number(document))

    # --- Rule 7: PO duplicate ---
    rejections.extend(_check_po_duplicate(document, master_data))

    # --- Rule 8: Customer not defined ---
    rejections.extend(_check_customer(validated))

    # --- Rules 3, 4, 5: Line items ---
    # Extract materials lookup from master_data if not passed explicitly
    if materials is None and master_data:
        materials = master_data.get("materials_by_id", {})
    rejections.extend(_check_line_items(lignes, materials))

    # --- Rule 9: Not an order ---
    rejections.extend(_check_document_type(document))

    return rejections


# -------------------------------------------------------------------------
# Individual rejection checks
# -------------------------------------------------------------------------

def _check_delivery_address(validated: dict) -> list[dict]:
    """Rules 1 & 2: Check delivery address validity."""
    rejections = []
    confidence = validated.get("Confiance", 0)
    shipto = validated.get("SHIPTO", "")
    soldto = validated.get("SOLDTO", "")

    if not shipto or shipto == "-":
        # SHIPTO vide peut être légitime si SHIPTO = SOLDTO (livraison = facturation)
        if soldto and validated.get("Livraison egale facturation SOLDTO") == "oui":
            return []  # adresse valide, SOLDTO utilisé comme SHIPTO

        statut = validated.get("Statut", "")
        if "non identifie" in statut.lower() or not statut:
            rejections.append({
                "code": "NO_DELIVERY_ADDRESS",
                "message": format_rejection_message("NO_DELIVERY_ADDRESS"),
                "severity": "blocking",
                "details": {"statut": statut},
            })
        else:
            rejections.append({
                "code": "DELIVERY_ADDRESS_INVALID",
                "message": format_rejection_message(
                    "DELIVERY_ADDRESS_INVALID",
                    {"statut": statut, "confiance": confidence},
                ),
                "severity": "blocking",
                "details": {"statut": statut, "confiance": confidence},
            })
    elif confidence > 0 and confidence < 50:
        rejections.append({
            "code": "DELIVERY_ADDRESS_INVALID",
            "message": format_rejection_message(
                "DELIVERY_ADDRESS_INVALID",
                {"shipto": shipto, "confiance": confidence},
            ),
            "severity": "blocking",
            "details": {"shipto": shipto, "confiance": confidence},
        })

    return rejections


def _check_po_number(document: dict) -> list[dict]:
    """Rule 6: Check PO number presence."""
    po = document.get("Numero de commande", "")
    if not po or po == "-" or po.strip() == "":
        return [{
            "code": "PO_NUMBER_MISSING",
            "message": format_rejection_message("ORDER_KEY_MISSING"),
            "severity": "blocking",
            "details": {},
        }]
    return []


def _check_po_duplicate(document: dict, master_data: dict = None) -> list[dict]:
    """Rule 7: Check PO number duplicate in salesorders."""
    if not master_data:
        return []

    po = document.get("Numero de commande", "")
    if not po or po == "-":
        return []

    salesorders_by_bstnk = master_data.get("salesorders_by_bstnk", {})
    if not salesorders_by_bstnk:
        return []

    # Normalize PO: strip, take first part before /
    po_clean = po.strip().split("/")[0].strip()

    if po_clean in salesorders_by_bstnk:
        so_entry = salesorders_by_bstnk[po_clean]
        # salesorders_by_bstnk may map to a list or a dict
        if isinstance(so_entry, list):
            so = so_entry[0] if so_entry else {}
        else:
            so = so_entry if isinstance(so_entry, dict) else {}
        return [{
            "code": "PO_NUMBER_DUPLICATE",
            "message": format_rejection_message(
                "PO_NUMBER_DUPLICATE",
                {
                    "po_number": po_clean,
                    "existing_vbeln": so.get("VBELN", "") if isinstance(so, dict) else "",
                    "existing_kunnr": so.get("KUNNR", "") if isinstance(so, dict) else "",
                },
            ),
            "severity": "warning",
            "details": {
                "po_number": po_clean,
                "existing_vbeln": so.get("VBELN", "") if isinstance(so, dict) else "",
                "existing_date": so.get("ERDAT", "") if isinstance(so, dict) else "",
                "existing_kunnr": so.get("KUNNR", "") if isinstance(so, dict) else "",
            },
        }]
    return []


def _check_customer(validated: dict) -> list[dict]:
    """Rule 8: Check customer (SOLDTO) is defined."""
    soldto = validated.get("SOLDTO", "")
    if not soldto or soldto == "-":
        return [{
            "code": "CUSTOMER_NOT_DEFINED",
            "message": format_rejection_message("CUSTOMER_NOT_DEFINED"),
            "severity": "blocking",
            "details": {},
        }]
    return []


def _check_line_items(lignes: dict, materials: dict = None) -> list[dict]:
    """Rules 3, 4, 5: Check line item validity."""
    rejections = []
    items = lignes.get("lignes", [])

    if not items:
        # No line items at all - might be acceptable for some documents
        # but flag as warning
        rejections.append({
            "code": "NO_LINE_ITEMS",
            "message": format_rejection_message("NO_LINE_ITEMS"),
            "severity": "warning",
            "details": {},
        })
        return rejections

    lines_without_qty = []
    lines_without_price = []
    lines_article_not_found = []

    for item in items:
        line_num = item.get("numero_ligne", "?")
        article = item.get("code_article", "")
        qty = item.get("quantite")
        price = item.get("prix_unitaire_ht")

        # Rule 4: Quantity missing
        if qty is None or qty == 0:
            lines_without_qty.append(line_num)

        # Rule 5: Price missing
        if price is None:
            lines_without_price.append(line_num)

        # Rule 3: Article not in masterdata
        if materials and article:
            # Normalize: remove spaces, dashes, leading zeros
            article_norm = re.sub(r"[\s\-]", "", article)
            # Try multiple formats: raw, without leading zeros, with leading zeros
            found = (
                article_norm in materials
                or article_norm.lstrip("0") in materials
                or article_norm.zfill(10) in materials
                or article_norm.zfill(18) in materials
            )
            if not found:
                lines_article_not_found.append({
                    "line": line_num,
                    "article": article,
                    "article_norm": article_norm,
                })

    if lines_without_qty:
        rejections.append({
            "code": "QUANTITY_MISSING",
            "message": format_rejection_message("QUANTITY_MISSING", {"lines": lines_without_qty}),
            "severity": "blocking",
            "details": {"lines": lines_without_qty},
        })

    if lines_without_price:
        rejections.append({
            "code": "PRICE_MISSING",
            "message": format_rejection_message("PRICE_MISSING", {"lines": lines_without_price}),
            "severity": "blocking",
            "details": {"lines": lines_without_price},
        })

    if lines_article_not_found:
        rejections.append({
            "code": "ARTICLE_NOT_FOUND",
            "message": format_rejection_message(
                "ARTICLE_NOT_FOUND",
                {"articles": lines_article_not_found},
            ),
            "severity": "warning",
            "details": {"articles": lines_article_not_found, "action": "saisir_et_informer"},
        })

    return rejections


def _check_document_type(document: dict) -> list[dict]:
    """Rule 9: Check if document is actually a purchase order."""
    doc_type = (document.get("Type") or "").lower()

    # If the extraction engine detected it's not an order
    if doc_type and doc_type not in ("commande", "order", "purchase_order", "bon de commande", ""):
        if "avoir" in doc_type or "credit" in doc_type:
            return [{
                "code": "NOT_AN_ORDER",
                "message": format_rejection_message(
                    "NOT_AN_ORDER",
                    {"detected_type": "avoir / note de crédit"},
                ),
                "severity": "blocking",
                "details": {"detected_type": doc_type},
            }]
        if "modif" in doc_type or "change" in doc_type:
            return [{
                "code": "ORDER_CHANGE",
                "message": format_rejection_message(
                    "ORDER_CHANGE",
                    {"detected_type": doc_type},
                ),
                "severity": "blocking",
                "details": {"detected_type": doc_type},
            }]

    return []


# -------------------------------------------------------------------------
# Summary helpers
# -------------------------------------------------------------------------

def rejection_summary(rejections: list[dict]) -> dict:
    """Summarize rejections into a decision."""
    blocking = [r for r in rejections if r["severity"] == "blocking"]
    warnings = [r for r in rejections if r["severity"] == "warning"]

    if blocking:
        decision = "REJECTED"
        reason = blocking[0]["code"]  # Primary rejection reason
    elif warnings:
        decision = "REVIEW"
        reason = warnings[0]["code"]
    else:
        decision = "ACCEPTED"
        reason = None

    return {
        "decision": decision,
        "primary_reason": reason,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "rejections": rejections,
    }
