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

try:
    import mlflow.deployments
    _client = mlflow.deployments.get_deploy_client("databricks")
except Exception:
    _client = None

logger = logging.getLogger(__name__)

MODEL_ENDPOINT = "databricks-claude-sonnet-4"
FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

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
    """Call the LLM endpoint."""
    if _client is None:
        logger.warning("mlflow.deployments client not available")
        return None
    try:
        resp = _client.predict(
            endpoint=endpoint,
            inputs={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"LLM orderlines call failed ({endpoint}): {e}")
        if endpoint != FALLBACK_ENDPOINT:
            try:
                resp = _client.predict(
                    endpoint=FALLBACK_ENDPOINT,
                    inputs={
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0,
                    },
                )
                return resp["choices"][0]["message"]["content"].strip()
            except Exception as e2:
                logger.warning(f"LLM orderlines fallback failed: {e2}")
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

    # Post-process lines
    result = []
    line_num = 10
    for line in lines:
        if not isinstance(line, dict):
            continue
        if _should_ignore_line(line):
            continue

        article_raw = line.get("code_article") or ""
        article_clean = _clean_article_number(article_raw)

        # Skip if no article number
        if not article_clean:
            continue

        qty = _normalize_quantity(line.get("quantite"))
        price = _normalize_price(line.get("prix_unitaire_ht"))
        total = _normalize_price(line.get("montant_ligne_ht"))

        # Infer missing values
        if qty and price and not total:
            total = round(qty * price, 2)
        elif qty and total and not price:
            price = round(total / qty, 2) if qty != 0 else None

        result.append({
            "numero_ligne": line_num,
            "code_article": article_clean,
            "code_article_raw": article_raw.strip(),
            "description": (line.get("description") or "").strip(),
            "quantite": qty,
            "prix_unitaire_ht": price,
            "montant_ligne_ht": total,
            "date_livraison": (line.get("date_livraison") or "").strip() or None,
        })
        line_num += 10

    logger.info(f"LLM orderlines: {len(result)} lines extracted")
    return result
