"""AI-powered order line extraction.

Ported from FILE2EDI app/engines/llm_orderlines.py; uses src.llm_client
instead of a local mlflow.deployments init.

Business rules (from Esker documentation):
- Article numbers are Bosch seller codes, e.g. 7736901359, EL 7716010683
- Strip EL/ELM prefix before returning
- Ignore PORT, PORTSFAB, ECOTAXE, FRAIS DE PORT, PARTICIPATION TRANSPORT
- Decimal separator: comma (FR) or dot
- Line item numbers: generated as 10, 20, 30 …

Public API:
    extract_order_lines(text, filename) → list[dict]
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .llm_client import llm_call
from .edifact_builder import normalize_article_code, format_decimal, parse_date_to_ccyymmdd

log = logging.getLogger("edifact.llm_orderlines")

_SYSTEM_PROMPT = """Tu es un extracteur de lignes de commande B2B pour Bosch Thermotechnologie France.

Règles strictes :
- Les codes articles sont des codes vendeur Bosch/ELM (ex: 7736901359, EL 7716010683).
- Supprimer le préfixe EL ou ELM avant de retourner le code.
- Ignorer les lignes: PORT, PORTSFAB, ECOTAXE, ECOTAX, FRAIS DE PORT, PARTICIPATION TRANSPORT.
- Séparateur décimal: virgule (FR) ou point.

Retourner UNIQUEMENT un tableau JSON valide, sans markdown ni texte autour:
[
  {
    "article_code": "7736901359",
    "description": "CHAUFFE-EAU THERMODYNAMIQUE 200L",
    "qty": 2.0,
    "unit_price": 456.78,
    "delivery_date": null
  }
]"""


def extract_order_lines(
    text:     str,
    filename: str | None = None,
    max_tokens: int = 2000,
) -> list[dict]:
    """Extract order line items from PDF text using the LLM endpoint.

    Returns a list of dicts with keys:
        article_code, description, qty, unit_price, delivery_date

    After extraction, applies normalize_article_code() so EL/ELM prefixes
    are stripped and PORT/ECOTAXE lines are filtered.

    Returns empty list if LLM unavailable or response is unparseable.
    """
    if not text.strip():
        return []

    prompt = f"Fichier: {filename or 'commande.pdf'}\n\n{text[:4000]}"
    raw_items = _call_and_parse(prompt, max_tokens)

    if not isinstance(raw_items, list):
        log.warning("llm_orderlines: unexpected response type %s", type(raw_items))
        return []

    result = []
    line_num = 10
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        raw_code = item.get("article_code") or ""
        code, err, ignore = normalize_article_code(raw_code)

        if ignore:
            log.debug("Skipping ignored article: %r", raw_code)
            continue
        if not code:
            log.debug("Skipping empty article on line: %r", item)
            continue

        result.append({
            "article_code":   code,
            "description":    (item.get("description") or "").strip()[:35],
            "qty":            format_decimal(item.get("qty",  1)) or "1",
            "unit_price":     format_decimal(item.get("unit_price")) or "",
            "delivery_date":  parse_date_to_ccyymmdd(item.get("delivery_date") or ""),
            "line_number":    line_num,
            "_article_warn":  err,
        })
        line_num += 10

    log.info("llm_orderlines: extracted %d valid line(s) from %s", len(result), filename)
    return result


# ─────────────────────────────────────────────────────────────────────────────

def _call_and_parse(prompt: str, max_tokens: int) -> Optional[list]:
    """Call LLM and parse JSON array from response."""
    raw = llm_call(prompt, system=_SYSTEM_PROMPT, max_tokens=max_tokens)
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return parsed.get("lignes") or parsed.get("lines") or []
    except json.JSONDecodeError:
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    log.debug("llm_orderlines: JSON parse failed; raw=%s", cleaned[:300])
    return None
