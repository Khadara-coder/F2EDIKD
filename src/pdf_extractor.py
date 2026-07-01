"""PDF text extraction for EDIFACT Orders Generator.

Uses PyPDF2 / pypdf for text extraction.
No external OCR APIs called in this initial stack.
Returns a structured order dict or raises PdfExtractionError.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Optional

from .exceptions import PdfExtractionError

log = logging.getLogger("edifact.pdf")


# --------------------------------------------------------------------------- #
# PDF reading helpers
# --------------------------------------------------------------------------- #

def _read_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF using pypdf/PyPDF2.

    Raises:
        PdfExtractionError: If the PDF cannot be opened or text is empty.
    """
    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        pages_text: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception as exc:
                log.warning("Page text extraction error (continuing): %s", exc)
                t = ""
            pages_text.append(t)

        full_text = "\n".join(pages_text).strip()
        if not full_text:
            raise PdfExtractionError(
                f"PDF_EMPTY_TEXT: No text extracted from {pdf_path.name}. "
                "File may be image-only; OCR is required."
            )
        log.info("PDF text extracted: %s (%d chars)", pdf_path.name, len(full_text))
        return full_text

    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError(
            f"PDF_READ_FAILED: Cannot read {pdf_path.name}: {type(exc).__name__}: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Field extraction patterns
# --------------------------------------------------------------------------- #

_ORDER_NUMBER_PATTERNS = [
    re.compile(r"(?:commande|order|bon de commande|n[o\xb0]\s*commande)[\s:]+([A-Z0-9\-/]{4,20})", re.IGNORECASE),
    re.compile(r"(?:po|p\.o\.|purchase order)[\s#:]+([A-Z0-9\-/]{4,20})", re.IGNORECASE),
    re.compile(r"(?:r[e\xe9]f[\xe9e]rence)[\s:]+([A-Z0-9\-/]{4,20})", re.IGNORECASE),
]

_ORDER_DATE_PATTERNS = [
    re.compile(r"(?:date)[\s:]+([0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})", re.IGNORECASE),
    re.compile(r"([0-9]{2}[\-/\.][0-9]{2}[\-/\.][0-9]{4})"),
    re.compile(r"([0-9]{4}[\-/][0-9]{2}[\-/][0-9]{2})"),  # ISO
]

_LINE_PATTERNS = [
    # Pattern: ref/code, qty, description, unit price
    re.compile(
        r"([A-Z0-9]{5,15})[\s;,|]+"
        r"([0-9]+(?:[,\.][0-9]+)?)[\s;,|]+"
        r"([^\n;|]{5,60})[\s;,|]*"
        r"([0-9]+(?:[,\.][0-9]+)?)?\s*(?:EUR|€|\bPCE\b)?",
        re.IGNORECASE,
    ),
]

_EAN_PATTERN = re.compile(r"(?:EAN|code[-\s]?barre)[\s:]+([0-9]{12,13})", re.IGNORECASE)
_PRICE_PATTERN = re.compile(r"([0-9]+(?:[,\.][0-9]{1,2})?)\s*(?:EUR|€)", re.IGNORECASE)
_QTY_PATTERN = re.compile(r"(?:qte|qtt|quantit[e\xe9])[\s.:]+([0-9]+(?:[,\.][0-9]+)?)", re.IGNORECASE)

_BUYER_SECTION = re.compile(
    r"(?:acheteur|buyer|donneur d.ordre|vendu \xE0)[^\n]{0,40}\n"
    r"([\w\s\-\.,']+?\n[\w\s\-\.,'0-9]+?\n[\w\s\-\.,'0-9]+)",
    re.IGNORECASE,
)
_DELIVERY_SECTION = re.compile(
    r"(?:livraison|ship.to|livrer \xE0|adresse de livraison)[^\n]{0,40}\n"
    r"([\w\s\-\.,']+?\n[\w\s\-\.,'0-9]+?\n[\w\s\-\.,'0-9]+)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

def _extract_field(text: str, patterns: list[re.Pattern]) -> Optional[str]:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _extract_section(text: str, pattern: re.Pattern) -> str:
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _normalise_date(raw: str) -> str:
    """Attempt to normalise date to YYYYMMDD for DTM+137."""
    if not raw:
        return ""
    # Remove dots
    raw = raw.replace(".", "/")
    # Try DD/MM/YYYY
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}"
    # Try YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    # Try DD-MM-YYYY
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", raw)
    if m:
        return f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}"
    return raw.replace("/", "").replace("-", "")


def _extract_lines(text: str) -> list[dict[str, str]]:
    """Extract order line items from PDF text.

    Uses heuristic patterns. Each line must have at minimum a quantity.
    """
    lines: list[dict[str, str]] = []
    # Look for table-like rows
    for line_text in text.split("\n"):
        line_text = line_text.strip()
        if not line_text:
            continue

        # Try each line pattern
        for pat in _LINE_PATTERNS:
            m = pat.match(line_text)
            if m:
                groups = m.groups()
                line: dict[str, str] = {
                    "customer_article": (groups[0] or "").strip(),
                    "quantity": (groups[1] or "").strip(),
                    "description": (groups[2] or "").strip(),
                    "unit_price": (groups[3] or "").strip(),
                    "ean": "",
                }
                # Try to extract EAN from the same line or nearby
                ean_m = _EAN_PATTERN.search(line_text)
                if ean_m:
                    line["ean"] = ean_m.group(1)
                lines.append(line)
                break

    return lines


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def compute_pdf_hash(pdf_path: Path) -> str:
    """Compute SHA-256 hash of a PDF file."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_order(pdf_path: Path) -> dict[str, Any]:
    """Extract structured order data from a PDF file.

    Returns a dict conforming to the standardised order schema:
    {
        'pdf_file': str,
        'raw_text': str,
        'order_number': str,
        'order_date': str,     # YYYYMMDD
        'buyer_text': str,
        'delivery_text': str,
        'lines': [
            {
                'customer_article': str,
                'ean': str,
                'description': str,
                'quantity': str,
                'unit_price': str,
            }
        ]
    }

    Raises:
        PdfExtractionError: If PDF cannot be read or yields no usable content.
    """
    raw_text = _read_pdf_text(pdf_path)

    order_number = _extract_field(raw_text, _ORDER_NUMBER_PATTERNS) or ""
    order_date_raw = _extract_field(raw_text, _ORDER_DATE_PATTERNS) or ""
    order_date = _normalise_date(order_date_raw)
    buyer_text = _extract_section(raw_text, _BUYER_SECTION)
    delivery_text = _extract_section(raw_text, _DELIVERY_SECTION)
    lines = _extract_lines(raw_text)

    log.info(
        "Extracted order: file=%s order_number=%r date=%s lines=%d",
        pdf_path.name, order_number, order_date, len(lines),
    )

    return {
        "pdf_file": str(pdf_path),
        "raw_text": raw_text,
        "order_number": order_number,
        "order_date": order_date,
        "buyer_text": buyer_text,
        "delivery_text": delivery_text,
        "lines": lines,
    }


def parse_buyer_fields(buyer_text: str) -> dict[str, str]:
    """Parse buyer address text into structured fields."""
    lines = [l.strip() for l in buyer_text.strip().split("\n") if l.strip()]
    result: dict[str, str] = {
        "name": lines[0] if lines else "",
        "street": lines[1] if len(lines) > 1 else "",
        "postal_city": lines[2] if len(lines) > 2 else "",
        "city": "",
        "postal_code": "",
        "vat": "",
    }
    # Try to split postal + city
    pc_text = result["postal_city"]
    m = re.match(r"(\d{4,6})\s+(.+)", pc_text)
    if m:
        result["postal_code"] = m.group(1)
        result["city"] = m.group(2).strip()
    # Look for VAT in raw text
    vat_m = re.search(r"(?:TVA|VAT)[\s:]+([A-Z]{2}[0-9A-Z]{8,15})", buyer_text, re.IGNORECASE)
    if vat_m:
        result["vat"] = vat_m.group(1)
    return result


def parse_delivery_fields(delivery_text: str) -> dict[str, str]:
    """Parse delivery address text into structured fields."""
    lines = [l.strip() for l in delivery_text.strip().split("\n") if l.strip()]
    result: dict[str, str] = {
        "name": lines[0] if lines else "",
        "street": lines[1] if len(lines) > 1 else "",
        "postal_city": lines[2] if len(lines) > 2 else "",
        "city": "",
        "postal_code": "",
    }
    pc_text = result["postal_city"]
    m = re.match(r"(\d{4,6})\s+(.+)", pc_text)
    if m:
        result["postal_code"] = m.group(1)
        result["city"] = m.group(2).strip()
    return result
