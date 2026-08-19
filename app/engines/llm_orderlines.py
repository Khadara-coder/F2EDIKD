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
    if ratio < 1 or ratio > 10000:
        return None
    rounded_int = round(ratio)
    # Allow tiny epsilon for floating point arithmetic (e.g. 445.38/222.69 = 1.9999...)
    if abs(ratio - rounded_int) < 1e-6:
        return float(rounded_int)
    return None


def _to_natural_qty(value: float | None) -> Optional[float]:
    """Enforce business rule: quantities are always exact natural integers >= 1.
    Tiny epsilon (1e-6) allowed for floating point imprecision.
    Rejects genuine non-integers: 0.5, 1.5, 1.98, 3.072.
    """
    if value is None or value <= 0:
        return None
    rounded = round(value)
    if rounded < 1:
        return None
    # Allow tiny epsilon for floating point arithmetic
    if abs(value - rounded) < 1e-6:
        return float(rounded)
    return None  # Genuine non-integer - reject


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
    # Fallback: only accept natural integers
    if qty is None and total is not None and price is not None and price > 0:
        qty = _to_natural_qty(total / price)

    # Enforce business rule: quantity must be a natural integer
    if qty is not None:
        qty = _to_natural_qty(qty)

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
    line_num = 10
    for line in lines:
        if not isinstance(line, dict) or _should_ignore_line(line):
            continue
        fixed = _cohere_line(line)
        if fixed is None:
            continue
        coherent.append({"numero_ligne": line_num, **fixed})
        line_num += 10
    return coherent


# -------------------------------------------------------------------------
# MAIN EXTRACTION PROMPT
# -------------------------------------------------------------------------

ORDERLINES_PROMPT = """Tu es un extracteur de lignes de commande B2B pour Bosch/ELM LEBLANC (chauffage, climatisation).

TEXTE DU PDF (document complet ou extrait de pages):
---
{text}
---

Extrais TOUTES les lignes de commande commerciales du document. Parcours toutes les pages fournies. N'omets aucune ligne article.

Regles:
- "Code article" = reference produit Bosch/ELM (souvent 7-10 chiffres, parfois prefixe EL/ELM)
- Ignore les lignes PORT, PORTSFAB, ECOTAXE, ECOTAX, FRAIS DE PORT, PARTICIPATION TRANSPORT
- Le meme code article peut apparaitre plusieurs fois (quantites ou bons client differents) : conserve CHAQUE ligne distincte
- Une mention "REMPLACE 77..." n'est PAS une ligne : c'est une note sur l'article precedent
- "Quantite" = nombre d'unites (souvent petit entier). Ne pas inverser quantite et prix
- "Prix unitaire" = prix net HT par unite (pas le montant total de la ligne)
- "montant_ligne_ht" = quantite x prix unitaire
- Si le document ne contient PAS de lignes de commande, retourne un tableau vide []

Reponds UNIQUEMENT en JSON (pas de markdown, pas de ```):
[{{"code_article": "...", "description": "...", "quantite": ..., "prix_unitaire_ht": ..., "montant_ligne_ht": ..., "customer_reference": "", "date_livraison": "..."}}]

Si aucune ligne article n'est trouvee, reponds: []"""


LLM_TEXT_CHUNK_CHARS = 14000
LLM_ORDERLINES_MAX_TOKENS = 4000


def _split_text_for_llm(text: str, max_chars: int = LLM_TEXT_CHUNK_CHARS) -> list[str]:
    """Keep the full document: one chunk if short, otherwise page/line slices."""
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= max_chars:
        return [raw]

    pages = re.split(r"(?=^===== PAGE \d+ =====)", raw, flags=re.MULTILINE)
    pages = [part.strip() for part in pages if part.strip()]
    if len(pages) <= 1:
        pages = raw.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for line in pages:
            extra = len(line) + 1
            if current and size + extra > max_chars:
                chunks.append("\n".join(current))
                current = [line]
                size = extra
            else:
                current.append(line)
                size += extra
        if current:
            chunks.append("\n".join(current))
        return chunks or [raw]

    chunks = []
    current = ""
    for page in pages:
        if current and len(current) + 2 + len(page) > max_chars:
            chunks.append(current)
            current = page
        else:
            current = f"{current}\n\n{page}" if current else page
    if current:
        chunks.append(current)
    return chunks


def _line_key(line: dict) -> tuple:
    return (
        str(line.get("code_article") or "").strip(),
        line.get("quantite"),
        line.get("montant_ligne_ht"),
        str(line.get("customer_reference") or "").strip(),
    )


def llm_extract_orderlines(text: str) -> list[dict]:
    """Extract order lines from the full PDF text using the LLM.

    Long documents are processed in successive chunks so later pages are not dropped.
    """
    if not text or len(text) < 50:
        return []

    merged: list[dict] = []
    seen: set[tuple] = set()
    for chunk in _split_text_for_llm(text):
        prompt = ORDERLINES_PROMPT.format(text=chunk)
        raw = _call_llm(prompt, max_tokens=LLM_ORDERLINES_MAX_TOKENS)
        parsed = _parse_json(raw)
        if not parsed or not isinstance(parsed, list):
            continue
        for line in _finalize_llm_lines(parsed):
            key = _line_key(line)
            if not key[0] or key in seen:
                continue
            seen.add(key)
            merged.append(line)

    for index, line in enumerate(merged, start=1):
        line["numero_ligne"] = index * 10

    logger.info("LLM orderlines: %s lines extracted from full document", len(merged))
    return merged
