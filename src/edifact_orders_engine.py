"""EDIFACT Orders Generator - Main Engine.

Command-line entry point and batch processing loop.

UNB profile is ALWAYS ELM_STANDARD:
  UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'

Forbidden values that must NEVER appear: see FORBIDDEN_SENDER_IDS in src/__init__.py
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Bootstrap: ensure src/ is on sys.path when run as script
# ---------------------------------------------------------------------------
_SRC_DIR = Path(__file__).parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_SRC_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR.parent))

from src.logger_setup import setup_logging, get_logger
from src.config_loader import load_config, AppConfig
from src.exceptions import (
    EdifactGeneratorError, ConfigError, ForbiddenProfileError,
    MasterDataError, PdfExtractionError, MatchingError,
    MaterialResolutionError, ValidationError, DuplicateOrderError,
    SftpDeliveryError, FileRoutingError,
)
from src.validations import (
    validate_unb_profile_csv,
    validate_masterdata_paths,
    validate_order_data,
    validate_sftp_config,
    validate_output_folders_writable,
    validate_forbidden_strings_in_text,
)
from src.master_data import load_master_data, MasterData
from src.pompac_rules import load_lookup_tables, resolve_material, LookupTables
from src.pdf_extractor import extract_order, compute_pdf_hash, parse_buyer_fields, parse_delivery_fields
from src.matcher import match_soldto, match_shipto
from src.edifact_builder import build_orders_message, generate_tst_filename
from src.sftp_delivery import upload_tst
from src.file_router import (
    list_pdfs, move_to_processed, move_to_error,
    archive_tst_submitted, archive_tst_failed,
    write_local_tst_atomically,
)
from src.duplicate_ledger import (
    check_duplicate, record_processing, record_sftp_delivery,
)
from src.n8n_project_analyzer import analyse_n8n_project, generate_analysis_report

log = get_logger("edifact.engine")

# Forbidden strings that must never be in active config or output
# Values come from FORBIDDEN_SENDER_IDS / FORBIDDEN_RECEIVER_IDS in src/__init__.py
from src import FORBIDDEN_SENDER_IDS as _FORBIDDEN


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------

def startup_validate(cfg: AppConfig, args: argparse.Namespace) -> None:
    """Run startup validation sequence.

    Raises:
        ForbiddenProfileError: If ELM_STANDARD constraints are violated.
        ConfigError: If mandatory config or files are missing.
    """
    log.info("=== EDIFACT Orders Generator - Startup Validation ===")

    # 1. UNB profiles CSV
    unb_csv = str(Path("lookups") / "unb_profiles.csv")
    validate_unb_profile_csv(unb_csv)

    # 2. Forbidden strings in config
    for forbidden_val in _FORBIDDEN:
        if (forbidden_val in (cfg.edi.sender_id or '')) or (forbidden_val in (cfg.edi.receiver_id or '')):
            raise ForbiddenProfileError(
                f"Forbidden value {forbidden_val!r} detected in EDI config."
            )

    # 3. Master data files
    validate_masterdata_paths(
        cfg.masterdata.customers_csv,
        cfg.masterdata.partners_csv,
        cfg.masterdata.materials_csv,
    )

    # 4. SFTP config (unless --skip-sftp or --dry-run)
    if not args.skip_sftp and not args.dry_run:
        validate_sftp_config(cfg.sftp)

    # 5. Output folders
    validate_output_folders_writable(
        cfg.paths.local_generated_outbox,
        cfg.paths.sftp_submitted_archive,
        cfg.paths.sftp_failed_archive,
    )

    log.info("=== Startup validation PASSED ===")


# ---------------------------------------------------------------------------
# n8n analysis
# ---------------------------------------------------------------------------

def run_n8n_analysis(cfg: AppConfig) -> None:
    """Analyse n8n project and generate N8N_ANALYSIS_REPORT.md."""
    if not cfg.n8n.analyse_existing_project:
        log.info("n8n analysis disabled in config.")
        return
    log.info("Running n8n project analysis: %s", cfg.n8n.n8n_project_root)
    report = analyse_n8n_project(cfg.n8n.n8n_project_root)
    generate_analysis_report(report, cfg.n8n.analysis_report)
    log.info("n8n analysis report written: %s", cfg.n8n.analysis_report)


# ---------------------------------------------------------------------------
# Single PDF processing
# ---------------------------------------------------------------------------

def process_single_pdf(
    pdf_path: Path,
    cfg: AppConfig,
    master: MasterData,
    lookups: LookupTables,
    args: argparse.Namespace,
) -> bool:
    """Process one PDF through the full EDIFACT generation and SFTP pipeline.

    Returns:
        True if successfully processed (PDF moved to PROCESSED).
        False if failed (PDF moved to ERROR).

    This function must not raise; all failures are handled internally.
    """
    log.info("--- Processing: %s ---", pdf_path.name)
    pdf_hash = ""
    order: dict = {}
    tst_path: Optional[Path] = None
    soldto_row: dict = {}
    shipto_row: dict = {}
    resolved_lines: list = []

    try:
        # --- a. Compute PDF hash ---
        pdf_hash = compute_pdf_hash(pdf_path)
        log.info("PDF hash: %s", pdf_hash)

        # --- b. Extract PDF text ---
        order = extract_order(pdf_path)

        # --- c. Validate extracted order ---
        validate_order_data(order)

        # --- d. Detect Sold-to ---
        buyer_fields = parse_buyer_fields(order.get("buyer_text", ""))
        soldto_row = match_soldto(
            master.customers,
            name_query=buyer_fields.get("name", ""),
            street_query=buyer_fields.get("street", ""),
            postal_query=buyer_fields.get("postal_code", ""),
            city_query=buyer_fields.get("city", ""),
            vat_query=buyer_fields.get("vat", ""),
        )
        soldto = soldto_row["soldto"]
        log.info("Sold-to resolved: %s", soldto)

        # --- e. Detect Ship-to ---
        delivery_fields = parse_delivery_fields(order.get("delivery_text", ""))
        shipto_row = match_shipto(
            master.partners,
            soldto=soldto,
            name_query=delivery_fields.get("name", ""),
            street_query=delivery_fields.get("street", ""),
            postal_query=delivery_fields.get("postal_code", ""),
            city_query=delivery_fields.get("city", ""),
        )
        shipto = shipto_row["shipto"]
        log.info("Ship-to resolved: %s", shipto)

        # --- f. Resolve materials ---
        resolved_lines = []
        for line in order.get("lines", []):
            resolved = resolve_material(
                article_code=line.get("customer_article", ""),
                description=line.get("description", ""),
                ean_code=line.get("ean", ""),
                materials_master=master.materials,
                lookups=lookups,
            )
            resolved_lines.append({
                "matnr": resolved.matnr,
                "description": resolved.description,
                "quantity": line.get("quantity", "1"),
                "unit_price": line.get("unit_price", ""),
                "original_article": line.get("customer_article", ""),
            })

        # --- g. Check duplicates (before building) ---
        if cfg.duplicates.enabled:
            check_duplicate(
                cfg.duplicates.ledger_csv,
                order["order_number"],
                soldto,
                pdf_hash,
            )

        # --- h. Build EDIFACT ORDERS ---
        from datetime import datetime
        ts = datetime.now()
        message = build_orders_message(
            order=order,
            resolved_lines=resolved_lines,
            soldto_row=soldto_row,
            shipto_row=shipto_row,
            generation_ts=ts,
        )

        # Final forbidden string check on generated output
        validate_forbidden_strings_in_text(message, context=pdf_path.name)

        # --- i. Generate filename and write local .tst ---
        tst_filename = generate_tst_filename(order["order_number"], soldto, ts)
        tst_path = Path(cfg.paths.local_generated_outbox) / tst_filename
        write_local_tst_atomically(message, tst_path)

        # --- j. SFTP upload ---
        if args.dry_run or args.skip_sftp:
            log.info("DRY RUN / SKIP SFTP: Skipping SFTP upload for %s", tst_filename)
            sftp_status = "DRY_RUN"
        else:
            sftp_result = upload_tst(tst_path, tst_filename, cfg.sftp)
            if not sftp_result.success:
                # SFTP failed: route PDF to error, archive tst to failed
                if tst_path and tst_path.exists():
                    archive_tst_failed(tst_path, cfg.paths.sftp_failed_archive)
                record_sftp_delivery(
                    "data/sftp_delivery_ledger.csv",
                    tst_filename=tst_filename,
                    local_path=str(tst_path),
                    remote_dir=cfg.sftp.remote_dir,
                    remote_path="",
                    file_size=tst_path.stat().st_size if tst_path.exists() else 0,
                    sha256=_sha256_file(tst_path) if tst_path and tst_path.exists() else "",
                    status="SFTP_FAILED",
                    error_reason=sftp_result.error_reason,
                )
                raise SftpDeliveryError(sftp_result.error_reason)

            sftp_status = "SFTP_SUBMITTED"
            log.info("SFTP upload confirmed: %s", sftp_result.remote_path)

            # Archive locally submitted copy
            if cfg.sftp.keep_local_copy:
                archive_tst_submitted(tst_path, cfg.paths.sftp_submitted_archive)

            record_sftp_delivery(
                "data/sftp_delivery_ledger.csv",
                tst_filename=tst_filename,
                local_path=str(tst_path),
                remote_dir=cfg.sftp.remote_dir,
                remote_path=sftp_result.remote_path,
                file_size=sftp_result.file_size,
                sha256=_sha256_file(tst_path) if tst_path.exists() else "",
                status="SFTP_SUBMITTED",
            )

        # --- k/l/m. Update duplicate ledger (only after confirmed SFTP) ---
        if cfg.duplicates.enabled and sftp_status in {"SFTP_SUBMITTED", "DRY_RUN"}:
            record_processing(
                cfg.duplicates.ledger_csv,
                order_number=order["order_number"],
                soldto=soldto,
                shipto=shipto,
                pdf_hash=pdf_hash,
                tst_filename=tst_filename,
                sftp_status=sftp_status,
                status=sftp_status,
            )

        # --- n. Move PDF to PROCESSED (only after confirmed SFTP) ---
        if not args.dry_run:
            move_to_processed(pdf_path, cfg.paths.pdf_processed)

        log.info("SUCCESS: %s -> %s", pdf_path.name, tst_filename)
        return True

    except DuplicateOrderError as exc:
        log.warning("[DUPLICATE] %s: %s", pdf_path.name, exc)
        _route_to_error(pdf_path, cfg, str(exc), args)
        return False

    except (PdfExtractionError, ValidationError, MatchingError, MaterialResolutionError) as exc:
        log.error("[REJECTION] %s: %s", pdf_path.name, exc)
        _route_to_error(pdf_path, cfg, str(exc), args)
        return False

    except SftpDeliveryError as exc:
        log.error("[SFTP_FAILED] %s: %s", pdf_path.name, exc)
        _route_to_error(pdf_path, cfg, str(exc), args)
        return False

    except ForbiddenProfileError as exc:
        log.critical("[FORBIDDEN_PROFILE] %s: %s", pdf_path.name, exc)
        _route_to_error(pdf_path, cfg, str(exc), args)
        return False

    except Exception as exc:
        log.exception("[UNEXPECTED_ERROR] %s: %s", pdf_path.name, exc)
        _route_to_error(pdf_path, cfg, f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}", args)
        return False


def _route_to_error(pdf_path: Path, cfg: AppConfig, reason: str, args: argparse.Namespace) -> None:
    """Move PDF to error folder unless dry-run."""
    if args.dry_run:
        log.info("[DRY RUN] Would move %s to ERROR: %s", pdf_path.name, reason)
        return
    try:
        move_to_error(pdf_path, cfg.paths.pdf_error, reason)
    except FileRoutingError as exc:
        log.error("FileRoutingError: %s", exc)


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EDIFACT Orders Generator - ELM_STANDARD only",
    )
    parser.add_argument(
        "--config", default="config.ini",
        help="Path to config.ini (default: config.ini)",
    )
    parser.add_argument(
        "--analyse-n8n-only", action="store_true",
        help="Analyse n8n project and write N8N_ANALYSIS_REPORT.md, then exit.",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Validate config, master data, SFTP config, forbidden strings. Exit.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build EDIFACT but do not upload to SFTP and do not move PDFs.",
    )
    parser.add_argument(
        "--single-pdf", metavar="PDF_PATH",
        help="Process a single PDF file instead of the inbox.",
    )
    parser.add_argument(
        "--skip-sftp", action="store_true",
        help="Skip SFTP upload (local dev only; not for production).",
    )
    parser.add_argument(
        "--log-level", default="",
        help="Override logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    """Main engine entry point.

    Returns:
        0 on successful run completion.
        Non-zero only for fatal startup/config/master-data/SFTP setup failures.
    """
    args = parse_args()

    # Bootstrap logging before config is loaded
    log_level = args.log_level or "INFO"
    setup_logging(level=log_level)

    log.info("EDIFACT Orders Generator starting. UNB profile: ELM_STANDARD ONLY.")

    try:
        cfg = load_config(args.config)
    except (ConfigError, ForbiddenProfileError) as exc:
        log.critical("Configuration fatal error: %s", exc)
        return 2
    except Exception as exc:
        log.exception("Unexpected config error: %s", exc)
        return 2

    # Re-configure logging from config
    effective_level = args.log_level or cfg.logging.level
    setup_logging(
        level=effective_level,
        log_file="logs/edifact.log",
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
    )

    # --- Warn about skip-sftp ---
    if args.skip_sftp:
        log.warning(
            "--skip-sftp active. This is for local development ONLY. "
            "NEVER use in production."
        )

    # --- analyse-n8n-only mode ---
    if args.analyse_n8n_only:
        log.info("Mode: --analyse-n8n-only")
        report = analyse_n8n_project(cfg.n8n.n8n_project_root)
        generate_analysis_report(report, cfg.n8n.analysis_report)
        log.info("n8n analysis complete. Report: %s", cfg.n8n.analysis_report)
        return 0

    # --- validate-only mode ---
    if args.validate_only:
        log.info("Mode: --validate-only")
        try:
            startup_validate(cfg, args)
        except (ConfigError, ForbiddenProfileError, ValidationError) as exc:
            log.error("Validation failed: %s", exc)
            return 1
        log.info("Validation PASSED.")
        return 0

    # --- Full run ---
    try:
        startup_validate(cfg, args)
    except (ConfigError, ForbiddenProfileError, ValidationError) as exc:
        log.critical("Startup validation failed: %s", exc)
        return 2

    # Step 3/4: n8n analysis
    try:
        run_n8n_analysis(cfg)
    except Exception as exc:
        log.warning("n8n analysis non-fatal error: %s", exc)

    # Step 7: Load master data
    try:
        master = load_master_data(
            customers_csv=cfg.masterdata.customers_csv,
            partners_csv=cfg.masterdata.partners_csv,
            materials_csv=cfg.masterdata.materials_csv,
            salesorder_csv=cfg.masterdata.salesorder_csv,
        )
    except MasterDataError as exc:
        log.critical("Master data load failed: %s", exc)
        return 2

    # Step 8: Load lookup tables
    lookups = load_lookup_tables(
        ean_csv="lookups/lookup_ean_to_material.csv",
        fourretout_csv="lookups/lookup_fourretout_to_material.csv",
        discontinued_csv="lookups/lookup_discontinued.csv",
        roh_csv="lookups/lookup_roh_noncommercial.csv",
    )

    # Step 10/11: Detect and process PDFs
    if args.single_pdf:
        pdfs = [Path(args.single_pdf)]
        if not pdfs[0].exists():
            log.error("--single-pdf: file not found: %s", args.single_pdf)
            return 2
    else:
        pdfs = list_pdfs(cfg.paths.pdf_inbox)

    if not pdfs:
        log.info("No PDFs found in inbox: %s", cfg.paths.pdf_inbox)
        return 0

    total = len(pdfs)
    success_count = 0
    fail_count = 0

    for pdf_path in pdfs:
        result = process_single_pdf(pdf_path, cfg, master, lookups, args)
        if result:
            success_count += 1
        else:
            fail_count += 1

    log.info(
        "Batch complete: total=%d success=%d failed=%d",
        total, success_count, fail_count,
    )

    # Exit code 0 always if batch completed (individual failures are logged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
