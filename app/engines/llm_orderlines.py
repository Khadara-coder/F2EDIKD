"""LLM-based order line extraction using Claude Sonnet 4.

Extracts structured line items from PDF text:
- Article number (Bosch/ELM seller code)
- Quantity
- Unit price (net, HT)
- Optional: description, delivery date

Business rules (from Esker documentation):
- Article numbers are Bosch seller codes (e.g. 7736901359, EL 7716010683)
- Remove EL/ELM prefix before returning
- Ignore lines: PORTSFAB, ECOTAXE, ECOTAX, PORT FOURNISSEUR, PORT (shipping/tax lines)
- Decimal separator: comma (FR) or dot
- Line item numbers: generated as 10, 20, 30...

Endpoint: databricks-claude-sonnet-4
"""

import json
import logging
import math
import re
from typing import Optional
from app.engines.llm_gateway import chat_completion
from app.engines.delivery_date import extract_delivery_info
from app.engines.special_instructions import extract_special_instructions, extract_warnings

logger = logging.getLogger(__name__)

MODEL_ENDPOINT = "databricks-claude-sonnet-4"
FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
AMOUNT_PATTERN = r"(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+)[,.]\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€?)"


# Lines to ignore (shipping/eco-tax surcharges)
IGNORE_PATTERNS = [
    r"PORT\s*FOURNISSEUR",
    r"PORTSFAB",
    r"ECOTAX[E]?",
    r"^PORT$",
    r"FRAIS\s*DE\s*PORT",
    r"PARTICIPATION\s*TRANSPORT",
]


def _call_llm(prompt: str, max_tokens: int = 1500, endpoint: str = MODEL_ENDPOINT) -> Optional[str]:
    """Call the configured LLM provider."""
    try:
        return chat_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            databricks_endpoint=endpoint,
            databricks_fallback_endpoint=FALLBACK_ENDPOINT,
        )
    except Exception as e:
        logger.warning(f"LLM orderlines call failed ({endpoint}): {e}")
        return None


def _parse_json(text: str) -> Optional[list]:
    """Extract JSON array from LLM response."""
    if not text:
        return None
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    cleaned = cleaned.strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "lignes" in result:
            return result["lignes"]
        if isinstance(result, dict) and "lines" in result:
            return result["lines"]
    except json.JSONDecodeError:
        # Try to find JSON array in text
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _clean_article_number(raw: str) -> str:
    """Clean article number: remove EL/ELM prefix, spaces, dashes."""
    if not raw:
        return ""
    cleaned = raw.strip()
    # Remove EL / ELM prefix
    cleaned = re.sub(r"^E\.?L\.?M?\.?\s*", "", cleaned, flags=re.IGNORECASE)
    # Remove spaces and dashes within the number
    cleaned = re.sub(r"[\s\-]", "", cleaned)
    return cleaned


def _should_ignore_line(line: dict) -> bool:
    """Check if a line item should be ignored (shipping/eco-tax)."""
    article = (line.get("code_article") or "").upper()
    description = (line.get("description") or "").upper()
    combined = f"{article} {description}"
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, combined):
            return True
    return False


def _normalize_price(raw) -> Optional[float]:
    """Normalize price: handle comma decimal separator."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    # Remove currency symbols and spaces
    s = re.sub(r"[\u20ac$\s]", "", s)
    # Handle FR format: 1.234,56 or 1 234,56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _normalize_quantity(raw) -> Optional[float]:
    """Normalize quantity."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    s = re.sub(r"[\s]", "", s)
    if "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _looks_polluted_description(description: str) -> bool:
    value = (description or "").strip()
    if not value:
        return False
    if len(value) > 220:
        return True
    if len(re.findall(r"(?:ELM|EL)?\d{7,11}", value, flags=re.IGNORECASE)) >= 2:
        return True
    if len(re.findall(AMOUNT_PATTERN, value, flags=re.IGNORECASE)) >= 4:
        return True
    folded = value.lower()
    return "page 1 sur" in folded or "a livrer" in folded or "a facturer" in folded


def _infer_quantity_from_price_and_total(price: float | None, total: float | None) -> Optional[float]:
    if not price or not total or price <= 0 or total <= 0:
        return None
    ratio = total / price
    if ratio <= 0 or ratio > 10000:
        return None
    rounded_int = round(ratio)
    if abs(ratio - rounded_int) <= 0.02:
        return float(rounded_int)
    rounded_3 = round(ratio, 3)
    if abs(ratio - rounded_3) <= 0.005:
        return rounded_3
    return None


_QTY_IN_DESC_RE = re.compile(
    r"(?<![\d.,])(?P<qty>\d{1,4}(?:[,.]\d{1,3})?)\s*"
    r"(?:PIECE|PCE|PCS|PC|UN|EA)\b",
    flags=re.IGNORECASE,
)


def _extract_qty_from_description(description: str) -> Optional[float]:
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


def _cohere_line(line: dict) -> dict | None:
    article_raw = line.get("code_article") or ""
    article_clean = _clean_article_number(article_raw)
    if not article_clean:
        return None

    qty = _normalize_quantity(line.get("quantite"))
    price = _normalize_price(line.get("prix_unitaire_ht"))
    total = _normalize_price(line.get("montant_ligne_ht"))
    description = (line.get("description") or "").strip()
    customer_reference = (line.get("customer_reference") or "").strip()
    payment_terms = (line.get("payment_terms") or "").strip()
    
    # Extract delivery info and special instructions from description
    delivery_info = extract_delivery_info(description)
    delivery_date_extracted = line.get("date_livraison") or delivery_info.get("delivery_date")
    special_instructions = extract_special_instructions(description)
    warnings = extract_warnings(description)

    if qty is not None and qty <= 0:
        qty = None
    if price is not None and price <= 0:
        price = None
    if total is not None and total <= 0:
        total = None

    if qty is None:
        qty = _infer_quantity_from_price_and_total(price, total)
    if qty is None:
        qty = _extract_qty_from_description(description)
    # NEW: Calculate qty from total/price when both exist
    if qty is None and total is not None and price is not None and price > 0:
        calculated_qty = round(total / price, 2)
        if 0 < calculated_qty <= 9999:  # Reasonable bounds
            qty = calculated_qty
    
    if qty and price and not total:
        total = round(qty * price, 2)
    elif qty and total and not price:
        price = round(total / qty, 2) if qty != 0 else None

    if qty and price and total:
        expected = qty * price
        if expected > 0 and abs(expected - total) > max(0.5, expected * 0.08):
            inferred_qty = _infer_quantity_from_price_and_total(price, total)
            if inferred_qty:
                qty = inferred_qty

    polluted = _looks_polluted_description(description)
    strong_signals = sum(1 for value in (qty, price, total) if value is not None)
    if polluted and strong_signals < 3:
        return None
    if qty is None or qty <= 0:
        return None
    if price is None and total is None:
        return None

    return {
        "code_article": article_clean,
        "code_article_raw": article_raw.strip(),
        "description": description,
        "customer_reference": customer_reference or None,
        "payment_terms": payment_terms or None,
        "quantite": qty,
        "prix_unitaire_ht": price,
        "montant_ligne_ht": total,
        "date_livraison": delivery_date_extracted,
        "special_instructions": special_instructions or None,
        "warnings": warnings or None,
    }


def _finalize_llm_lines(lines: list[dict]) -> list[dict]:
    coherent = []
    rejected = 0
    line_num = 10
    for line in lines:
        if not isinstance(line, dict) or _should_ignore_line(line):
            continue
        fixed = _cohere_line(line)
        if fixed is None:
            rejected += 1
            continue
        coherent.append({"numero_ligne": line_num, **fixed})
        line_num += 10

    if not coherent:
        return []
    if len(coherent) == 1 and rejected >= 2:
        return []
    if len(coherent) < math.ceil((len(coherent) + rejected) * 0.5):
        return []
    return coherent


# -------------------------------------------------------------------------
# MAIN EXTRACTION PROMPT
# -------------------------------------------------------------------------

ORDERLINES_PROMPT = """Tu es un extracteur de lignes de commande B2B pour Bosch/ELM LEBLANC (chauffage, climatisation).

TEXTE DU PDF:
---
{text}
---

Extrais TOUTES les lignes de commande (articles commandes) du document.

Regles:
- "Code article" = reference produit Bosch/ELM (souvent 7-10 chiffres, parfois prefixe EL/ELM)
- Ignore les lignes PORT, PORTSFAB, ECOTAXE, ECOTAX, FRAIS DE PORT, PARTICIPATION TRANSPORT
- "Quantite" = nombre d'unites commandees
- "Prix unitaire" = prix net HT par unite (pas le montant total de la ligne)
- Si le document ne contient PAS de lignes de commande (ex: c'est juste un bon de livraison sans detail), retourne un tableau vide []
- Separe bien prix unitaire (par piece) et montant total ligne

Reponds UNIQUEMENT en JSON (pas de markdown, pas de ```):
[{{"code_article": "...", "description": "...", "quantite": ..., "prix_unitaire_ht": ..., "montant_ligne_ht": ..., "date_livraison": "..."}}]

Si aucune ligne article n'est trouvee, reponds: []"""


def llm_extract_orderlines(text: str) -> list[dict]:
    """Extract order lines from PDF text using Sonnet 4.

    Returns list of dicts with keys:
        - numero_ligne: generated (10, 20, 30...)
        - code_article: cleaned Bosch article number
        - code_article_raw: original from document
        - description: article description
        - quantite: quantity (float)
        - prix_unitaire_ht: net unit price (float)
        - montant_ligne_ht: line total (float)
        - date_livraison: delivery date if present
    """
    if not text or len(text) < 50:
        return []

    truncated = text[:4000] if len(text) > 4000 else text
    prompt = ORDERLINES_PROMPT.format(text=truncated)

    raw = _call_llm(prompt, max_tokens=1500)
    lines = _parse_json(raw)

    if not lines or not isinstance(lines, list):
        return []

    result = _finalize_llm_lines(lines)

    logger.info(f"LLM orderlines: {len(result)} lines extracted")
    return result
