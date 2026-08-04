"""AI-powered PDF reader for EDIFACT Orders Generator.

Pipeline:
1. Extract native PDF text with pdfplumber.
2. Correct doubled-character OCR artifacts when detected.
3. Use Databricks Model Serving over HTTP as structured extraction fallback.
4. Parse and sanitize JSON.
5. Filter shipping/eco-tax lines and normalize dates.

Databricks is used as a remote LLM provider only; this module does not require
mlflow or a Databricks runtime.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("edifact.ai_pdf_reader")

IGNORED_ARTICLE_PATTERNS = (
    "PORT",
    "PORTSFAB",
    "PORT FOURNISSEUR",
    "ECOTAX",
    "ECOTAXE",
    "FRAIS DE PORT",
    "PARTICIPATION TRANSPORT",
)

_MIN_TEXT_CHARS = 80
_FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

_EXTRACTION_SYSTEM = """\
Tu es un extracteur strict de bons de commande B2B francais pour Bosch Thermotechnologie France.
L'expediteur/vendeur (ELM LEBLANC, Bosch Thermotechnologie, 124-126 rue Stalingrad Drancy) est ignore.
Reponds UNIQUEMENT en JSON valide, sans markdown:

{
  "status": "ok",
  "order_key": "...",
  "document_date": "YYYY-MM-DD ou null",
  "delivery_date": "YYYY-MM-DD ou null",
  "buyer_vat": "...",
  "buyer_name": "...",
  "buyer_siren": "...",
  "shipto_name": "...",
  "shipto_address": "...",
  "shipto_postal": "...",
  "shipto_city": "...",
  "confidence": 0.0,
  "line_items": [
    {
      "article_code": "...",
      "description": "...",
      "qty": 0.0,
      "unit_price": 0.0,
      "delivery_date": null
    }
  ]
}

Regles:
- Ne pas retourner les lignes PORT, PORTSFAB, ECOTAXE, FRAIS DE PORT, ECOTAX.
- Supprimer le prefixe EL ou ELM des codes articles.
- confidence = 0.0-1.0 refletant la fiabilite de l'extraction.
- Si un champ est absent ou illisible: null."""


def _model_endpoint() -> str:
    return os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")


def _call_llm(prompt: str, max_tokens: int = 2000) -> Optional[str]:
    """Call the configured Databricks Model Serving endpoint via shared HTTP client."""
    try:
        from src.llm_client import llm_call

        result = llm_call(prompt, system=_EXTRACTION_SYSTEM, max_tokens=max_tokens, endpoint=_model_endpoint())
        if result is None and _model_endpoint() != _FALLBACK_ENDPOINT:
            return llm_call(prompt, system=_EXTRACTION_SYSTEM, max_tokens=max_tokens, endpoint=_FALLBACK_ENDPOINT)
        return result
    except Exception as exc:
        log.warning("AI extraction LLM call failed: %s", exc)
        return None


def _parse_json_response(raw: str) -> Optional[dict]:
    """Strip markdown fences and parse a JSON object from an LLM response."""
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _norm_doubled_chars(text: str) -> str:
    """Fix doubled-character OCR artifacts such as LLYYOONN -> LYON."""
    if not text:
        return text
    doubled = sum(1 for i in range(len(text) - 1) if text[i] == text[i + 1] and text[i].isalpha())
    if doubled / max(len(text), 1) < 0.30:
        return text

    result: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if i + 1 < len(text) and text[i + 1] == char and char.isalpha():
            result.append(char)
            i += 2
        else:
            result.append(char)
            i += 1
    return "".join(result)


def _clean_article_code(raw: str) -> str:
    """Remove EL/ELM prefixes from Bosch article codes."""
    return re.sub(r"^(ELM?\s+)", "", (raw or "").strip(), flags=re.IGNORECASE)


def _norm_date(value: Optional[str]) -> Optional[str]:
    """Normalize common date formats to CCYYMMDD."""
    if not value:
        return None
    raw = str(value).strip()

    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if match:
        return match.group(1) + match.group(2) + match.group(3)

    match = re.match(r"^(\d{2})[/\-. ](\d{2})[/\-. ](\d{4})$", raw)
    if match:
        return match.group(3) + match.group(2) + match.group(1)

    if re.match(r"^\d{8}$", raw):
        return raw
    return None


def _filter_lines(line_items: list[dict]) -> list[dict]:
    """Remove shipping/eco-tax lines and normalize article codes."""
    clean: list[dict] = []
    for line in line_items:
        if not isinstance(line, dict):
            continue

        article = _clean_article_code(line.get("article_code") or "")
        description = str(line.get("description") or "").strip()
        if not article and not description:
            continue

        upper_article = article.upper()
        upper_description = description.upper()
        if any(upper_article.startswith(pat) or upper_description.startswith(pat) for pat in IGNORED_ARTICLE_PATTERNS):
            log.debug("Skipping ignored article: art=%r desc=%r", article, description)
            continue

        try:
            qty = float(line.get("qty") or line.get("quantity") or 1)
            price = float(line.get("unit_price") or line.get("price") or 0)
        except (TypeError, ValueError):
            qty, price = 1.0, 0.0

        clean.append(
            {
                "customer_article": article,
                "description": description,
                "quantity": str(qty),
                "unit_price": str(price),
                "ean": "",
            }
        )
    return clean


def compute_pdf_hash(path: Path) -> str:
    """SHA256 of the first 128 KB of raw PDF bytes."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read(131072)).hexdigest()


def extract_text_from_pdf(path: Path) -> tuple[str, str]:
    """Extract text from a PDF and return (text, source)."""
    try:
        import pdfplumber

        with pdfplumber.open(path) as doc:
            pages = [page.extract_text() or "" for page in doc.pages[:4]]
        raw = "\n".join(pages).strip()
    except Exception as exc:
        log.warning("pdfplumber failed on %s: %s", path.name, exc)
        raw = ""

    if not raw:
        return "", "empty"

    corrected = _norm_doubled_chars(raw)
    if corrected != raw:
        log.info("%s: doubled-character OCR correction applied", path.name)
        return corrected, "pdf_ocr_doubled"
    return raw, "pdf_text"


def ai_extract_po(pdf_path: Path) -> dict[str, Any]:
    """Run the AI extraction pipeline for one purchase-order PDF."""
    text, source = extract_text_from_pdf(pdf_path)
    pdf_hash = compute_pdf_hash(pdf_path)

    result: dict[str, Any] = {
        "order_number": None,
        "order_date": None,
        "raw_text": text,
        "buyer_text": "",
        "delivery_text": "",
        "lines": [],
        "confidence": 0.0,
        "source": source,
        "pdf_hash": pdf_hash,
        "ai_used": False,
    }

    if not text or len(text) < _MIN_TEXT_CHARS:
        log.info("%s: text too short (%d chars), AI cannot extract from empty PDF", pdf_path.name, len(text))
        result["rejection_reason"] = "PDF_PARSE_FAILURE"
        return result

    prompt = f"PDF ({pdf_path.name}):\n{text[:3800]}"
    raw_response = _call_llm(prompt, max_tokens=2000)
    if not raw_response:
        log.warning("%s: AI endpoint returned no response", pdf_path.name)
        return result

    parsed = _parse_json_response(raw_response)
    if not parsed:
        log.warning("%s: could not parse AI JSON response: %s", pdf_path.name, raw_response[:200])
        return result

    result["ai_used"] = True
    result["confidence"] = float(parsed.get("confidence") or 0.0)
    result["order_number"] = str(parsed.get("order_key") or "").strip() or None
    result["order_date"] = _norm_date(parsed.get("document_date"))
    result["delivery_date"] = _norm_date(parsed.get("delivery_date"))

    buyer_parts = [
        parsed.get("buyer_vat") or "",
        parsed.get("buyer_name") or "",
        parsed.get("buyer_siren") or "",
    ]
    result["buyer_text"] = "\n".join(part for part in buyer_parts if part)

    delivery_parts = [
        parsed.get("shipto_name") or "",
        parsed.get("shipto_address") or "",
        parsed.get("shipto_postal") or "",
        parsed.get("shipto_city") or "",
    ]
    result["delivery_text"] = "\n".join(part for part in delivery_parts if part)
    result["lines"] = _filter_lines(parsed.get("line_items") or [])

    result["buyer_vat"] = parsed.get("buyer_vat")
    result["buyer_name"] = parsed.get("buyer_name")
    result["shipto_postal"] = parsed.get("shipto_postal")
    result["shipto_city"] = parsed.get("shipto_city")
    result["shipto_address"] = parsed.get("shipto_address")

    log.info(
        "%s: AI extraction complete - order=%s conf=%.2f lines=%d",
        pdf_path.name,
        result["order_number"],
        result["confidence"],
        len(result["lines"]),
    )
    return result
