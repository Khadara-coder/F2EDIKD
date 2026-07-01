"""AI-powered PDF extraction for EDIFACT Orders Generator.

Extraction chain (first that yields enough text wins):
  1. pdfplumber         -- best for complex French PO layouts
  2. PyMuPDF / fitz     -- fallback for encrypted/complex PDFs
  3. PyPDF2 / pypdf     -- lightweight fallback
  4. pytesseract OCR    -- last resort for scanned/image-only PDFs

Parsed text is then sent to databricks-gpt-oss-120b (OpenAI-compat chat API)
for structured field extraction matching the n8n workflow JSON schema.

Public API
----------
extract_pdf_text(pdf_path)           -> (text: str, method: str)
ai_parse_order(text, headers)        -> dict   (raw AI response, sanitized)
extract_order_with_ai(pdf_path, hdrs)-> AiExtractResult
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("edifact.ai_extract")

# Minimum character count to consider text extraction "sufficient"
_MIN_TEXT_LEN = 80


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class AiExtractResult:
    """Structured result returned by extract_order_with_ai()."""
    ok: bool                           # True if AI extraction succeeded
    text_method: str = "none"          # which extractor produced the text
    raw_text: str = ""                 # full extracted PDF text
    ai_json: Optional[dict] = None     # sanitized AI response dict
    order_key: str = ""
    document_date: str = ""            # CCYYMMDD
    delivery_date: str = ""            # CCYYMMDD or ""
    express: bool = False
    confidence: float = 0.0
    soldto_vat: str = ""
    soldto_name: str = ""
    soldto_postal: str = ""
    soldto_city: str = ""
    soldto_street: str = ""
    shipto_name: str = ""
    shipto_postal: str = ""
    shipto_city: str = ""
    shipto_street: str = ""
    line_items: list[dict] = field(default_factory=list)
    error: str = ""


# ── Text extraction (multi-engine) ────────────────────────────────────────────

def _try_pdfplumber(pdf_path: Path) -> str:
    """Extract text via pdfplumber (best for tables and complex layouts)."""
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        log.debug("pdfplumber failed: %s", exc)
        return ""


def _try_fitz(pdf_path: Path) -> str:
    """Extract text via PyMuPDF/fitz."""
    try:
        import fitz  # type: ignore
        doc = fitz.open(str(pdf_path))
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages).strip()
    except Exception as exc:
        log.debug("PyMuPDF failed: %s", exc)
        return ""


def _try_pypdf(pdf_path: Path) -> str:
    """Extract text via pypdf / PyPDF2 (fallback)."""
    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore  # noqa: N813
        reader = PdfReader(str(pdf_path))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        log.debug("pypdf failed: %s", exc)
        return ""


def _try_tesseract(pdf_path: Path) -> str:
    """OCR fallback via pytesseract (requires tesseract + Pillow + PyMuPDF)."""
    try:
        import fitz          # type: ignore
        import pytesseract   # type: ignore
        from PIL import Image  # type: ignore
        import io

        doc  = fitz.open(str(pdf_path))
        bits: list[str] = []
        for page in doc:
            pix  = page.get_pixmap(dpi=200)
            img  = Image.open(io.BytesIO(pix.tobytes("png")))
            lang = "fra+eng"   # French + English
            text = pytesseract.image_to_string(img, lang=lang)
            bits.append(text)
        doc.close()
        return "\n".join(bits).strip()
    except ImportError:
        log.debug("pytesseract/fitz/Pillow not available — skipping OCR")
        return ""
    except Exception as exc:
        log.warning("pytesseract OCR failed: %s", exc)
        return ""


def extract_pdf_text(pdf_path: Path) -> tuple[str, str]:
    """Extract text from *pdf_path* using the first engine that yields enough content.

    Returns
    -------
    (text, method_used)
        method_used is one of: "pdfplumber", "fitz", "pypdf", "tesseract", "none".
    """
    for fn, name in (
        (_try_pdfplumber, "pdfplumber"),
        (_try_fitz,       "fitz"),
        (_try_pypdf,      "pypdf"),
    ):
        text = fn(pdf_path)
        if len(text) >= _MIN_TEXT_LEN:
            log.debug("PDF text extracted via %s (%d chars)", name, len(text))
            return text, name

    # OCR last resort (slow — only for image-only PDFs)
    log.info("All text extractors returned short text — trying OCR")
    text = _try_tesseract(pdf_path)
    if text:
        return text, "tesseract"

    return "", "none"


# ── Date / number normalization helpers (mirrors n8n sanitizer) ───────────────

def _norm_date(v: str) -> str:
    """Normalize various date formats to CCYYMMDD. Returns '' on failure."""
    if not v:
        return ""
    s = re.sub(r"[^0-9/\-\.\s]", "", str(v).strip())
    # compact 8-digit: 20260528
    m = re.match(r"^(\d{8})$", s)
    if m:
        return m.group(1)
    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^(\d{4})[/\-\.\s](\d{1,2})[/\-\.\s](\d{1,2})$", s)
    if m:
        return m.group(1) + m.group(2).zfill(2) + m.group(3).zfill(2)
    # DD/MM/YYYY (French)
    m = re.match(r"^(\d{1,2})[/\-\.\s](\d{1,2})[/\-\.\s](\d{4})$", s)
    if m:
        return m.group(3) + m.group(2).zfill(2) + m.group(1).zfill(2)
    return ""


def _norm_vat(v: str) -> str:
    """Uppercase, strip non-alphanumeric."""
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def _norm_txt(v: str) -> str:
    return str(v or "").strip()


# ── AI parse ─────────────────────────────────────────────────────────────────

# Extraction prompt mirrors the n8n workflow's "API: parse PDF" node
_EXTRACT_SYSTEM = """\
You are a strict order-document extractor for Bosch Thermotechnologie France.
Return ONE JSON object only with these exact keys (no markdown, no explanation):
{
  "status": "ok",
  "order_key": "customer PO number",
  "document_date": "CCYYMMDD or null",
  "delivery_date_doc": "CCYYMMDD or null",
  "express": false,
  "confidence": 0.95,
  "soldto_keys": {
    "vat": "FR-VAT or similar",
    "name": "company name",
    "postal": "postal code",
    "city": "city",
    "street": "street address"
  },
  "shipto_keys": {
    "name": "delivery company name",
    "postal": "delivery postal code",
    "city": "delivery city",
    "street": "delivery street"
  },
  "line_items": [
    {
      "line_no": 1,
      "customer_article": "article code",
      "description": "article description",
      "quantity": "1",
      "unit_price": "0.00",
      "ean": ""
    }
  ]
}
Use null for any field not found. Strict JSON only — no extra text."""


def _sanitize_ai_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from the AI response string."""
    s = raw.strip()
    # Remove ```json ... ``` fences
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"```\s*$", "", s)
    # Find outermost JSON object
    first = s.find("{")
    last  = s.rfind("}")
    if first >= 0 and last > first:
        s = s[first : last + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        log.warning("AI JSON parse error: %s — raw: %.200s", exc, raw)
        return {"status": "parse_error", "error": f"JSON_PARSE_FAILED: {exc}", "raw": raw[:500]}


def ai_parse_order(text: str, headers: dict, endpoint_url: str) -> dict:
    """Send *text* to the AI endpoint and return the sanitized extraction dict.

    Parameters
    ----------
    text          : extracted PDF text (plain text)
    headers       : HTTP headers dict (must include Authorization)
    endpoint_url  : full invocation URL for databricks-gpt-oss-120b

    Returns a dict with at least a ``status`` key ("ok" or "parse_error").
    Never raises.
    """
    import requests as _req  # lazy

    if not text.strip():
        return {"status": "parse_error", "error": "EMPTY_INPUT"}

    payload = {
        "messages": [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user",   "content": f"PURCHASE ORDER TEXT:\n\n{text[:6000]}"},
        ],
        "max_tokens": 1200,
        "temperature": 0,
    }
    try:
        resp = _req.post(endpoint_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _sanitize_ai_json(content)
    except Exception as exc:
        log.error("AI parse error: %s", exc)
        return {"status": "parse_error", "error": str(exc)}


# ── Full pipeline ─────────────────────────────────────────────────────────────

def extract_order_with_ai(
    pdf_path: Path,
    headers: dict,
    endpoint_url: str,
) -> AiExtractResult:
    """Full pipeline: PDF → text → AI → AiExtractResult.

    Steps
    -----
    1. Extract text with pdfplumber → fitz → pypdf → pytesseract.
    2. Send to databricks-gpt-oss-120b for structured extraction.
    3. Normalize and map to AiExtractResult.

    Never raises — errors are captured in ``result.error``.
    """
    # 1. Text extraction
    text, method = extract_pdf_text(pdf_path)
    if not text:
        return AiExtractResult(
            ok=False,
            text_method="none",
            error="Could not extract any text from the PDF (text layer empty and OCR unavailable).",
        )

    # 2. AI parsing
    raw = ai_parse_order(text, headers, endpoint_url)

    if raw.get("status") == "parse_error":
        return AiExtractResult(
            ok=False,
            text_method=method,
            raw_text=text,
            ai_json=raw,
            error=raw.get("error", "AI parse failed"),
        )

    # 3. Map to result
    sk = raw.get("soldto_keys") or {}
    hk = raw.get("shipto_keys") or {}
    lines = raw.get("line_items") or []

    return AiExtractResult(
        ok=True,
        text_method=method,
        raw_text=text,
        ai_json=raw,
        order_key=_norm_txt(raw.get("order_key", "")),
        document_date=_norm_date(raw.get("document_date", "")),
        delivery_date=_norm_date(raw.get("delivery_date_doc", "")),
        express=bool(raw.get("express", False)),
        confidence=float(raw.get("confidence", 0.0)),
        soldto_vat=_norm_vat(sk.get("vat", "")),
        soldto_name=_norm_txt(sk.get("name", "")),
        soldto_postal=_norm_txt(sk.get("postal", "")),
        soldto_city=_norm_txt(sk.get("city", "")),
        soldto_street=_norm_txt(sk.get("street", "")),
        shipto_name=_norm_txt(hk.get("name", "")),
        shipto_postal=_norm_txt(hk.get("postal", "")),
        shipto_city=_norm_txt(hk.get("city", "")),
        shipto_street=_norm_txt(hk.get("street", "")),
        line_items=lines,
    )
