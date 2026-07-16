"""AI-powered PDF reader for EDIFACT Orders Generator.

Pipeline (mirrors FILE2EDI app/engine.py + app/engines/llm_resolver.py):
  1. pdfplumber — native text extraction (higher quality than pypdf for French PDFs)
  2. Doubled-char OCR artifact correction (e.g. LLYYOONN -> LYON)
  3. databricks-gpt-oss-120b — structured extraction fallback when regex misfires
  4. JSON sanitisation: strip markdown fences, clean EL/ELM article prefixes,
     filter IGNORED_ARTICLE_PATTERNS (PORT, ECOTAXE, FRAIS DE PORT…)
  5. Date normalisation: DD/MM/YYYY → CCYYMMDD

Endpoint: databricks-gpt-oss-120b via mlflow.deployments (primary)
          OR requests POST with _auth_headers() (app container fallback)

Returns a dict compatible with pdf_extractor.extract_order() so it can be
consumed directly by engine_adapter.process_pdf_to_edifact().
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

# ── Bosch/Esker constants (mirrors FILE2EDI edifact_generator.py) ─────────────
IGNORED_ARTICLE_PATTERNS = (
    "PORT", "PORTSFAB", "PORT FOURNISSEUR",
    "ECOTAX", "ECOTAXE", "FRAIS DE PORT",
    "PARTICIPATION TRANSPORT",
)

# ── Model endpoint ─────────────────────────────────────────────────────────────
_FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def _model_endpoint() -> str:
    return os.environ.get("DATABRICKS_MODEL_ENDPOINT", "databricks-gpt-oss-120b")


def _ai_endpoint_url() -> str:
    host = os.environ.get(
        "DATABRICKS_HOST",
        "https://adb-5555213114570927.7.azuredatabricks.net",
    ).rstrip("/")
    return host + f"/serving-endpoints/{_model_endpoint()}/invocations"

# Minimum chars before calling the AI endpoint at all
_MIN_TEXT_CHARS = 80
# Trigger AI if pdfplumber text is shorter than this (likely scanned/empty)
_SCANNED_THRESHOLD = 150


# ── LLM system prompt (adapted from FILE2EDI llm_resolver.py) ─────────────────
_EXTRACTION_SYSTEM = """\
Tu es un extracteur strict de bons de commande B2B français pour Bosch Thermotechnologie France.
L'expéditeur/vendeur (ELM LEBLANC, Bosch Thermotechnologie, 124-126 rue Stalingrad Drancy) est ignoré.
Réponds UNIQUEMENT en JSON valide, sans markdown, sans ```:

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

Règles:
- Ne pas retourner les lignes PORT, PORTSFAB, ECOTAXE, FRAIS DE PORT, ECOTAX.
- Supprimer le préfixe EL ou ELM des codes articles (ex: "EL 87167432990" → "87167432990").
- confidence = 0.0–1.0 reflétant la fiabilité de l'extraction.
- Si un champ est absent ou illisible: null."""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _text_from_content(content: Any) -> str:
    """Extract answer text from gpt-oss-120b reasoning-model content blocks.

    The model returns a list:  [{type:'reasoning',...}, {type:'text', text:'...'}]
    Only the 'text' block contains the actual answer.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
        # Fallback: collect reasoning summaries if no text block
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "reasoning":
                for s in block.get("summary", []):
                    if s.get("type") == "summary_text":
                        parts.append(s.get("text", ""))
        return " ".join(parts)
    return str(content)


def _call_llm(prompt: str, max_tokens: int = 2000) -> Optional[str]:
    """Call gpt-oss-120b via mlflow.deployments (primary) or requests (fallback).

    Returns the raw text response or None on failure.
    """
    # ── Primary: mlflow.deployments (works inside Databricks notebook / cluster) ──
    try:
        import mlflow.deployments
        client = mlflow.deployments.get_deploy_client("databricks")
        resp = client.predict(
            endpoint=_model_endpoint(),
            inputs={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 1,   # Required for reasoning models
            },
        )
        text = _text_from_content(resp["choices"][0]["message"]["content"])
        if text.strip():
            return text.strip()
    except Exception as exc:
        log.debug("mlflow.deployments call failed, trying requests: %s", exc)

    # ── Fallback: direct HTTP (app service-principal auth) ──
    try:
        import requests as _req
        from importlib import import_module
        _server_mod = import_module("server") if "server" in dir() else None
        auth_fn = getattr(_server_mod, "_auth_headers", None)
        if auth_fn is None:
            token = os.environ.get("DATABRICKS_TOKEN", "")
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}
        else:
            headers = auth_fn()
        resp = _req.post(
            _ai_endpoint_url(),
            headers=headers,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw_resp = resp.json()
        content = raw_resp["choices"][0]["message"]["content"]
        return _text_from_content(content).strip()
    except Exception as exc:
        log.warning("AI extraction HTTP call failed: %s", exc)
        return None


def _parse_json_response(raw: str) -> Optional[dict]:
    """Strip markdown fences and parse JSON from LLM response."""
    if not raw:
        return None
    cleaned = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find the first JSON object in the text
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _norm_doubled_chars(text: str) -> str:
    """Fix doubled-char OCR artifacts (LLYYOONN -> LYON).

    Only applied when > 30% of consecutive char pairs are doubled.
    """
    if not text:
        return text
    doubled = sum(
        1 for i in range(len(text) - 1)
        if text[i] == text[i + 1] and text[i].isalpha()
    )
    if doubled / max(len(text), 1) < 0.30:
        return text   # Not a doubled-char document
    result: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if i + 1 < len(text) and text[i + 1] == c and c.isalpha():
            result.append(c)
            i += 2
        else:
            result.append(c)
            i += 1
    return "".join(result)


def _clean_article_code(raw: str) -> str:
    """Remove EL/ELM prefix from Bosch article codes (FILE2EDI business rule)."""
    return re.sub(r"^(ELM?\s+)", "", (raw or "").strip(), flags=re.IGNORECASE)


def _norm_date(value: Optional[str]) -> Optional[str]:
    """Normalise various date formats to CCYYMMDD string (for EDIFACT DTM segments)."""
    if not value:
        return None
    raw = str(value).strip()
    # YYYY-MM-DD (ISO)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m = re.match(r"^(\d{2})[/\-.](\ d{2})[/\-.\ ](\d{4})$", raw)
    if m:
        return m.group(3) + m.group(2) + m.group(1)
    # Already CCYYMMDD
    if re.match(r"^\d{8}$", raw):
        return raw
    return None


def _filter_lines(line_items: list[dict]) -> list[dict]:
    """Remove PORT/ECOTAXE/FRAIS DE PORT lines; clean article codes."""
    clean = []
    for li in line_items:
        art = _clean_article_code(li.get("article_code") or "")
        desc = (li.get("description") or "").strip().upper()
        if not art and not desc:
            continue
        # Skip ignored patterns
        upper_art = art.upper()
        upper_desc = desc.upper()
        skip = False
        for pat in IGNORED_ARTICLE_PATTERNS:
            if upper_art.startswith(pat) or upper_desc.startswith(pat):
                skip = True
                break
        if skip:
            log.debug("Skipping ignored article: art=%r desc=%r", art, desc)
            continue
        try:
            qty = float(li.get("qty") or li.get("quantity") or 1)
            price = float(li.get("unit_price") or li.get("price") or 0)
        except (TypeError, ValueError):
            qty, price = 1.0, 0.0
        clean.append({
            "customer_article": art,
            "description":      li.get("description", ""),
            "quantity":         str(qty),
            "unit_price":       str(price),
            "ean":              "",
        })
    return clean


def compute_pdf_hash(path: Path) -> str:
    """SHA256 of raw PDF bytes (first 128 KB for speed)."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read(131072)).hexdigest()


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_text_from_pdf(path: Path) -> tuple[str, str]:
    """Extract text from *path* using pdfplumber.

    Returns (text, source) where source is:
      pdf_text          — native text layer extracted cleanly
      pdf_ocr_doubled   — native text after doubled-char correction
      empty             — no text (scanned/image PDF)
    """
    try:
        import pdfplumber
        with pdfplumber.open(path) as doc:
            pages = [pg.extract_text() or "" for pg in doc.pages[:4]]
        raw = "\n".join(pages).strip()
    except Exception as exc:
        log.warning("pdfplumber failed on %s (%s), falling back to path str", path.name, exc)
        raw = ""

    if not raw:
        return "", "empty"

    corrected = _norm_doubled_chars(raw)
    if corrected != raw:
        log.info("%s: doubled-char OCR correction applied", path.name)
        return corrected, "pdf_ocr_doubled"
    return raw, "pdf_text"


def ai_extract_po(pdf_path: Path) -> dict[str, Any]:
    """Full AI extraction pipeline for a purchase-order PDF.

    1. pdfplumber text extraction
    2. (optional) doubled-char correction
    3. gpt-oss-120b structured extraction
    4. JSON sanitisation and date normalisation
    5. Port/eco-tax line filtering + EL prefix removal

    Returns a dict compatible with pdf_extractor.extract_order():
      order_number, order_date, raw_text, buyer_text, delivery_text,
      lines, confidence, source, pdf_hash, ai_used
    """
    text, source = extract_text_from_pdf(pdf_path)
    pdf_hash = compute_pdf_hash(pdf_path)

    base_result: dict[str, Any] = {
        "order_number":    None,
        "order_date":      None,
        "raw_text":        text,
        "buyer_text":      "",
        "delivery_text":   "",
        "lines":           [],
        "confidence":      0.0,
        "source":          source,
        "pdf_hash":        pdf_hash,
        "ai_used":         False,
    }

    if not text or len(text) < _MIN_TEXT_CHARS:
        log.info("%s: text too short (%d chars), AI cannot extract from empty PDF",
                 pdf_path.name, len(text))
        base_result["rejection_reason"] = "PDF_PARSE_FAILURE"
        return base_result

    # ── AI Extraction ────────────────────────────────────────────────────────
    prompt = (
        f"{_EXTRACTION_SYSTEM}\n\n"
        f"PDF ({pdf_path.name}):\n{text[:3800]}"
    )
    raw_response = _call_llm(prompt, max_tokens=2000)
    if not raw_response:
        log.warning("%s: AI endpoint returned no response", pdf_path.name)
        return base_result

    parsed = _parse_json_response(raw_response)
    if not parsed:
        log.warning("%s: could not parse AI JSON response: %s", pdf_path.name, raw_response[:200])
        return base_result

    base_result["ai_used"] = True
    base_result["confidence"] = float(parsed.get("confidence") or 0.0)

    # ── Order header ─────────────────────────────────────────────────────────
    base_result["order_number"] = (parsed.get("order_key") or "").strip() or None
    doc_date  = _norm_date(parsed.get("document_date"))
    base_result["order_date"]   = doc_date

    # ── Build buyer_text / delivery_text strings for matcher.py ─────────────
    buyer_parts = [
        parsed.get("buyer_vat") or "",
        parsed.get("buyer_name") or "",
        parsed.get("buyer_siren") or "",
    ]
    base_result["buyer_text"] = "\n".join(p for p in buyer_parts if p)

    delivery_parts = [
        parsed.get("shipto_name")    or "",
        parsed.get("shipto_address") or "",
        parsed.get("shipto_postal")  or "",
        parsed.get("shipto_city")    or "",
    ]
    base_result["delivery_text"] = "\n".join(p for p in delivery_parts if p)

    # ── Delivery date ─────────────────────────────────────────────────────────
    base_result["delivery_date"] = _norm_date(parsed.get("delivery_date"))

    # ── Line items ────────────────────────────────────────────────────────────
    raw_lines = parsed.get("line_items") or []
    base_result["lines"] = _filter_lines(raw_lines)

    # ── Extra keys for richer UI display ─────────────────────────────────────
    base_result["buyer_vat"]       = parsed.get("buyer_vat")
    base_result["buyer_name"]      = parsed.get("buyer_name")
    base_result["shipto_postal"]   = parsed.get("shipto_postal")
    base_result["shipto_city"]     = parsed.get("shipto_city")
    base_result["shipto_address"]  = parsed.get("shipto_address")

    log.info("%s: AI extraction complete — order=%s conf=%.2f lines=%d",
             pdf_path.name, base_result["order_number"],
             base_result["confidence"], len(base_result["lines"]))
    return base_result
