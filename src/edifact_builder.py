"""EDIFACT ORDERS D.96A message builder.

Always uses ELM_STANDARD UNB profile:
  UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'

Forbidden sender IDs (see FORBIDDEN_SENDER_IDS in src/__init__.py) must never appear
in generated output.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional

from . import (
    AUTHORISED_PROFILE_ID,
    AUTHORISED_SENDER_ID,
    AUTHORISED_RECEIVER_ID,
)
from .exceptions import EdifactBuildError, ForbiddenProfileError
from .validations import validate_forbidden_strings_in_text

log = logging.getLogger("edifact.builder")

# Article lines to silently skip (shipping / eco-tax surcharges).
# Mirrors FILE2EDI app/edifact_generator.py IGNORED_ARTICLE_PATTERNS.
IGNORED_ARTICLE_PATTERNS: tuple[str, ...] = (
    "PORT", "PORTSFAB", "PORT FOURNISSEUR",
    "ECOTAX", "ECOTAXE", "FRAIS DE PORT",
    "PARTICIPATION TRANSPORT",
)

# EDIFACT segment terminator
_SEG_TERM = "'"
# EDIFACT component separator
_COMP_SEP = ":"
# EDIFACT data element separator
_DATA_SEP = "+"

_SAP_ARTICLE_RE = re.compile(r"^[A-Z0-9]{1,18}$")
_SAP_CUSTOMER_REF_RE = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,17}$")
_PRICE_ONLY_RE = re.compile(r"^\s*\d{1,7}(?:[,.]\d{1,6})?(?:\s+\d{1,7}(?:[,.]\d{1,6})?)*\s*$")
_PRICE_WITH_UNIT_RE = re.compile(r"\b\d{1,7}[,.]\d{2,6}\s*(?:EUR|EUROS?|HT|TTC)?\b", re.IGNORECASE)
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_WORD_TOKEN_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def _safe(value: str, max_len: int = 35) -> str:
    """Sanitise a string for inclusion in EDIFACT: remove/replace special chars."""
    if not value:
        return ""
    # Replace EDIFACT special chars with space (release char is '?')
    s = re.sub(r"[\?'\+:\n\r]", " ", str(value))
    return s.strip()[:max_len]


def _normalize_sap_reference(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    raw = re.sub(r"^EL[M]?\s*", "", raw)
    raw = raw.replace("\u00a0", " ")
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("-", "")
    return raw


def _validate_bosch_material(value: Any) -> str:
    matnr = _normalize_sap_reference(value)
    if not matnr or not _SAP_ARTICLE_RE.fullmatch(matnr):
        raise EdifactBuildError(f"INVALID_MATERIAL_REFERENCE: invalid Bosch material {value!r}")
    return matnr


def _customer_reference_for_pia(line: dict[str, Any], matnr: str) -> str:
    raw = (
        line.get("customer_reference")
        or line.get("customerReference")
        or line.get("original_article")
        or line.get("customer_article")
        or ""
    )
    ref = _normalize_sap_reference(raw)
    if not ref or ref == matnr:
        return ""
    if not _SAP_CUSTOMER_REF_RE.fullmatch(ref):
        return ""
    return ref


def _description_contains_price(description: str, line: dict[str, Any]) -> bool:
    compact = str(description or "").strip()
    if not compact:
        return False
    if _PRICE_ONLY_RE.fullmatch(compact):
        return True
    for key in ("unit_price", "price", "amount", "montant_ligne_ht"):
        formatted = format_decimal(line.get(key))
        if formatted:
            raw = str(line.get(key) or "").strip()
            if compact in {formatted, raw, raw.replace(".", ","), formatted.replace(".", ",")}:
                return True
    return False


def _clean_item_description(line: dict[str, Any]) -> str:
    raw = str(
        line.get("description")
        or line.get("designation")
        or line.get("product_description")
        or ""
    ).strip()
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return ""
    if _description_contains_price(raw, line):
        raise EdifactBuildError(f"INVALID_ITEM_DESCRIPTION: price-like IMD description {raw!r}")
    # A product text may contain model numbers, but it must contain at least one letter.
    if not _LETTER_RE.search(raw):
        raise EdifactBuildError(f"INVALID_ITEM_DESCRIPTION: non-product IMD description {raw!r}")
    if _PRICE_WITH_UNIT_RE.search(raw) and len(_WORD_TOKEN_RE.findall(raw)) < 2:
        raise EdifactBuildError(f"INVALID_ITEM_DESCRIPTION: amount leaked into IMD description {raw!r}")
    return _safe(raw, 70)


def _pia_value(segment: str) -> str:
    parts = segment.split("+")
    if len(parts) < 3:
        return ""
    return parts[2].split(":", 1)[0].strip()


def _imd_description(segment: str) -> str:
    if "+++" not in segment:
        return ""
    return segment.split("+++", 1)[1].strip()


def _validate_sap_orders05_segments(segments: list[str]) -> None:
    """Block EDIFACT output that would create invalid SAP ORDERS05 item IDocs."""
    lin_count = qty_count = pri_count = 0
    current_line: dict[str, list[str]] | None = None

    def validate_current_line() -> None:
        if current_line is None:
            return
        pia_values = current_line["pia1"] + current_line["pia5"]
        duplicates = {value for value in pia_values if pia_values.count(value) > 1}
        if duplicates:
            raise EdifactBuildError(
                f"INVALID_MATERIAL_REFERENCE: duplicated PIA value {sorted(duplicates)[0]!r}"
            )
        for value in current_line["pia1"]:
            if not _SAP_ARTICLE_RE.fullmatch(value):
                raise EdifactBuildError(
                    f"INVALID_MATERIAL_REFERENCE: invalid Bosch material {value!r}"
                )
        for value in current_line["pia5"]:
            if value in current_line["pia1"] or not _SAP_CUSTOMER_REF_RE.fullmatch(value):
                raise EdifactBuildError(
                    f"INVALID_MATERIAL_REFERENCE: invalid customer material {value!r}"
                )
        if len(current_line["pia1"]) != 1:
            raise EdifactBuildError("INVALID_MATERIAL_REFERENCE: each LIN requires exactly one PIA+1")

    for segment in segments:
        if segment.startswith("LIN+"):
            validate_current_line()
            current_line = {"pia1": [], "pia5": []}
            lin_count += 1
            continue
        if segment.startswith("PIA+1+"):
            if current_line is None:
                raise EdifactBuildError("INVALID_MATERIAL_REFERENCE: PIA outside LIN")
            current_line["pia1"].append(_pia_value(segment))
            continue
        if segment.startswith("PIA+5+"):
            if current_line is None:
                raise EdifactBuildError("INVALID_MATERIAL_REFERENCE: PIA outside LIN")
            current_line["pia5"].append(_pia_value(segment))
            continue
        if segment.startswith("IMD+"):
            description = _imd_description(segment)
            if not description or _PRICE_ONLY_RE.fullmatch(description):
                raise EdifactBuildError(
                    f"INVALID_ITEM_DESCRIPTION: invalid IMD description {description!r}"
                )
            if _PRICE_WITH_UNIT_RE.search(description) and len(
                _WORD_TOKEN_RE.findall(description)
            ) < 2:
                raise EdifactBuildError(
                    f"INVALID_ITEM_DESCRIPTION: amount leaked into IMD description {description!r}"
                )
            continue
        if segment.startswith("QTY+21:"):
            qty_count += 1
            continue
        if segment.startswith("PRI+AAA:"):
            pri_count += 1

    validate_current_line()
    if lin_count != qty_count or lin_count != pri_count:
        raise EdifactBuildError(
            f"INVALID_EDIFACT_STRUCTURE: LIN={lin_count} QTY={qty_count} PRI={pri_count}"
        )


def _validate_date_parts(yyyy: str, mm: str, dd: str) -> Optional[str]:
    """Validate calendar date components; return CCYYMMDD or None.

    Ported from FILE2EDI app/edifact_generator.py validate_date_parts().
    """
    try:
        datetime(int(yyyy), int(mm), int(dd))
        return f"{yyyy}{mm}{dd}"
    except (ValueError, TypeError):
        return None


def _parse_date_ccyymmdd(value: Any) -> Optional[str]:
    """Parse various date formats to CCYYMMDD for DTM segments.

    Handles (priority order):
      1. dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy  (French)
      2. yyyy/mm/dd, yyyy-mm-dd, yyyy.mm.dd  (ISO)
      3. 8-digit YYYYMMDD (validated)
      4. 8-digit DDMMYYYY ambiguous fallback  (FILE2EDI rule)

    Returns CCYYMMDD string or None on failure.
    Ported from FILE2EDI app/edifact_generator.py parse_date_to_ccyymmdd().
    """
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return None

    # dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy
    m = re.match(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$", raw)
    if m:
        dd, mm, yyyy = m.groups()
        return _validate_date_parts(yyyy, mm, dd)

    # yyyy/mm/dd or yyyy-mm-dd or yyyy.mm.dd
    m = re.match(r"^(\d{4})[/.-](\d{2})[/.-](\d{2})$", raw)
    if m:
        yyyy, mm, dd = m.groups()
        return _validate_date_parts(yyyy, mm, dd)

    digits = re.sub(r"\D", "", raw)
    if re.match(r"^\d{8}$", digits):
        # Try YYYYMMDD first
        valid = _validate_date_parts(digits[:4], digits[4:6], digits[6:8])
        if valid:
            return valid
        # Fallback: DDMMYYYY (French compact)
        return _validate_date_parts(digits[4:8], digits[2:4], digits[:2])

    return None


# Public alias for external callers (engine_adapter, tests)
parse_date_to_ccyymmdd = _parse_date_ccyymmdd


def format_decimal(value: Any, scale: int = 6) -> Optional[str]:
    """Convert French/English decimal strings with Decimal precision.

    Examples:
        "10,5"      -> "10.5"
        "1 234,56"  -> "1234.56"
        "1.234,56"  -> "1234.56"  (French thousands separator)
        "25.50"     -> "25.5"
        ""          -> None
        "0"         -> None  (zero / non-positive ignored)
    Ported from FILE2EDI app/edifact_generator.py format_decimal().
    """
    if value is None or value == "":
        return None
    raw = str(value).strip().replace("\u00a0", "").replace("\N{NO-BREAK SPACE}", "").replace(" ", "")
    # French thousands+decimal: 1.234,56 → 1234.56
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return None
    if d <= 0:
        return None
    quant = Decimal("1." + ("0" * scale))
    d = d.quantize(quant, rounding=ROUND_HALF_UP)
    s = format(d, "f").rstrip("0").rstrip(".")
    return s or None


# Legacy alias - kept so existing callers that used _parse_decimal_fr still work.
def _parse_decimal_fr(value: Any) -> str:
    """Legacy wrapper around format_decimal(); returns '' on None."""
    return format_decimal(value) or ""


def normalize_article_code(value: Any) -> tuple[Optional[str], Optional[str], bool]:
    """Normalise a raw article code from a customer PO.

    Returns (article_code, error_code, ignore_line):
      - (None, None, True)                   → line is PORT/ECOTAXE/etc, skip silently
      - (code, None, False)                  → valid, use it
      - (code, "ARTICLE_FORMAT_WARNING:raw", False) → non-standard format, warn but proceed
      - (None, "ARTICLE_MISSING", False)     → empty/missing code

    Rules (ported from FILE2EDI app/edifact_generator.py normalize_article_code()):
      • Strips EL / ELM prefix (Bosch/ELM LEBLANC seller codes)
      • Strips spaces and hyphens
      • Validates [A-Z0-9]{1,13}
      • Ignores IGNORED_ARTICLE_PATTERNS (shipping / eco-tax surcharges)
    """
    raw = re.sub(r"\s+", " ", str(value or "")).strip().upper()

    if not raw:
        return None, "ARTICLE_MISSING", False

    # Silently skip PORT / ECOTAXE / FRAIS DE PORT etc.
    for pattern in IGNORED_ARTICLE_PATTERNS:
        if raw.startswith(pattern):
            return None, None, True

    code = raw
    code = re.sub(r"^EL[M]?\s*", "", code)   # strip EL or ELM prefix
    code = re.sub(r"[\s\-]", "", code)        # strip spaces and hyphens

    if not re.fullmatch(r"[A-Z0-9]{1,13}", code):
        return code, f"ARTICLE_FORMAT_WARNING:{raw}", False

    return code, None, False


def _control_ref(order_number: str, timestamp: datetime) -> str:
    """Generate a deterministic UNB control reference.

    Uses last 9 chars of order_number + HHMM to stay within 14 char limit.
    """
    clean_order = re.sub(r"[^A-Z0-9]", "", order_number.upper())[-9:]
    time_part = timestamp.strftime("%H%M")
    ref = f"{clean_order}{time_part}"
    return ref[:14]


def build_orders_message(
    order: dict[str, Any],
    resolved_lines: list[dict[str, Any]],
    soldto_row: dict[str, str],
    shipto_row: dict[str, str],
    generation_ts: Optional[datetime] = None,
    include_pia_1: bool = True,
) -> str:
    """Build a complete EDIFACT ORDERS D.96A message string.

    Args:
        order: Structured order dict from pdf_extractor (order_number, order_date).
        resolved_lines: List of dicts with 'matnr', 'description', 'quantity',
                        'unit_price', 'original_article'.
        soldto_row: Matched customer row from master data.
        shipto_row: Matched partner row from master data.
        generation_ts: Timestamp override (defaults to now).

    Returns:
        Complete EDIFACT ORDERS message as a string.

    Raises:
        EdifactBuildError: If mandatory fields are missing or segment count is wrong.
        ForbiddenProfileError: If forbidden sender/receiver would appear in output.
    """
    if not resolved_lines:
        raise EdifactBuildError("EDIFACT_NO_LINES: Cannot build ORDERS with zero lines.")

    ts = generation_ts or datetime.now()
    date_str = ts.strftime("%y%m%d")
    time_str = ts.strftime("%H%M")
    order_number = (order.get("order_number") or "").strip()
    if not order_number:
        raise EdifactBuildError("EDIFACT_NO_ORDER_NUMBER")

    order_date = _parse_date_ccyymmdd((order.get("order_date") or "").strip())
    delivery_date = _parse_date_ccyymmdd((order.get("delivery_date") or "").strip())
    ctrl_ref = _control_ref(order_number, ts)

    segments: list[str] = []

    # --- UNA ---
    segments.append("UNA:+.? ")

    # --- UNB ---
    # ALWAYS ELM_STANDARD: UNOC:3 + sender 4399901876613 + receiver 3015981600108
    unb = (
        f"UNB+UNOC:3"
        f"+{AUTHORISED_SENDER_ID}"
        f"+{AUTHORISED_RECEIVER_ID}"
        f"+{date_str}:{time_str}"
        f"+{ctrl_ref}"
    )
    segments.append(unb)

    # --- UNH ---
    segments.append(f"UNH+1+ORDERS:D:96A:UN")

    # Segment counter starts after UNA/UNB; UNH is segment #1
    seg_count = 1  # UNH is first message segment

    # --- BGM ---
    segments.append(f"BGM+220+{_safe(order_number)}+9")
    seg_count += 1

    # --- DTM ---
    if order_date:
        segments.append(f"DTM+137:{_safe(order_date)}:102")
        seg_count += 1

    if delivery_date:
        segments.append(f"DTM+2:{_safe(delivery_date)}:102")
        seg_count += 1

    # --- NAD+BY (Sold-to) ---
    soldto_id = _safe(soldto_row.get("soldto", ""))
    soldto_name = _safe(soldto_row.get("name", ""))
    soldto_street = _safe(soldto_row.get("street", ""))
    soldto_city = _safe(soldto_row.get("city", ""))
    soldto_postal = _safe(soldto_row.get("postal_code", ""))
    soldto_country = _safe(soldto_row.get("country", "FR"), 3)
    segments.append(
        f"NAD+BY+{soldto_id}::91++{soldto_name}+{soldto_street}"
        f"+{soldto_city}++{soldto_postal}+{soldto_country}"
    )
    seg_count += 1

    # --- NAD+DP (Ship-to) ---
    shipto_id = _safe(shipto_row.get("shipto", ""))
    shipto_name = _safe(shipto_row.get("name", ""))
    shipto_street = _safe(shipto_row.get("street", ""))
    shipto_city = _safe(shipto_row.get("city", ""))
    shipto_postal = _safe(shipto_row.get("postal_code", ""))
    shipto_country = _safe(shipto_row.get("country", "FR"), 3)
    segments.append(
        f"NAD+DP+{shipto_id}::91++{shipto_name}+{shipto_street}"
        f"+{shipto_city}++{shipto_postal}+{shipto_country}"
    )
    seg_count += 1

    # --- Order lines ---
    line_number = 0
    line_count = 0
    lin_count = qty_count = pri_count = 0
    for line in resolved_lines:
        line_number += 10
        line_count += 1
        matnr = _validate_bosch_material(line.get("matnr", ""))
        customer_ref = _customer_reference_for_pia(line, matnr)
        description = _clean_item_description(line)
        qty_raw = _parse_decimal_fr(line.get("quantity", "1"))
        try:
            qty_clean = str(int(float(qty_raw)))
        except (ValueError, TypeError):
            qty_clean = "1"
        unit_price_raw = _parse_decimal_fr(line.get("unit_price", ""))
        unit_code = _safe(str(line.get("unit") or "PCE").strip() or "PCE", 3)

        # LIN
        segments.append(f"LIN+{line_number}")
        seg_count += 1
        lin_count += 1

        # PIA+1 is the single Bosch master material reference expected by SAP.
        segments.append(f"PIA+1+{matnr}:SA::91")
        seg_count += 1
        # PIA+5 is only allowed for a distinct, valid customer material reference.
        if customer_ref:
            segments.append(f"PIA+5+{customer_ref}:SA::91")
            seg_count += 1

        # IMD is optional: omit it when OCR did not provide a reliable product text.
        if description:
            segments.append(f"IMD+A+++{description}")
            seg_count += 1

        # QTY+21
        segments.append(f"QTY+21:{qty_clean}:{unit_code}")
        seg_count += 1
        qty_count += 1

        # PRI - only when unit price present
        if unit_price_raw:
            try:
                float(unit_price_raw)  # validate numeric
                segments.append(f"PRI+AAA:{unit_price_raw}:::1")
                seg_count += 1
                pri_count += 1
            except ValueError:
                raise EdifactBuildError(f"INVALID_PRICE: {line.get('unit_price')!r}") from None

    if lin_count != qty_count:
        raise EdifactBuildError(f"INVALID_EDIFACT_STRUCTURE: LIN={lin_count} QTY={qty_count}")
    if pri_count != lin_count:
        raise EdifactBuildError(f"INVALID_EDIFACT_STRUCTURE: LIN={lin_count} PRI={pri_count}")

    # --- UNS+S ---
    segments.append("UNS+S")
    seg_count += 1

    # --- CNT+2 ---
    segments.append(f"CNT+2:{line_count}")
    seg_count += 1

    # seg_count now = all segments counted EXCEPT UNT itself
    # UNT counts itself: total_segs = seg_count + 1 (UNT)
    unt_count = seg_count + 1
    segments.append(f"UNT+{unt_count}+1")

    # --- UNZ ---
    segments.append(f"UNZ+1+{ctrl_ref}")

    _validate_sap_orders05_segments(segments)

    # Join with EDIFACT segment terminator + newline for readability
    message = "'\n".join(segments) + "'\n"

    # Final safety check: no forbidden strings
    validate_forbidden_strings_in_text(message, context="EDIFACT ORDERS output")

    # Verify UNB integrity
    if AUTHORISED_SENDER_ID not in message:
        raise EdifactBuildError("UNB sender not present in generated message.")
    if AUTHORISED_RECEIVER_ID not in message:
        raise EdifactBuildError("UNB receiver not present in generated message.")

    log.info(
        "EDIFACT ORDERS built: order=%s lines=%d segments=%d ctrl_ref=%s",
        order_number, line_count, unt_count, ctrl_ref,
    )
    return message


def generate_tst_filename(order_number: str, soldto: str, ts: Optional[datetime] = None) -> str:
    """Generate the output .tst filename.

    Format: ORDERS_<SOLDTO>_<ORDERNUMBER>_<YYYYMMDDHHMMSS>.tst
    """
    t = ts or datetime.now()
    clean_order = re.sub(r"[^A-Z0-9]", "", order_number.upper())
    clean_soldto = re.sub(r"[^A-Z0-9]", "", soldto.upper())
    timestamp_part = t.strftime("%Y%m%d%H%M%S")
    return f"ORDERS_{clean_soldto}_{clean_order}_{timestamp_part}.tst"
