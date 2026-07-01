"""Worker process for EDIFACT Standalone Orchestrator.

Polls SQLite for queued jobs and drives the full pipeline:
  PDF → engine_adapter → SFTP (if enabled) → status update

Run via: python run_worker.py
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .config_loader import load_config
from .database import initialize_database
from .engine_adapter import ProcessingResult, process_pdf_to_edifact
from .repository import (
    append_event,
    check_and_record_duplicate,
    reserve_next_job,
    update_job_status,
)
from .sftp_delivery import SftpDeliveryResult, upload_tst

log = logging.getLogger("edifact.worker")


def _dir(env_key: str, default: str) -> Path:
    """Resolve a runtime directory from env or default, creating it if absent."""
    root = Path(__file__).resolve().parent.parent
    p = Path(os.getenv(env_key, str(root / default)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def process_job_logic(job: dict) -> tuple[str, str | None, Path | None]:
    """Run the full parse/build/deliver pipeline for one job.

    Returns (status, rejection_reason, output_path).
    """
    cfg = load_config()
    source_path = Path(job["source_path"])
    reject_dir  = _dir("REJECT_DIR",    "data/reject")
    outbox_dir  = _dir("OUTBOX_DIR",    "data/outbox")
    done_dir    = _dir("PROCESSED_DIR", "data/processed")

    result: ProcessingResult = process_pdf_to_edifact(source_path)

    # --- Rejection ---
    if result.status == "REJECTED":
        reject_target = reject_dir / source_path.name
        source_path.replace(reject_target)
        return "REJECTED", result.rejection_reason, None

    if result.status != "COMPLETED" or not result.output_content or not result.output_filename:
        raise RuntimeError(f"Unexpected engine result: status={result.status!r}")

    # --- Dedupe (3-component key) ---
    soldto = result.soldto or ""
    if result.po_number and check_and_record_duplicate(result.po_number, soldto, source_path):
        reject_target = reject_dir / source_path.name
        source_path.replace(reject_target)
        return "DUPLICATE", "DUPLICATE_ORDER", None

    # --- Write .tst ---
    output_path = outbox_dir / result.output_filename
    output_path.write_text(result.output_content, encoding="utf-8")

    # --- SFTP upload ---
    if cfg.sftp.enabled:
        sftp_result: SftpDeliveryResult = upload_tst(
            local_path=output_path,
            tst_filename=result.output_filename,
            sftp_cfg=cfg.sftp,
        )
        if not sftp_result.success:
            raise RuntimeError(f"SFTP_UPLOAD_FAILED: {sftp_result.error_reason}")

    # --- Archive source PDF ---
    source_path.replace(done_dir / source_path.name)
    return "COMPLETED", None, output_path


def run_once() -> bool:
    """Pick the oldest queued job, process it. Return True if work was done."""
    job = reserve_next_job()
    if not job:
        return False

    job_id = job["id"]
    try:
        append_event(job_id, "PIPELINE_START", {"source_path": job["source_path"]})
        status, rejection_reason, output_path = process_job_logic(job)
        append_event(job_id, "PIPELINE_RESULT", {"status": status, "rejection_reason": rejection_reason})

        if status == "COMPLETED" and output_path is not None:
            update_job_status(
                job_id, status,
                output_filename=output_path.name,
                output_path=str(output_path),
            )
            log.info("Job %s COMPLETED: %s", job_id, output_path.name)
        elif status in {"REJECTED", "DUPLICATE"}:
            update_job_status(job_id, status, rejection_reason=rejection_reason)
            log.info("Job %s %s: %s", job_id, status, rejection_reason)
        else:
            update_job_status(job_id, "FAILED", error_message="Unexpected status")

    except Exception as exc:
        append_event(job_id, "PIPELINE_EXCEPTION", {"error": f"{type(exc).__name__}: {exc}"})
        update_job_status(job_id, "FAILED", error_message=f"{type(exc).__name__}: {exc}")
        log.exception("Job %s FAILED", job_id)

    return True


def run_forever() -> None:
    """Poll-and-process loop. Runs until interrupted."""
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    initialize_database()
    poll_seconds = int(os.getenv("WORKER_POLL_SECONDS", "5"))
    log.info("Worker started. poll=%ss sftp_enabled=%s", poll_seconds, cfg.sftp.enabled)

    while True:
        had_work = run_once()
        if not had_work:
            time.sleep(poll_seconds)
