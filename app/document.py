from __future__ import annotations

import re

from app.text_utils import compact_text, first_value, fold_text


def extract_order_number(text: str, filename: str | None = None) -> str | None:
    compact = compact_text(text)
    match = re.search(r"N[°o]\s*(?:de\s*)?commande\s*:?\s*([A-Z0-9-]{6,})", compact, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(
        r"COMMANDE\s*N[°o]?\s*:?\s*(?:\n|\r\n)\s*(ST\s+\d+\s+CSP\s+\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return compact_text(match.group(1))

    match = re.search(
        r"COMMANDE\s*N[°o]?\s*:?\s*([A-Z0-9][A-Z0-9 \-]{4,})",
        compact,
        flags=re.IGNORECASE,
    )
    if match:
        return compact_text(match.group(1))

    ignored = {"BON", "COMMANDE", "FOURNISSEUR", "CLIENT", "PAGE"}
    for line_number, line in enumerate(text.splitlines()):
        if "commande" not in fold_text(line):
            continue
        following = text.splitlines()[line_number + 1 : line_number + 3]
        for candidate_line in following:
            candidate = candidate_line.split("|", 1)[0].strip()
            if candidate.upper() not in ignored and re.fullmatch(r"[A-Z0-9-]{6,}", candidate, flags=re.IGNORECASE):
                return candidate

    match = re.search(r"\b(CM-\d{5,}|[A-Z]{2,}-\d{5,})\b", compact, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    return first_value(re.findall(r"(?<!\d)\d{6,10}(?!\d)", filename or ""))


def merge_delivery_addresses(text_address: dict, layout_address: dict | None) -> dict:
    from app.text_utils import norm_key

    if not layout_address:
        return text_address
    if not text_address or text_address.get("Statut") in {"Non detectee", "Libelle trouve mais adresse non reconstruite"}:
        return layout_address

    merged = dict(text_address)
    merged["Source"] = "fusion texte+geometrie"
    conflicts = []
    for field in ("Rue", "Code postal", "Ville", "Nom / service", "Complement"):
        text_val = text_address.get(field)
        geo_val = layout_address.get(field)
        if geo_val and not text_val:
            merged[field] = geo_val
        elif text_val and geo_val and norm_key(str(text_val)) != norm_key(str(geo_val)):
            merged[f"{field} (geometrie)"] = geo_val
            conflicts.append(field)
    if conflicts:
        merged["Conflits fusion"] = conflicts
    if layout_address.get("Score geometrie"):
        merged["Score geometrie"] = layout_address.get("Score geometrie")
    if layout_address.get("Ancre positive"):
        merged["Ancre positive"] = layout_address.get("Ancre positive")
    return merged


def build_cross_validation(order_validation: dict, master_delivery: dict) -> dict:
    order_kunnr = order_validation.get("KUNNR") or ""
    soldto = master_delivery.get("SOLDTO") or ""
    order_status = order_validation.get("Statut") or ""
    delivery_status = master_delivery.get("Statut") or ""

    if order_status == "Non detecte" and not soldto:
        return {"Statut": "Donnees insuffisantes", "Detail": "Pas de commande ni de SOLDTO"}

    if order_status == "Confirmee master data" and soldto:
        if order_kunnr == soldto:
            return {
                "Statut": "Coherent",
                "Detail": f"BSTNK et SOLDTO alignes sur {soldto}",
                "KUNNR": order_kunnr,
                "SOLDTO": soldto,
            }
        return {
            "Statut": "Conflit commande/client",
            "Detail": f"BSTNK->{order_kunnr} != SOLDTO->{soldto}",
            "KUNNR": order_kunnr,
            "SOLDTO": soldto,
        }

    if order_status == "Non trouvee master data" and soldto:
        return {
            "Statut": "Commande inconnue, client identifie",
            "Detail": f"SOLDTO {soldto} sans BSTNK masterdata",
            "SOLDTO": soldto,
        }

    if order_status == "Confirmee master data" and not soldto:
        return {
            "Statut": "Commande connue, livraison non validee",
            "Detail": f"KUNNR {order_kunnr} sans SHIPTO valide",
            "KUNNR": order_kunnr,
        }

    return {
        "Statut": "A verifier",
        "Detail": f"commande={order_status}; livraison={delivery_status}",
        "KUNNR": order_kunnr,
        "SOLDTO": soldto,
    }


def build_debug_summary(structured: dict) -> dict:
    document = structured.get("document", {})
    adresses = structured.get("adresses", {})
    validated = adresses.get("Adresse de livraison validee", {})
    order_validation = document.get("Commande masterdata", {})
    return {
        "order_number": document.get("Numero de commande"),
        "order_masterdata_status": order_validation.get("Statut"),
        "soldto": validated.get("SOLDTO"),
        "shipto": validated.get("SHIPTO"),
        "delivery_status": validated.get("Statut"),
        "delivery_confidence": validated.get("Confiance"),
        "buyer_reason": validated.get("Buyer reason"),
        "line_items_count": len(structured.get("line_items") or []),
        "cross_validation": structured.get("validation", {}),
    }
