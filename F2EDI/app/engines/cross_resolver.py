"""Cross-resolver: combine signals from all engines to identify SOLDTO/SHIPTO.

When DeliveryAddressEngine + ShipToMatchingEngine fail to match (Confiance=0),
this module tries alternate resolution paths:
  Path A: TVA/SIREN -> customers_by_vat -> SOLDTO -> Partners -> SHIPTO
  Path B: Client number in text -> customers_by_id -> SOLDTO -> Partners -> SHIPTO
  Path C: Order number -> salesorders_by_bstnk -> KUNNR -> Partners -> SHIPTO

Masterdata field names: id, name, street, city, postal, country, vat
"""
from __future__ import annotations

import re
from typing import Any

from app.masterdata import get_master_data
from app.text_utils import fold_text, norm_postal


def _score_shipto_vs_text(shipto: dict, text: str, detected_address: dict) -> int:
    """Score how well a SHIPTO candidate matches the document text/address."""
    score = 0
    folded = fold_text(text)
    shipto_postal = norm_postal(shipto.get("postal", ""))
    shipto_city = fold_text(shipto.get("city", ""))
    shipto_street = fold_text(shipto.get("street", ""))
    shipto_name = fold_text(shipto.get("name", ""))

    det_postal = norm_postal(detected_address.get("Code postal", ""))
    det_city = fold_text(detected_address.get("Ville", ""))

    # Postal code match
    if shipto_postal and shipto_postal in folded:
        score += 40
        if det_postal and det_postal == shipto_postal:
            score += 20

    # City match
    if shipto_city and len(shipto_city) > 3 and shipto_city in folded:
        score += 30
        if det_city and det_city == shipto_city:
            score += 15

    # Street match
    if shipto_street and len(shipto_street) > 5 and shipto_street in folded:
        score += 25

    # Name match
    if shipto_name and len(shipto_name) > 4 and shipto_name in folded:
        score += 20

    return score


def _resolve_via_vat(tax_result: dict, master_data: dict) -> list[str]:
    """Path A: TVA/SIREN -> SOLDTO via customers_by_vat index."""
    soldtos = []
    customers_by_vat = master_data.get("customers_by_vat", {})
    customers = master_data.get("customers", [])

    vat_numbers = tax_result.get("vat_numbers", [])
    expected_vats = tax_result.get("expected_vat_from_siren", [])
    all_vats = vat_numbers + expected_vats

    for vat in all_vats:
        vat_normalized = re.sub(r"[^A-Z0-9]", "", vat.upper())
        # Try index lookup (value is a list of customers)
        customer_list = customers_by_vat.get(vat_normalized)
        if customer_list:
            for customer in customer_list:
                soldto = customer.get("id")
                if soldto and soldto not in soldtos:
                    soldtos.append(soldto)
            if soldtos:
                continue
        # Fallback: iterate
        for c in customers:
            cust_vat = re.sub(r"[^A-Z0-9]", "", (c.get("vat") or "").upper())
            if cust_vat and cust_vat == vat_normalized:
                soldto = c.get("id")
                if soldto and soldto not in soldtos:
                    soldtos.append(soldto)
                break

    return soldtos


def _resolve_via_client_number(text: str, master_data: dict) -> list[str]:
    """Path B: Client number in text matching a known SOLDTO."""
    soldtos = []
    customers_by_id = master_data.get("customers_by_id", {})
    known_soldtos = set(customers_by_id.keys()) if customers_by_id else {
        c.get("id") for c in master_data.get("customers", []) if c.get("id")
    }

    # Pattern 1: "N Client" label then number on same or next line
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"N.{0,3}\s*Client", line, flags=re.IGNORECASE):
            match = re.search(r"(\d{7,10})", line)
            if match:
                normalized = str(int(match.group(1)))
                if normalized in known_soldtos and normalized not in soldtos:
                    soldtos.append(normalized)
            # Check next 2 lines
            for j in range(i + 1, min(i + 3, len(lines))):
                for m in re.finditer(r"(\d{7,10})", lines[j]):
                    normalized = str(int(m.group(1)))
                    if normalized in known_soldtos and normalized not in soldtos:
                        soldtos.append(normalized)
            if soldtos:
                break

    # Pattern 2: standalone 8-digit numbers starting with 1 (Bosch IDs)
    if not soldtos:
        for m in re.finditer(r"\b(1[0-9]{7})\b", text):
            normalized = str(int(m.group(1)))
            if normalized in known_soldtos and normalized not in soldtos:
                soldtos.append(normalized)

    return soldtos


def _resolve_via_order(order_result: dict, master_data: dict) -> list[str]:
    """Path C: Order number -> BSTNK -> KUNNR."""
    soldtos = []
    candidates = order_result.get("candidates", [])
    for candidate in candidates:
        validation = candidate.get("validation", {})
        kunnr = validation.get("KUNNR")
        if kunnr and kunnr not in soldtos:
            soldtos.append(kunnr)
    return soldtos


def _get_shiptos_for_soldto(soldto: str, master_data: dict) -> list[dict]:
    """Get all SHIPTO entries for a given SOLDTO."""
    partners_by_soldto = master_data.get("partners_by_soldto", {})
    partners = partners_by_soldto.get(soldto, [])
    # Fallback: if no partners, use the customer itself as SHIPTO
    if not partners:
        customers_by_id = master_data.get("customers_by_id", {})
        customer = customers_by_id.get(soldto)
        if customer:
            partners = [customer]
    return partners


def _resolve_via_name(text: str, master_data: dict) -> list[str]:
    """Path D: Customer name found in PDF text -> SOLDTO candidates.
    
    Uses only the document content (not filename).
    Searches for known customer names in the OCR/extracted text.
    """
    soldtos = []
    folded = fold_text(text)
    if len(folded) < 20:
        return soldtos

    customers = master_data.get("customers", [])
    # Score matches: longer name = more specific = better
    scored_matches = []
    for c in customers:
        name = c.get("name", "")
        if not name or len(name) < 6:
            continue
        name_folded = fold_text(name)
        # Skip generic / internal names (appear in Bosch sender address)
        if name_folded in ("france", "paris", "bosch", "bosch thermotechnologie",
                           "elm leblanc", "elm lelblanc", "leblanc",
                           "e.l.m. leblanc", "elm leblanc s.a.s."):
            continue
        # Skip names that are substrings of Bosch entity names
        if "leblanc" in name_folded and len(name_folded) < 10:
            continue
        # Check if customer name appears in document text
        if name_folded in folded:
            scored_matches.append((len(name_folded), c.get("id"), name))

    # Sort by name length descending (prefer most specific match)
    scored_matches.sort(reverse=True)
    for _, soldto, _ in scored_matches[:5]:
        if soldto and soldto not in soldtos:
            soldtos.append(soldto)

    return soldtos


def cross_resolve(
    *,
    text: str,
    tax_result: dict,
    order_result: dict,
    detected_address: dict,
    validated_result: dict,
) -> dict[str, Any]:
    """Try to resolve SHIPTO by crossing signals when primary matching fails."""
    master_data = get_master_data()
    if not master_data.get("loaded"):
        return {"resolved": False, "reason": "masterdata_unavailable"}

    paths_tried = []
    soldto = None
    path_used = None

    # Path B FIRST: Client number in text (most specific signal)
    client_soldtos = _resolve_via_client_number(text, master_data)
    paths_tried.append(f"client_nr:{len(client_soldtos)}")
    if client_soldtos:
        soldto = client_soldtos[0]
        path_used = "client_number"

    # Path C: Order number -> BSTNK -> KUNNR
    if not soldto:
        order_soldtos = _resolve_via_order(order_result, master_data)
        paths_tried.append(f"order:{len(order_soldtos)}")
        if order_soldtos:
            soldto = order_soldtos[0]
            path_used = "order_bstnk"

    # Path A: TVA/SIREN (may return multiple - score against text)
    if not soldto:
        vat_soldtos = _resolve_via_vat(tax_result, master_data)
        paths_tried.append(f"vat:{len(vat_soldtos)}")
        if len(vat_soldtos) == 1:
            soldto = vat_soldtos[0]
            path_used = "vat_siren"
        elif len(vat_soldtos) > 1:
            # Multiple customers share this VAT - score each against text
            best_vat_score = -1
            for candidate_soldto in vat_soldtos:
                candidate_shiptos = _get_shiptos_for_soldto(candidate_soldto, master_data)
                for sh in candidate_shiptos:
                    s = _score_shipto_vs_text(sh, text, detected_address)
                    if s > best_vat_score:
                        best_vat_score = s
                        soldto = candidate_soldto
                        path_used = "vat_siren_scored"
            if not soldto and vat_soldtos:
                soldto = vat_soldtos[0]
                path_used = "vat_siren_first"

    # Path D: Customer name in document text (least specific, last resort)
    if not soldto:
        name_soldtos = _resolve_via_name(text, master_data)
        paths_tried.append(f"name:{len(name_soldtos)}")
        if len(name_soldtos) == 1:
            soldto = name_soldtos[0]
            path_used = "name_match"
        elif len(name_soldtos) > 1:
            # Multiple names found - score their SHIPTOs against text
            best_name_score = -1
            for candidate_soldto in name_soldtos:
                candidate_shiptos = _get_shiptos_for_soldto(candidate_soldto, master_data)
                for sh in candidate_shiptos:
                    s = _score_shipto_vs_text(sh, text, detected_address)
                    if s > best_name_score:
                        best_name_score = s
                        soldto = candidate_soldto
                        path_used = "name_match_scored"

    if not soldto:
        return {"resolved": False, "reason": "no_soldto_found", "paths_tried": paths_tried}

    # Get SHIPTO candidates for this SOLDTO
    shiptos = _get_shiptos_for_soldto(soldto, master_data)
    if not shiptos:
        return {
            "resolved": False, "soldto": soldto, "path": path_used,
            "reason": f"no_shipto_for_soldto_{soldto}", "paths_tried": paths_tried,
        }

    # Score each SHIPTO against document text
    scored = []
    for shipto in shiptos:
        score = _score_shipto_vs_text(shipto, text, detected_address)
        scored.append({**shipto, "_cross_score": score})

    # If multiple SHIPTOs: deprioritize the one that IS the SOLDTO itself
    # (its address always appears in the PDF as sender, inflating its score)
    # Only apply when another candidate has a strong match (postal found = 40+)
    if len(scored) > 1:
        for entry in scored:
            if entry.get("id") == soldto:
                best_other = max(
                    (e.get("_cross_score", 0) for e in scored if e.get("id") != soldto),
                    default=0
                )
                if best_other >= 40:
                    # Strong alternative exists - reduce SOLDTO's inflated score
                    entry["_cross_score"] = max(0, entry["_cross_score"] - 80)

    scored.sort(key=lambda x: x.get("_cross_score", 0), reverse=True)
    best = scored[0]
    best_score = best.get("_cross_score", 0)

    # Determine confidence
    if best_score >= 80:
        confidence = 95
        statut = "Validee cross-resolution"
    elif best_score >= 50:
        confidence = 75
        statut = "Probable cross-resolution"
    elif best_score >= 20:
        confidence = 50
        statut = "A verifier cross-resolution"
    elif len(shiptos) == 1:
        confidence = 70
        statut = "SHIPTO unique pour SOLDTO"
    else:
        confidence = 30
        statut = "Faible cross-resolution"

    return {
        "resolved": True,
        "soldto": soldto,
        "shipto": best,
        "path": path_used,
        "confidence": confidence,
        "statut": statut,
        "score": best_score,
        "candidates_count": len(shiptos),
        "paths_tried": paths_tried,
    }
