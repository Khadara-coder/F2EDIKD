from __future__ import annotations

import json
import re
import time
from datetime import date

from app.amounts import extract_document_totals, rank_amounts_by_context
from app.document import build_cross_validation, build_debug_summary
from app.engines.customer_order import CustomerOrderNumberEngine
from app.engines.delivery_address import DeliveryAddressEngine
from app.engines.delivery_date import extract_delivery_info
from app.engines.order_lines import OrderLinesEngine
from app.engines.shipto_matching import ShipToMatchingEngine
from app.engines.special_instructions import extract_special_instructions, extract_warnings
from app.engines.tax_identification import TaxIdentificationEngine
from app.engines.cross_resolver import cross_resolve
from app.engines.llm_resolver import llm_resolve, llm_validate
from app.engines.llm_orderlines import llm_extract_orderlines
from app.engines.rejection_engine import check_rejections, rejection_summary
from app.edifact_generator import structured_to_order, build_orders_d96a, EdifactBuildError
from app.masterdata import get_master_data, validate_order_number
from app.text_utils import compact_text, first_value, fold_text, unique


def candidate_lines(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    matches = []
    for line in text.splitlines():
        folded = fold_text(line)
        if any(keyword in folded for keyword in keywords):
            matches.append(line)
    return unique(matches, limit=limit)


def _to_float(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _format_amount_fr(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def _looks_polluted_line_description(description: str) -> bool:
    value = compact_text(description or "")
    if not value:
        return False
    if len(value) > 220:
        return True
    if len(re.findall(r"(?:ELM|EL)?\d{7,11}", value, flags=re.IGNORECASE)) >= 2:
        return True
    if len(re.findall(r"\d+[,.]\d{2}", value)) >= 4:
        return True
    folded = fold_text(value)
    return "page 1 sur" in folded or "a livrer" in folded or "a facturer" in folded


def _infer_quantity_from_price_total(price: float | None, total: float | None) -> float | None:
    if not price or not total or price <= 0 or total <= 0:
        return None
    ratio = total / price
    if ratio < 1 or ratio > 10000:
        return None
    rounded_int = round(ratio)
    # Allow tiny epsilon for floating point arithmetic (e.g. 445.38/222.69 = 1.9999...)
    if abs(ratio - rounded_int) < 1e-6:
        return float(rounded_int)
    # Quantities are natural integers — reject genuine non-integers (0.5, 1.5, etc.)
    return None


def _to_natural_qty(value: float | None) -> float | None:
    """Enforce business rule: quantities are always exact natural integers >= 1.
    
    Allows tiny epsilon (1e-6) for floating point arithmetic imprecision.
    Rejects genuine non-integers like 0.5, 1.5, 3.072, 1.98.
    """
    if value is None or value <= 0:
        return None
    rounded = round(value)
    if rounded < 1:
        return None
    # Allow tiny epsilon for floating point arithmetic
    if abs(value - rounded) < 1e-6:
        return float(rounded)
    # Reject genuine non-integers
    return None


_QTY_IN_DESC_RE = re.compile(
    r"(?<![\d.,])(?P<qty>\d{1,4}(?:[,.]\d{1,3})?)\s*"
    r"(?:PIECE|PCE|PCS|PC|UN|EA)\b",
    flags=re.IGNORECASE,
)


def _extract_qty_from_description(description: str) -> float | None:
    """Extract quantity embedded in description, e.g. '5 PIECE 25,77000 128,85000'."""
    if not description:
        return None
    m = _QTY_IN_DESC_RE.search(description)
    if m:
        try:
            return float(m.group("qty").replace(",", "."))
        except (ValueError, TypeError):
            pass
    return None


def _sanitize_order_lines(order_lines: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    next_line_num = 10
    for line in order_lines:
        article = compact_text(line.get("code_article") or line.get("article") or "")
        if not article:
            continue

        qty = _to_float(line.get("quantite") if "quantite" in line else line.get("quantity"))
        price = _to_float(line.get("prix_unitaire_ht") if "prix_unitaire_ht" in line else line.get("unit_price"))
        total = _to_float(line.get("montant_ligne_ht") if "montant_ligne_ht" in line else line.get("amount"))
        description = compact_text(line.get("description") or line.get("designation") or "")
        delivery_date = line.get("date_livraison") or line.get("delivery_date")
        customer_reference = compact_text(line.get("customer_reference") or line.get("ref_client") or "")
        payment_terms = compact_text(line.get("payment_terms") or "")
        
        # Extract delivery info and special instructions from description context
        delivery_info = extract_delivery_info(description)
        if not delivery_date and delivery_info.get("delivery_date"):
            delivery_date = delivery_info["delivery_date"]
        
        special_instructions = extract_special_instructions(description)
        warnings = extract_warnings(description)

        if qty is not None and qty <= 0:
            qty = None
        if price is not None and price <= 0:
            price = None
        if total is not None and total <= 0:
            total = None

        # Try multiple fallbacks for quantity
        if qty is None:
            qty = _infer_quantity_from_price_total(price, total)
        if qty is None:
            qty = _extract_qty_from_description(description)
        # Fallback: calculate from total/price — only accept if result is a natural integer
        if qty is None and total is not None and price is not None and price > 0:
            calculated_qty = total / price
            qty = _to_natural_qty(calculated_qty)  # rejects 0.03, 0.5, 3.072 etc.

        # Enforce business rule: quantity must be a natural integer
        if qty is not None:
            qty = _to_natural_qty(qty)

        if qty and price and not total:
            total = round(qty * price, 2)
        elif qty and total and not price:
            price = round(total / qty, 2) if qty != 0 else None

        polluted = _looks_polluted_line_description(description)
        if qty and price and total:
            expected = qty * price
            if expected > 0 and abs(expected - total) > max(1.0, expected * 0.15):
                inferred_qty = _infer_quantity_from_price_total(price, total)
                if inferred_qty:
                    qty = inferred_qty
                elif polluted:
                    continue

        if qty is None or qty <= 0:
            continue
        if price is None and total is None:
            continue
        if polluted and (price is None or total is None):
            continue

        cleaned.append(
            {
                "numero_ligne": next_line_num,
                "code_article": article,
                "code_article_raw": compact_text(line.get("code_article_raw") or article),
                "description": description,
                "quantite": qty,
                "prix_unitaire_ht": price,
                "montant_ligne_ht": total,
                "customer_reference": customer_reference,
                "payment_terms": payment_terms,
                "date_livraison": delivery_date,
                "special_instructions": special_instructions,
                "warnings": warnings,
            }
        )
        next_line_num += 10
    return cleaned


def _merge_order_line_candidates(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Keep LLM lines, then add deterministic lines whose Bosch article is missing."""
    merged = list(primary or [])
    seen = {
        compact_text(line.get("code_article") or line.get("article") or "")
        for line in merged
        if compact_text(line.get("code_article") or line.get("article") or "")
    }
    for line in secondary or []:
        article = compact_text(line.get("code_article") or line.get("article") or "")
        if not article or article in seen:
            continue
        merged.append(line)
        seen.add(article)
    return merged


def _finalize_document_totals(totals: dict[str, str | None], order_lines: list[dict]) -> tuple[dict[str, str | None], float | None]:
    merged = dict(totals or {})
    total_lignes_ht = round(sum(l.get("montant_ligne_ht") or 0 for l in order_lines), 2) if order_lines else None
    if not merged.get("Total HT") and total_lignes_ht is not None and total_lignes_ht > 0:
        merged["Total HT"] = _format_amount_fr(total_lignes_ht)
    return merged, total_lignes_ht


# ─── Deterministic date extraction (fallback when LLM unavailable) ────────────

_FR_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}

_ORDER_DATE_LABELS = [
    "date de la commande", "date de commande", "date commande",
    "commande du", "commande le", "date du bon de commande",
    "date bon de commande", "date d'emission", "date d emission",
    "date d'edition", "date d edition", "date document", "order date",
    "date de creation",
]

_DELIVERY_DATE_LABELS = [
    "date de livraison souhaitee", "livraison souhaitee",
    "date de livraison prevue", "date de livraison", "date livraison",
    "date de livraison au plus tard", "livraison prevue", "livraison le",
    "livrer le", "livrer avant le", "livrer avant", "delai de livraison",
    "date souhaitee", "date reception souhaitee", "reception souhaitee",
    "a livrer le", "to be delivered", "deliver by", "delivery date",
]

# Numeric: DD/MM/YYYY or DD-MM-YY, and ISO YYYY-MM-DD
_NUM_DATE_RE = re.compile(
    r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})"          # ISO first
    r"|(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})"       # DD/MM/YYYY
)
# Textual French: "9 juillet 2026" (accents already folded away)
_TXT_DATE_RE = re.compile(r"(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})")


def _iso_from_parts(year: int, month: int, day: int) -> str | None:
    if year < 100:
        year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_first_date(segment: str) -> str | None:
    """Return the first date found in a folded text segment as YYYY-MM-DD."""
    m = _NUM_DATE_RE.search(segment)
    if m:
        if m.group(1):  # ISO
            iso = _iso_from_parts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            iso = _iso_from_parts(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        if iso:
            return iso
    m = _TXT_DATE_RE.search(segment)
    if m:
        month = _FR_MONTHS.get(m.group(2))
        if month:
            return _iso_from_parts(int(m.group(3)), month, int(m.group(1)))
    return None


def _find_date_near_label(folded: str, labels: list[str], window: int = 40) -> str | None:
    """Find the first date appearing within `window` chars after any label."""
    for label in labels:
        start = folded.find(label)
        while start != -1:
            segment = folded[start + len(label): start + len(label) + window]
            iso = _extract_first_date(segment)
            if iso:
                return iso
            start = folded.find(label, start + 1)
    return None


def _collect_all_dates(text: str) -> list[str]:
    out: list[str] = []
    folded = fold_text(text or "")
    for m in _NUM_DATE_RE.finditer(folded):
        iso = None
        if m.group(1):
            iso = _iso_from_parts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            iso = _iso_from_parts(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        if iso and iso not in out:
            out.append(iso)
    for m in _TXT_DATE_RE.finditer(folded):
        month = _FR_MONTHS.get(m.group(2))
        if month:
            iso = _iso_from_parts(int(m.group(3)), month, int(m.group(1)))
            if iso and iso not in out:
                out.append(iso)
    return out


def _is_plausible_business_date(iso_date: str | None) -> bool:
    if not iso_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso_date):
        return False
    year = int(iso_date[:4])
    current_year = date.today().year
    return current_year - 5 <= year <= current_year + 2


def _choose_final_date(
    llm_date: str | None,
    anchored_date: str | None,
    anchored_source: str,
    all_dates: list[str],
) -> str | None:
    llm_ok = llm_date if _is_plausible_business_date(llm_date) else None
    anchored_ok = anchored_date if _is_plausible_business_date(anchored_date) else None
    strong_anchor = anchored_source in {"line_context", "label_window"}

    if strong_anchor and anchored_ok:
        return anchored_ok
    if llm_ok and llm_ok in all_dates:
        return llm_ok
    if anchored_ok:
        return anchored_ok
    return llm_ok


def _score_date_by_labels(line_folded: str, labels: list[str]) -> int:
    score = 0
    for lb in labels:
        if lb in line_folded:
            score += 10
    return score


def _extract_date_by_line_context(text: str, labels: list[str]) -> str | None:
    """Find best date on a labeled line, otherwise on the immediate next line."""
    best: tuple[int, str] | None = None
    lines = text.splitlines()
    for idx, raw in enumerate(lines):
        lf = fold_text(raw)
        base = _score_date_by_labels(lf, labels)
        if base <= 0:
            continue
        same_line = _extract_first_date(lf)
        if same_line:
            cand = (base + 5, same_line)
            if best is None or cand[0] > best[0]:
                best = cand
        if idx + 1 < len(lines):
            next_line = fold_text(lines[idx + 1])
            nxt = _extract_first_date(next_line)
            if nxt:
                cand = (base + 3, nxt)
                if best is None or cand[0] > best[0]:
                    best = cand
    return best[1] if best else None


def extract_dates_anchored(text: str) -> dict:
    """Deterministic extraction of order/delivery dates anchored on labels.

    Used as a fallback when the LLM is unavailable. Returns ISO dates
    (YYYY-MM-DD) or None for each field.
    """
    folded = fold_text(text or "")

    # 1) Strongest: line-level context (label + date on same/next line)
    order_date = _extract_date_by_line_context(text, _ORDER_DATE_LABELS)
    delivery_date = _extract_date_by_line_context(text, _DELIVERY_DATE_LABELS)

    # 2) Fallback: proximity in compact folded text (wider window for noisy OCR)
    if not order_date:
        order_date = _find_date_near_label(folded, _ORDER_DATE_LABELS, window=140)
    if not delivery_date:
        delivery_date = _find_date_near_label(folded, _DELIVERY_DATE_LABELS, window=140)

    # 3) Conservative defaults: earliest as order date, latest as delivery date
    all_dates = _collect_all_dates(text)
    order_source = "missing"
    delivery_source = "missing"
    if order_date:
        order_source = "line_context"
    if delivery_date:
        delivery_source = "line_context"
    if all_dates:
        sorted_dates = sorted(all_dates)
        if not order_date:
            order_date = sorted_dates[0]
            order_source = "fallback_all_dates"
        if not delivery_date:
            delivery_date = sorted_dates[-1]
            delivery_source = "fallback_all_dates"

    # 4) Keep temporal consistency when both exist
    if order_date and delivery_date and delivery_date < order_date:
        delivery_date = order_date

    return {
        "date_commande": order_date,
        "date_livraison": delivery_date,
        "date_commande_source": order_source,
        "date_livraison_source": delivery_source,
        "all_dates": all_dates,
    }


def extract_structured_fields(
    text: str,
    fields: dict,
    filename: str | None = None,
    layout_analysis: dict | None = None,
    extraction_context: dict | None = None,
    layout: dict | None = None,
) -> dict:
    context = extraction_context or {}
    compact = compact_text(text)
    folded = fold_text(compact)
    header = re.split(r"\b(?:Merci de livrer|Montant HT|Prix net|Total HT)\b", compact, maxsplit=1)[0]
    tax_identification = fields.get("tax_identification") or TaxIdentificationEngine().extract(text)
    vat_numbers = tax_identification.get("vat_numbers") or []

    reference_codes = [
        code
        for code in re.findall(r"\b[A-Z]{2,}\d{4}[A-Z0-9]{4,}\b", header)
        if code.upper() not in {item.upper().replace(" ", "") for item in vat_numbers}
    ]
    supplier_code = first_value(re.findall(r"Code fournisseur\s*:?\s*(\d+)", compact, flags=re.IGNORECASE))

    totals = extract_document_totals(text)
    ranked_amounts = rank_amounts_by_context(text, fields.get("amounts", []))
    payment = first_value(re.findall(r"(Virement\s+[^.]+?(?:le\s+\d{1,2})?)", compact, flags=re.IGNORECASE))
    delivery_mode = first_value(re.findall(r"Mode livraison\s*:?\s*([A-Za-z][A-Za-z -]{2,30})", compact, flags=re.IGNORECASE))
    if delivery_mode and "virement" in fold_text(delivery_mode):
        delivery_mode = "Standard" if "standard" in folded else None

    companies = unique(
        re.findall(r"\b(?:BOSCH PRODUITS FINIS|ISERBA|BAV|[A-Z][A-Z0-9&' -]{3,})\b", header),
        limit=12,
    )
    document_type = "Bon de commande" if "bon de commande" in folded else None
    order_engine_result = fields.get("customer_order_number") or CustomerOrderNumberEngine().extract(text, filename)
    order_number = context.get("order_number") or order_engine_result.get("order_number")
    delivery_engine = DeliveryAddressEngine()
    if layout_analysis is None:
        layout_analysis = delivery_engine.analyze_layout(layout)
    shipto_result = ShipToMatchingEngine().resolve_best(
        text=text,
        fields=fields,
        filename=filename,
        layout=layout,
        layout_analysis=layout_analysis,
        order_number=order_number,
        known_soldto_id=context.get("known_soldto_id"),
    )
    delivery_address = shipto_result["detected_address"]
    master_delivery_address = shipto_result["shipto"]

    # Cross-resolution: if primary matching failed, try alternate paths
    primary_confidence = master_delivery_address.get("Confiance", 0)
    if (not primary_confidence or primary_confidence == 0) and tax_identification:
        cross_resolution = cross_resolve(
            text=text,
            tax_result=tax_identification,
            order_result=order_engine_result,
            detected_address=delivery_address,
            validated_result=master_delivery_address,
        )
        if cross_resolution.get("resolved"):
            shipto_entry = cross_resolution["shipto"]
            soldto_resolved = cross_resolution["soldto"]
            soldto_customer = get_master_data().get("customers_by_id", {}).get(soldto_resolved) or {}
            master_delivery_address = {
                "Statut": cross_resolution["statut"],
                "Confiance": cross_resolution["confidence"],
                "Raison": f"cross_resolve:{cross_resolution['path']}",
                "SOLDTO": soldto_resolved,
                "Client": soldto_customer.get("name", ""),
                "SHIPTO": shipto_entry.get("id", soldto_resolved),
                "Nom": shipto_entry.get("name", ""),
                "Rue": shipto_entry.get("street", ""),
                "Code postal": shipto_entry.get("postal", ""),
                "Ville": shipto_entry.get("city", ""),
                "Pays": shipto_entry.get("country", "FR"),
                "Adresse complete": "\n".join(filter(None, [
                    shipto_entry.get("name", ""),
                    shipto_entry.get("street", ""),
                    f"{shipto_entry.get('postal', '')} {shipto_entry.get('city', '')}".strip(),
                    shipto_entry.get("country", ""),
                ])),
                "Cross resolution": cross_resolution["path"],
                "Cross score": cross_resolution.get("score", 0),
                "Candidats SHIPTO": cross_resolution.get("candidates_count", 0),
                "Guidage masterdata": "oui",
            }

    # LLM Layer: Systematic extraction (Sonnet 4) + Fallback + Validation
    current_confidence = master_delivery_address.get("Confiance", 0)

    # --- LLM EXTRACTION SYSTÉMATIQUE (Sonnet 4 pour N° commande sur tous les PDFs) ---
    llm_extracted = None
    try:
        from app.engines.llm_resolver import llm_extract
        _raw = llm_extract(text)
        if isinstance(_raw, dict):
            llm_extracted = _raw
        elif isinstance(_raw, list) and _raw and isinstance(_raw[0], dict):
            llm_extracted = _raw[0]
    except Exception:
        pass

    # --- LLM FALLBACK SHIPTO: if still Conf=0 after rules + cross-resolution ---
    if not current_confidence or current_confidence == 0:
        try:
            llm_result = llm_resolve(text, get_master_data(), pre_extracted=llm_extracted)
            if llm_result.get("resolved"):
                from app.engines.cross_resolver import _get_shiptos_for_soldto
                md = get_master_data()
                # Get SHIPTO details
                shipto_id = llm_result["shipto"]
                soldto_resolved = llm_result["soldto"]
                shiptos = _get_shiptos_for_soldto(soldto_resolved, md)
                shipto_entry = next((s for s in shiptos if s.get("id") == shipto_id), None)
                if not shipto_entry:
                    # SHIPTO = SOLDTO case
                    customers_by_id = md.get("customers_by_id", {})
                    shipto_entry = customers_by_id.get(shipto_id, {})

                master_delivery_address = {
                    "Statut": f"LLM resolution ({llm_result['path']})",
                    "Confiance": llm_result["confidence"],
                    "Raison": f"llm_resolve:{llm_result['path']}",
                    "SOLDTO": soldto_resolved,
                    "Client": (md.get("customers_by_id", {}).get(soldto_resolved) or {}).get("name", ""),
                    "SHIPTO": shipto_id,
                    "Nom": shipto_entry.get("name", ""),
                    "Rue": shipto_entry.get("street", ""),
                    "Code postal": shipto_entry.get("postal", ""),
                    "Ville": shipto_entry.get("city", ""),
                    "Pays": shipto_entry.get("country", "FR"),
                    "Adresse complete": "\n".join(filter(None, [
                        shipto_entry.get("name", ""),
                        shipto_entry.get("street", ""),
                        f"{shipto_entry.get('postal', '')} {shipto_entry.get('city', '')}".strip(),
                        shipto_entry.get("country", ""),
                    ])),
                    "Cross resolution": llm_result["path"],
                    "Cross score": llm_result.get("score", 0),
                    "LLM extracted": llm_result.get("extracted", {}),
                    "Guidage masterdata": "oui",
                }
                current_confidence = llm_result["confidence"]
        except Exception as e:
            pass  # LLM failure is non-blocking

    # --- LLM VALIDATOR: only for weak cross-resolution paths (name_match, order_bstnk) ---
    # Do NOT validate strong signals (vat_siren_scored, client_number, vat_siren)
    cross_path = master_delivery_address.get("Cross resolution", "")
    weak_paths = ("name_match", "order_bstnk", "name_match_scored")
    is_weak_cross = any(wp in cross_path for wp in weak_paths) if cross_path else False
    if 50 <= current_confidence < 80 and is_weak_cross:
        try:
            shipto_info = {
                "id": master_delivery_address.get("SHIPTO", ""),
                "name": master_delivery_address.get("Nom", ""),
                "street": master_delivery_address.get("Rue", ""),
                "postal": master_delivery_address.get("Code postal", ""),
                "city": master_delivery_address.get("Ville", ""),
            }
            soldto_for_valid = master_delivery_address.get("SOLDTO", "")
            validation = llm_validate(text, shipto_info, soldto_for_valid)
            if validation:
                if validation.get("match") is True and validation.get("confiance", 0) >= 70:
                    # LLM confirms: boost confidence
                    master_delivery_address["Confiance"] = max(current_confidence, 75)
                    master_delivery_address["LLM validation"] = f"confirmed ({validation.get('confiance')})"
                elif validation.get("match") is False and validation.get("confiance", 0) >= 70:
                    # LLM rejects: downgrade to 0
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = "Rejet LLM validation"
                    master_delivery_address["LLM validation"] = f"rejected: {validation.get('raison', '')}"
                else:
                    master_delivery_address["LLM validation"] = f"uncertain ({validation.get('confiance', '?')})"
        except Exception as e:
            pass  # LLM failure is non-blocking

    # --- LLM ORDER NUMBER: override regex if LLM extracted a clean order number ---
    llm_order_number = None
    if llm_extracted and llm_extracted.get("numero_commande"):
        llm_cmd = str(llm_extracted["numero_commande"]).strip()
        # Accept LLM order number if it's not null/empty and not a date
        if llm_cmd and llm_cmd.lower() not in ("null", "none", ""):
            import re as _re
            if not _re.fullmatch(r"\d{2}/\d{2}/\d{4}", llm_cmd) and not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", llm_cmd):
                llm_order_number = llm_cmd

    # Use LLM order number as primary, regex as fallback
    final_order_number = llm_order_number or order_number

    # --- ORDER LINES: LLM first, deterministic engine as complement/fallback ---
    order_lines = []
    try:
        order_lines = llm_extract_orderlines(text)
    except Exception:
        pass  # Non-blocking

    deterministic_lines = []
    try:
        engine_lines = OrderLinesEngine().extract(text, layout=layout).get("lines", [])
        for idx, ln in enumerate(engine_lines, start=1):
            article = (ln.get("article") or "").strip()
            if not article:
                continue
            deterministic_lines.append({
                "numero_ligne": idx * 10,
                "code_article": article,
                "code_article_raw": article,
                "description": (ln.get("designation") or "").strip(),
                "quantite": _to_float(ln.get("quantity")),
                "prix_unitaire_ht": _to_float(ln.get("unit_price")),
                "montant_ligne_ht": _to_float(ln.get("amount")),
                "date_livraison": ln.get("delivery_date"),
            })
    except Exception:
        pass

    order_lines = _merge_order_line_candidates(order_lines, deterministic_lines)

    order_lines = _sanitize_order_lines(order_lines)

    # --- SHIPTO RESOLUTION VIA SCORING ENGINE ---
    # Replaces the old Level 0/1/2 cascade with evidence-based scoring.
    # Each SHIPTO candidate gets points based on evidence found in the PDF.
    # LLM is only used as fallback on top 3 candidates if score < 95 or gap < 15.
    resolved_soldto = master_delivery_address.get("SOLDTO", "")

    # Always run scoring engine when SOLDTO has multiple SHIPTOs
    if resolved_soldto:
        try:
            from app.engines.shipto_scoring import resolve_shipto_with_scoring
            md = get_master_data()
            partners = md.get("partners_by_soldto", {}).get(resolved_soldto, [])

            if len(partners) > 1:
                # Run the scoring engine
                scoring_result = resolve_shipto_with_scoring(
                    text=text,
                    soldto_id=resolved_soldto,
                    masterdata=md,
                    soldto_confidence=master_delivery_address.get("Confiance", 80),
                    use_llm_fallback=True,
                )

                if scoring_result.best_candidate and scoring_result.shipto_confidence > 0:
                    best = scoring_result.best_candidate
                    master_delivery_address["SHIPTO"] = best.shipto_id
                    master_delivery_address["Nom"] = best.name
                    master_delivery_address["Rue"] = best.street
                    master_delivery_address["Code postal"] = best.postal
                    master_delivery_address["Ville"] = best.city
                    master_delivery_address["Confiance"] = scoring_result.shipto_confidence
                    master_delivery_address["Disambiguation"] = (
                        f"SCORING:{best.score}pts "
                        f"{'+'.join(scoring_result.matched_by[:3])}"
                        f"\u2192{best.shipto_id} {best.city}"
                    )
                    master_delivery_address["Disambiguation_explanation"] = scoring_result.explanation
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["matched_by"] = scoring_result.matched_by
                    master_delivery_address["shipto_score"] = best.score
                    master_delivery_address["scoring_decision"] = scoring_result.decision

                elif scoring_result.error:
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = f"ERREUR SCORING: {scoring_result.error}"
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["scoring_decision"] = "REJECTED"

                else:
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = "Aucun SHIPTO ne correspond aux preuves du document"
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["scoring_decision"] = scoring_result.decision or "REJECTED"
        except Exception:
            pass  # Scoring is non-blocking; keep existing master_delivery_address

    soldto_id = context.get("known_soldto_id") or master_delivery_address.get("SOLDTO")
    order_validation = validate_order_number(get_master_data(), final_order_number, soldto_id)
    cross_validation = build_cross_validation(order_validation, master_delivery_address)

    # --- REJECTION ENGINE: check all 9 Esker rejection rules ---
    rejection_input = {
        "document": {
            "Type": document_type,
            "Numero de commande": final_order_number,
        },
        "adresses": {
            "Adresse de livraison validee": master_delivery_address,
        },
        "lignes_commande": {
            "lignes": order_lines,
            "nb_lignes": len(order_lines),
        },
    }
    rejections = check_rejections(rejection_input, master_data=get_master_data())
    rejection_result = rejection_summary(rejections)

    # --- DATES: LLM primary, deterministic label-anchored fallback ---
    _anchored_dates = extract_dates_anchored(text)
    final_order_date = _choose_final_date(
        (llm_extracted.get("date_commande") if llm_extracted else None),
        _anchored_dates.get("date_commande"),
        str(_anchored_dates.get("date_commande_source") or "missing"),
        list(_anchored_dates.get("all_dates") or []),
    )
    final_delivery_date = _choose_final_date(
        (llm_extracted.get("date_livraison_souhaitee") if llm_extracted else None),
        _anchored_dates.get("date_livraison"),
        str(_anchored_dates.get("date_livraison_source") or "missing"),
        list(_anchored_dates.get("all_dates") or []),
    )
    if final_order_date and final_delivery_date and final_delivery_date < final_order_date:
        final_delivery_date = final_order_date

    totals, total_lignes_ht = _finalize_document_totals(totals, order_lines)

        # --- EDIFACT D96A: generate message if not blocked ---
    edifact_message = None
    edifact_errors = None
    edifact_generated = False
    if rejection_result.get("decision") != "REJECTED":
        try:
            edifact_input = {
                "document": {
                    "Numero de commande": final_order_number,
                    "Date commande LLM": final_order_date,
                    "Date document": first_value(fields.get("dates", [])),
                    "Date livraison souhaitee": final_delivery_date,
                },
                "adresses": {
                    "Adresse de livraison validee": master_delivery_address,
                },
                "lignes_commande": {
                    "lignes": order_lines,
                },
            }
            order_obj = structured_to_order(edifact_input)
            interchange_ref = f"LA{final_order_number or 'X'}".replace("/", "")[:14]
            edifact_message = build_orders_d96a(order=order_obj, interchange_ref=interchange_ref)
            edifact_generated = True
        except EdifactBuildError as e:
            edifact_errors = e.errors
        except Exception as e:
            edifact_errors = [str(e)]

    return {
        "document": {
            "Type": document_type,
            "Numero de commande": final_order_number,
            "Numero commande LLM": llm_order_number,
            "Numero commande regex": order_number,
            "CustomerOrderNumberEngine": order_engine_result,
            "Commande masterdata": order_validation,
            "Reference": first_value(reference_codes),
            "Date document": first_value(fields.get("dates", [])),
            "Date commande LLM": final_order_date,
            "Date livraison souhaitee": final_delivery_date,
            "Code fournisseur": supplier_code,
            "TVA intracommunautaire": first_value(vat_numbers),
            "Identification fiscale": tax_identification,
        },
        "adresses": {
            "Adresse de livraison validee": master_delivery_address,
            "Adresse de livraison detectee": delivery_address,
        },
        "lignes_commande": {
            "lignes": order_lines,
            "nb_lignes": len(order_lines),
            "total_lignes_ht": total_lignes_ht,
        },
        "rejets": rejection_result,
        "edifact": {
            "generated": edifact_generated,
            "message": edifact_message,
            "errors": edifact_errors,
        },
        "montants": {
            "Total HT": totals["Total HT"],
            "Total TTC": totals["Total TTC"],
            "Montants detectes": fields.get("amounts", []),
            "Montants priorises": ranked_amounts,
        },
        "conditions": {
            "Mode livraison": delivery_mode,
            "Condition paiement": payment,
        },
        "contacts": {
            "Emails": fields.get("emails", []),
            "Telephones": fields.get("phones", []),
        },
        "parties": {
            "Societes detectees": companies,
            "Client candidates": fields.get("client_candidates", []),
            "Fournisseur candidates": fields.get("supplier_candidates", []),
        },
        "identifiants": {
            "SIRET": tax_identification.get("siret") or fields.get("siret", []),
            "SIREN": tax_identification.get("siren") or fields.get("siren", []),
            "SIREN valide": tax_identification.get("valid_siren", []),
            "TVA candidates": tax_identification.get("vat_candidates", []),
            "TVA rejetees": tax_identification.get("rejected_vat_candidates", []),
            "TVA attendue depuis SIREN": tax_identification.get("expected_vat_from_siren", []),
            "IBAN": fields.get("iban", []),
        },
        "line_items": OrderLinesEngine().extract(text, layout=layout)["lines"],
        "validation": cross_validation,
    }


def extract_candidate_fields(
    text: str,
    instruction: str,
    filename: str | None = None,
    layout: dict | None = None,
    extraction_context: dict | None = None,
) -> dict:
    amount_pattern = r"(?<!\w)(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+),\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€)(?!\w)"
    date_pattern = r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    phone_pattern = r"\b(?:0\d(?:[\s.-]?\d{2}){4}|(?:(?:\+|00)33\s?)[1-9](?:[\s.-]?\d{2}){4})\b"

    tax_identification = TaxIdentificationEngine().extract(text)
    customer_order_number = CustomerOrderNumberEngine().extract(text, filename)
    fields = {
        "requested": instruction,
        "emails": unique(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)),
        "phones": unique(re.findall(phone_pattern, text)),
        "dates": unique(re.findall(date_pattern, text)),
        "amounts": unique(re.findall(amount_pattern, text), limit=30),
        "total_candidates": candidate_lines(
            text,
            ["total ttc", "ttc", "net a payer", "montant total", "total a payer", "total due"],
        ),
        "document_number_candidates": candidate_lines(
            text,
            ["facture", "invoice", "document", "commande", "devis", "reference", "ref "],
        ),
        "client_candidates": candidate_lines(
            text,
            ["client", "facture a", "bill to", "destinataire", "acheteur", "customer"],
        ),
        "supplier_candidates": candidate_lines(
            text,
            ["fournisseur", "vendeur", "seller", "emetteur", "societe", "supplier"],
        ),
        "siret": tax_identification.get("siret", []),
        "siren": tax_identification.get("siren", []),
        "vat_numbers": tax_identification.get("vat_numbers", []),
        "vat_candidates": tax_identification.get("vat_candidates", []),
        "tax_identification": tax_identification,
        "customer_order_number": customer_order_number,
        "iban": unique(re.findall(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b", text, flags=re.IGNORECASE)),
    }
    layout_analysis = DeliveryAddressEngine().analyze_layout(layout)
    if layout_analysis.get("address_candidates") or layout_analysis.get("anchor_summaries"):
        fields["layout_analysis"] = {
            "candidate_summaries": layout_analysis.get("candidate_summaries", []),
            "anchor_summaries": layout_analysis.get("anchor_summaries", []),
        }
    fields["structured"] = extract_structured_fields(
        text, fields, filename, layout_analysis, extraction_context, layout
    )
    return fields


def update_extraction_context_from_structured(context: dict, structured: dict) -> None:
    document = structured.get("document", {})
    validated = structured.get("adresses", {}).get("Adresse de livraison validee", {})
    order_number = document.get("Numero de commande")
    if order_number and not context.get("order_number"):
        context["order_number"] = order_number
    soldto = validated.get("SOLDTO")
    if soldto:
        context["known_soldto_id"] = soldto


def build_text_extraction_result(
    page: int,
    text: str,
    source: str,
    instruction: str,
    filename: str | None = None,
    layout: dict | None = None,
    engine_name: str = "text_ocr",
    extraction_context: dict | None = None,
    include_debug: bool = False,
) -> dict:
    started = time.perf_counter()
    context = extraction_context if extraction_context is not None else {}
    fields = extract_candidate_fields(text, instruction, filename, layout, context)
    structured = fields.get("structured", {})
    update_extraction_context_from_structured(context, structured)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    answer = json.dumps(
        {
            "source": source,
            "fields": fields,
            "text_excerpt": compact_text(text)[:4000],
        },
        ensure_ascii=False,
        indent=2,
    )
    result = {
        "page": page,
        "engine": engine_name,
        "device": "cpu",
        "generation_mode": source,
        "prompt": instruction,
        "answer": answer,
        "fields": fields,
        "raw_text": text,
        "boxes": [],
        "points": [],
        "timings_ms": {"extraction_total": elapsed_ms},
    }
    if include_debug:
        result["debug"] = build_debug_summary(structured)
    return result
