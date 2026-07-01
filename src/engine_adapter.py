"""Engine adapter — bridges worker.py to the src.* processing modules.

Replaces the legacy sys.path-based engine_adapter from FILE2EDI.
All imports are from the src package; no dynamic path injection.

Public API:
    process_pdf_to_edifact(source_pdf: Path) -> ProcessingResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("edifact.engine_adapter")

# Shipping / eco-tax lines: silently skip instead of rejecting order
# mirrors FILE2EDI app/edifact_generator.py IGNORED_ARTICLE_PATTERNS
_IGNORED_ARTICLE_PATTERNS = (
    "PORT", "PORTSFAB", "PORT FOURNISSEUR",
    "ECOTAX", "ECOTAXE", "FRAIS DE PORT",
    "PARTICIPATION TRANSPORT",
)


# ------------------------------------------------------------------ #
# Result type (mirrors FILE2EDI ProcessingResult, adds soldto)
# ------------------------------------------------------------------ #

@dataclass
class ProcessingResult:
    """Normalised result returned by process_pdf_to_edifact()."""
    status: str                          # COMPLETED | REJECTED
    po_number: str | None = None         # extracted PO number
    soldto: str | None = None            # matched SOLDTO code from master data
    rejection_reason: str | None = None  # rejection code string
    output_content: str | None = None    # EDIFACT .tst text body
    output_filename: str | None = None   # e.g. ORDERS_<SOLDTO>_<PO>_<TS>.tst


# ------------------------------------------------------------------ #
# Main pipeline entry point
# ------------------------------------------------------------------ #

def process_pdf_to_edifact(source_pdf: Path) -> ProcessingResult:
    """Run the full PDF → EDIFACT pipeline and return a ProcessingResult.

    Pipeline stages:
      1. Extract structured order data from PDF
      2. Validate mandatory fields (order key, lines, keywords)
      3. Load master data (Customers, Partners, Materials)
      4. Load lookup tables (EAN, fourre-tout, discontinued, ROH)
      5. Match Sold-to via postal/city/VAT scoring
      6. Match Ship-to filtered by resolved Sold-to
      7. Resolve each line item via POMPAC chain
      8. Build EDIFACT ORDERS D.96A message
      9. Return ProcessingResult(COMPLETED, ...)

    Any rejection exception maps to ProcessingResult(REJECTED, rejection_reason=...).
    Unexpected exceptions also produce REJECTED with PDF_PARSE_FAILURE.
    Never raises — all errors are surfaced via the return value.
    """
    try:
        from .config_loader import load_config
        from .pdf_extractor import (
            compute_pdf_hash,
            extract_order,
            parse_buyer_fields,
        )
        from .master_data import load_master_data
        from .matcher import match_shipto, match_soldto
        from .pompac_rules import LookupTables, load_lookup_tables, resolve_material
        from .edifact_builder import build_orders_message, generate_tst_filename
        from .exceptions import (
            EdifactGeneratorError,
            MatchingError,
            MaterialResolutionError,
            PdfExtractionError,
            ValidationError,
        )

        cfg = load_config()

        # --- 1. Extract ---
        order = extract_order(source_pdf)
        po_number = (order.get("order_number") or "").strip()
        if not po_number:
            return ProcessingResult(
                status="REJECTED",
                rejection_reason="ORDER_KEY_MISSING",
            )

        raw_text  = order.get("raw_text", "")
        lines_raw = order.get("lines", [])  # list of dicts

        # --- 2. Validate lines ---
        if not lines_raw:
            return ProcessingResult(
                status="REJECTED",
                po_number=po_number,
                rejection_reason="NO_VALID_ARTICLE",
            )

        # Contract keyword check (scan raw_text)
        _CONTRACT_KEYWORDS = (
            "contrat", "contract", "devis", "proforma", "quotation",
            "offre de prix", "appel d'offre",
        )
        text_lower = raw_text.lower()
        if any(kw in text_lower for kw in _CONTRACT_KEYWORDS):
            return ProcessingResult(
                status="REJECTED",
                po_number=po_number,
                rejection_reason="CONTRACT_KEYWORD",
            )

        # --- 3. Load master data ---
        md = load_master_data(
            customers_csv=cfg.masterdata.customers_csv,
            partners_csv=cfg.masterdata.partners_csv,
            materials_csv=cfg.masterdata.materials_csv,
            salesorder_csv=cfg.masterdata.salesorder_csv,
        )

        # --- 4. Load lookup tables ---
        lookups: LookupTables = load_lookup_tables()

        # --- 5. Match Sold-to ---
        buyer_text    = order.get("buyer_text", "")
        buyer_fields  = parse_buyer_fields(buyer_text)
        sold_to_row   = match_soldto(
            customers    = md.customers,
            name_query   = buyer_fields.get("name", ""),
            street_query = buyer_fields.get("street", ""),
            postal_query = buyer_fields.get("postal_code", ""),
            city_query   = buyer_fields.get("city", ""),
            vat_query    = buyer_fields.get("vat", ""),
        )
        soldto_code = sold_to_row.get("soldto", "")

        # --- 6. Match Ship-to ---
        delivery_text    = order.get("delivery_text", "")
        delivery_fields  = parse_buyer_fields(delivery_text)  # same parser
        ship_to_row      = match_shipto(
            partners     = md.partners,
            soldto       = soldto_code,
            name_query   = delivery_fields.get("name", ""),
            street_query = delivery_fields.get("street", ""),
            postal_query = delivery_fields.get("postal_code", ""),
            city_query   = delivery_fields.get("city", ""),
        )

        # --- 7. Resolve materials (POMPAC) ---
        resolved_lines = []
        for line in lines_raw:
            # Silently skip shipping/eco-tax lines (PORT, ECOTAXE, FRAIS DE PORT...)
            _art_upper = (line.get("customer_article") or "").strip().upper()
            if any(_art_upper.startswith(p) for p in _IGNORED_ARTICLE_PATTERNS):
                log.debug("Skipping ignored article pattern: %r", _art_upper)
                continue
            try:
                resolved = resolve_material(
                    article_code    = line.get("customer_article", ""),
                    description     = line.get("description", ""),
                    ean_code        = line.get("ean", ""),
                    materials_master= md.materials,
                    lookups         = lookups,
                )
                resolved_lines.append({
                    "matnr":            resolved.matnr,
                    "description":      resolved.description,
                    "quantity":         line.get("quantity", "1"),
                    "unit_price":       line.get("unit_price", ""),
                    "original_article": resolved.original_article,
                })
            except MaterialResolutionError as exc:
                reason = str(exc).split(":")[0] if ":" in str(exc) else "UNKNOWN_MATERIAL"
                return ProcessingResult(
                    status="REJECTED",
                    po_number=po_number,
                    soldto=soldto_code,
                    rejection_reason=reason,
                )

        if not resolved_lines:
            return ProcessingResult(
                status="REJECTED",
                po_number=po_number,
                soldto=soldto_code,
                rejection_reason="NO_VALID_ARTICLE",
            )

        # --- 8. Build EDIFACT ---
        edi_text     = build_orders_message(
            order          = order,
            resolved_lines = resolved_lines,
            soldto_row     = sold_to_row,
            shipto_row     = ship_to_row,
        )
        tst_filename = generate_tst_filename(po_number, soldto_code)

        return ProcessingResult(
            status           = "COMPLETED",
            po_number        = po_number,
            soldto           = soldto_code,
            output_content   = edi_text,
            output_filename  = tst_filename,
        )

    except MatchingError as exc:
        reason = "CONTRACT_BREAK_ADDRESSES_MISSING"
        log.warning("Matching failed for %s: %s", source_pdf.name, exc)
        return ProcessingResult(status="REJECTED", rejection_reason=reason)

    except PdfExtractionError as exc:
        log.warning("PDF extraction failed for %s: %s", source_pdf.name, exc)
        return ProcessingResult(status="REJECTED", rejection_reason="ORDER_KEY_MISSING")

    except ValidationError as exc:
        log.warning("Validation error for %s: %s", source_pdf.name, exc)
        return ProcessingResult(status="REJECTED", rejection_reason="NO_VALID_ARTICLE")

    except Exception as exc:  # noqa: BLE001
        log.exception("Unexpected error processing PDF: %s", source_pdf.name)
        return ProcessingResult(
            status="REJECTED",
            rejection_reason="PDF_PARSE_FAILURE",
        )
