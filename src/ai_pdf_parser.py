"""AI-powered PDF parser for EDIFACT Orders Generator.

Two-stage pipeline:
  1. Text extraction: pdfplumber (primary) → pypdf fallback → OCR hint.
  2. Structured parsing: POST extracted text to the configured LLM endpoint.

Returns a dict whose keys match build_orders_message() parameters:
  order      → {order_number, order_date}
  soldto_row → {soldto, name, street, city, postal_code, country}
  shipto_row → {shipto, name, street, city, postal_code, country}
  lines      → [{matnr, description, quantity, unit_price, original_article}]
  confidence, extraction_method, raw_text_chars
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("edifact.ai_pdf_parser")

# ── Normalisation helpers ──────────────────────────────────────────────────────

def _norm_vat(s: str) -> str:
    """Uppercase + strip non-alphanumeric. 'FR 12 345 678 901' → 'FR12345678901'."""
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()


def _norm_date(value: str) -> str:
    """Convert various date formats → CCYYMMDD.

    Handles: DD/MM/YYYY, YYYY-MM-DD, YYYYMMDD, DD-MM-YY (French default century 20xx).
    """
    s = str(value or "").strip()
    if not s:
        return ""
    # Remove non-digit/separator noise
    s = re.sub(r"[^0-9/\-\.\s]", "", s).strip()
    # YYYYMMDD compact
    m = re.match(r"^(\d{8})$", s)
    if m:
        return m.group(1)
    # YYYY[-/.]MM[-/.]DD
    m = re.match(r"^(\d{4})[/\-\.\s](\d{1,2})[/\-\.\s](\d{1,2})$", s)
    if m:
        return m.group(1) + m.group(2).zfill(2) + m.group(3).zfill(2)
    # DD[-/.]MM[-/.]YYYY (French)
    m = re.match(r"^(\d{1,2})[/\-\.\s](\d{1,2})[/\-\.\s](\d{4})$", s)
    if m:
        return m.group(3) + m.group(2).zfill(2) + m.group(1).zfill(2)
    # DD[-/.]MM[-/.]YY → 20YY
    m = re.match(r"^(\d{1,2})[/\-\.\s](\d{1,2})[/\-\.\s](\d{2})$", s)
    if m:
        return "20" + m.group(3) + m.group(2).zfill(2) + m.group(1).zfill(2)
    return ""


def _norm_num(v: Any) -> float:
    """French decimal string → float.  '1.234,56' → 1234.56, '10,5' → 10.5."""
    s = str(v or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── Stage 1: Text extraction ───────────────────────────────────────────────────

def extract_text_with_pdfplumber(pdf_path: Path) -> str:
    """Extract text using pdfplumber (handles complex table layouts).

    Returns full text or empty string on failure.
    """
    try:
        import pdfplumber  # type: ignore
        pages: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                # Extract structured words to preserve column order
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                if words:
                    # Group by y-position (line), sort by x within each line
                    from collections import defaultdict
                    lines_map: dict[float, list] = defaultdict(list)
                    for w in words:
                        bucket = round(w["top"] / 5) * 5  # 5-pt bucket
                        lines_map[bucket].append(w)
                    text_lines = []
                    for y in sorted(lines_map):
                        row_words = sorted(lines_map[y], key=lambda w: w["x0"])
                        text_lines.append(" ".join(w["text"] for w in row_words))
                    pages.append("\n".join(text_lines))
                else:
                    # Fallback: plain page text
                    t = page.extract_text() or ""
                    if t.strip():
                        pages.append(t)
        text = "\n\n".join(pages).strip()
        log.info("pdfplumber extracted %d chars from %s", len(text), pdf_path.name)
        return text
    except Exception as exc:
        log.warning("pdfplumber failed (%s): %s", type(exc).__name__, exc)
        return ""


def extract_text_with_pypdf(pdf_path: Path) -> str:
    """Fallback text extraction using pypdf/PyPDF2."""
    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(str(pdf_path))
        text = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        log.info("pypdf extracted %d chars from %s", len(text), pdf_path.name)
        return text
    except Exception as exc:
        log.warning("pypdf failed (%s): %s", type(exc).__name__, exc)
        return ""


def extract_pdf_text(pdf_path: Path) -> tuple[str, str]:
    """Extract text from PDF, trying pdfplumber first then pypdf.

    Returns (text, method) where method ∈ {"pdfplumber", "pypdf", "empty"}.
    """
    text = extract_text_with_pdfplumber(pdf_path)
    if len(text.strip()) > 80:
        return text, "pdfplumber"
    text = extract_text_with_pypdf(pdf_path)
    if len(text.strip()) > 80:
        return text, "pypdf"
    # Very sparse text — likely scanned; return what we have
    combined = text or extract_text_with_pdfplumber(pdf_path)
    return combined, "sparse" if combined else "empty"


# ── Stage 2: AI structured extraction ─────────────────────────────────────────

_AI_SYSTEM_PROMPT = """\
You are a strict purchase-order field extractor for Bosch Thermotechnologie France.
Input is raw text extracted from a customer PDF purchase order (may include noise).
Return ONLY a single valid JSON object — no markdown fences, no explanation:
{
  "status": "ok",
  "order_key": "<customer PO number>",
  "document_date": "<DD/MM/YYYY or YYYY-MM-DD or null>",
  "delivery_date": "<DD/MM/YYYY or YYYY-MM-DD or null>",
  "soldto_keys": {
    "vat": "<FR12345678901 or empty>",
    "name": "<company name>",
    "postal": "<5-digit postal code>",
    "city": "<city>",
    "street": "<street address>"
  },
  "shipto_keys": {
    "name": "<delivery company name>",
    "postal": "<5-digit postal code>",
    "city": "<city>",
    "street": "<delivery street>",
    "country": "FR"
  },
  "line_items": [
    {
      "line_no": 1,
      "article_code": "<article code as printed on PO>",
      "description": "<product description>",
      "qty": 1,
      "unit_price": 0.00,
      "unit": "PCE"
    }
  ],
  "confidence": 0.90
}
Rules:
- Extract ALL article lines (skip freight lines: PORT, PORTSFAB, ECOTAXE, FRAIS DE PORT).
- For French decimals: 1.234,56 means 1234.56.
- For dates in DD/MM/YYYY format, preserve as-is.
- confidence: 0.0–1.0, reflect how complete the extraction is.
- If a field is unknown, use empty string or null — never invent data."""


def _sanitize_json_response(raw: str) -> dict:
    """Parse LLM response to dict — handles markdown fences and leading garbage."""
    s = raw.strip()
    # Strip markdown code fences
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"```\s*$", "", s).strip()
    # Find first { … last }
    start = s.find("{")
    end   = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start:end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        log.warning("JSON parse failed: %s — raw: %.200s", exc, raw)
        return {"status": "parse_error", "error": str(exc)}


def call_ai_endpoint(
    text: str,
    headers: dict,
    endpoint_url: str,
    max_tokens: int = 1200,
) -> dict:
    """POST *text* to the LLM endpoint and return the parsed JSON dict."""
    import requests  # type: ignore

    payload = {
        "messages": [
            {"role": "system", "content": _AI_SYSTEM_PROMPT},
            {"role": "user",   "content": f"PURCHASE ORDER TEXT:\n\n{text[:6000]}"},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    try:
        resp = requests.post(endpoint_url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _sanitize_json_response(content)
    except Exception as exc:
        log.error("AI endpoint call failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ── Stage 3: Normalise AI output → build_orders_message() parameters ──────────

def _ai_to_build_params(ai: dict, pdf_name: str = "") -> dict:
    """Map AI-extracted dict to build_orders_message() parameter shapes.

    Returns:
        {
          order, soldto_row, shipto_row, lines,
          confidence, extraction_method, warnings
        }
    """
    warnings: list[str] = []

    # ---- order ----
    order_key  = str(ai.get("order_key") or "").strip()
    doc_date   = _norm_date(str(ai.get("document_date") or ""))
    del_date   = _norm_date(str(ai.get("delivery_date") or ""))
    if not order_key:
        warnings.append("order_key missing")
    if not doc_date:
        from datetime import datetime
        doc_date = datetime.now().strftime("%Y%m%d")
        warnings.append("document_date missing — defaulted to today")

    order = {
        "order_number": order_key,
        "order_date":   doc_date,
        "delivery_date": del_date,
    }

    # ---- sold-to ----
    sk = ai.get("soldto_keys") or {}
    vat_norm = _norm_vat(str(sk.get("vat") or ""))
    soldto_row = {
        "soldto":      vat_norm or sk.get("name", pdf_name)[:12],
        "name":        str(sk.get("name",    "") or ""),
        "street":      str(sk.get("street",  "") or ""),
        "city":        str(sk.get("city",    "") or ""),
        "postal_code": str(sk.get("postal",  "") or ""),
        "country":     "FR",
    }
    if not soldto_row["name"]:
        warnings.append("soldto name missing")

    # ---- ship-to ----
    shk = ai.get("shipto_keys") or {}
    shipto_row = {
        "shipto":      "",  # no SAP code available from AI
        "name":        str(shk.get("name",    "") or soldto_row["name"]),
        "street":      str(shk.get("street",  "") or soldto_row["street"]),
        "city":        str(shk.get("city",    "") or soldto_row["city"]),
        "postal_code": str(shk.get("postal",  "") or soldto_row["postal_code"]),
        "country":     str(shk.get("country", "FR") or "FR"),
    }

    # ---- lines ----
    _SKIP = {"PORT", "PORTSFAB", "ECOTAXE", "ECOTAXE", "FRAIS DE PORT",
             "PARTICIPATION TRANSPORT"}
    lines: list[dict] = []
    for item in (ai.get("line_items") or []):
        art = str(item.get("article_code") or "").strip().upper()
        if any(art.startswith(skip) for skip in _SKIP):
            continue
        qty        = _norm_num(item.get("qty", 0))
        unit_price = _norm_num(item.get("unit_price", 0))
        lines.append({
            "matnr":            art,
            "description":      str(item.get("description") or art),
            "quantity":         qty if qty > 0 else 1.0,
            "unit_price":       unit_price,
            "original_article": art,
        })
    if not lines:
        warnings.append("no valid article lines extracted")

    return {
        "order":              order,
        "soldto_row":         soldto_row,
        "shipto_row":         shipto_row,
        "lines":              lines,
        "confidence":         float(ai.get("confidence", 0.5)),
        "warnings":           warnings,
        "raw_ai":             ai,
    }


# ── Main public entry point ────────────────────────────────────────────────────

def parse_pdf_with_ai(
    pdf_path: Path,
    headers: dict,
    endpoint_url: str,
) -> dict:
    """Full pipeline: pdfplumber → AI endpoint → normalised build params.

    Returns the dict from _ai_to_build_params() plus:
      raw_text_chars, extraction_method.
    Never raises — errors appear in warnings/raw_ai fields.
    """
    pdf_path = Path(pdf_path)
    text, method = extract_pdf_text(pdf_path)
    log.info("PDF %s: %d chars via %s", pdf_path.name, len(text), method)

    if len(text.strip()) < 20:
        return {
            "order": {"order_number": "", "order_date": "", "delivery_date": ""},
            "soldto_row": {}, "shipto_row": {}, "lines": [],
            "confidence": 0.0, "warnings": ["PDF text is empty — may be scanned"],
            "raw_ai": {}, "raw_text_chars": 0, "extraction_method": method,
        }

    ai_raw = call_ai_endpoint(text, headers, endpoint_url)
    params = _ai_to_build_params(ai_raw, pdf_path.stem)
    params["raw_text_chars"]    = len(text)
    params["extraction_method"] = method
    return params
