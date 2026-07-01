"""Duplicate detection ledger for EDIFACT Orders Generator.

Duplicate policy from n8n FINAL_IMPLEMENTATION_STATUS:
- Composite key: order_number + soldto (order_key) AND pdf_hash
- Only SFTP_SUBMITTED final-state entries trigger duplicate rejection
- SENT and DELIVERED are also treated as final states for compatibility
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .exceptions import DuplicateOrderError

log = logging.getLogger("edifact.duplicates")

_FINAL_STATES = frozenset({"SFTP_SUBMITTED", "SENT", "DELIVERED"})
_FIELDNAMES = [
    "processed_at",
    "order_number",
    "soldto",
    "shipto",
    "pdf_hash",
    "tst_filename",
    "sftp_status",
    "status",
    "error_reason",
]
_SFTP_FIELDNAMES = [
    "submitted_at",
    "tst_filename",
    "local_path",
    "remote_dir",
    "remote_path",
    "file_size",
    "sha256",
    "status",
    "error_reason",
]


def _ensure_header(path: Path, fieldnames: list[str]) -> None:
    """Create the CSV with header row if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()


def _load_ledger(path: Path) -> list[dict[str, str]]:
    """Load all ledger rows from CSV."""
    _ensure_header(path, _FIELDNAMES)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def check_duplicate(
    ledger_csv: str,
    order_number: str,
    soldto: str,
    pdf_hash: str,
) -> None:
    """Check if this order is a duplicate.

    Raises DuplicateOrderError if a final-state entry exists for:
    - same pdf_hash, OR
    - same (order_number + soldto) composite key

    Args:
        ledger_csv: Path to the duplicate ledger CSV.
        order_number: Order number from PDF.
        soldto: Resolved Sold-to number.
        pdf_hash: SHA-256 hash of the PDF file.

    Raises:
        DuplicateOrderError: If this order was previously submitted.
    """
    path = Path(ledger_csv)
    rows = _load_ledger(path)

    for row in rows:
        if row.get("status") not in _FINAL_STATES and row.get("sftp_status") not in _FINAL_STATES:
            continue
        # Check pdf_hash match
        if pdf_hash and row.get("pdf_hash") == pdf_hash:
            raise DuplicateOrderError(
                f"DUPLICATE_ORDER: PDF hash already submitted. "
                f"order_number={order_number!r} pdf_hash={pdf_hash!r} "
                f"previous_tst={row.get('tst_filename')!r}"
            )
        # Check composite key (order_number + soldto)
        if (
            order_number
            and row.get("order_number") == order_number
            and row.get("soldto") == soldto
        ):
            raise DuplicateOrderError(
                f"DUPLICATE_ORDER: Order already submitted. "
                f"order_number={order_number!r} soldto={soldto!r} "
                f"previous_tst={row.get('tst_filename')!r}"
            )

    log.info(
        "Duplicate check passed: order_number=%r soldto=%r", order_number, soldto
    )


def record_processing(
    ledger_csv: str,
    order_number: str,
    soldto: str,
    shipto: str,
    pdf_hash: str,
    tst_filename: str,
    sftp_status: str,
    status: str,
    error_reason: str = "",
) -> None:
    """Append a processing record to the duplicate ledger.

    This should only be called after confirmed SFTP submission
    (sftp_status=SFTP_SUBMITTED) to avoid false duplicate detection.
    """
    path = Path(ledger_csv)
    _ensure_header(path, _FIELDNAMES)
    row = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "order_number": order_number,
        "soldto": soldto,
        "shipto": shipto,
        "pdf_hash": pdf_hash,
        "tst_filename": tst_filename,
        "sftp_status": sftp_status,
        "status": status,
        "error_reason": error_reason,
    }
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writerow(row)
    log.info(
        "Ledger recorded: order=%r soldto=%r status=%s sftp=%s",
        order_number, soldto, status, sftp_status,
    )


def record_sftp_delivery(
    ledger_csv: str,
    tst_filename: str,
    local_path: str,
    remote_dir: str,
    remote_path: str,
    file_size: int,
    sha256: str,
    status: str,
    error_reason: str = "",
) -> None:
    """Append a record to the SFTP delivery ledger."""
    path = Path(ledger_csv)
    _ensure_header(path, _SFTP_FIELDNAMES)
    row = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "tst_filename": tst_filename,
        "local_path": local_path,
        "remote_dir": remote_dir,
        "remote_path": remote_path,
        "file_size": str(file_size),
        "sha256": sha256,
        "status": status,
        "error_reason": error_reason,
    }
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_SFTP_FIELDNAMES)
        writer.writerow(row)
    log.info(
        "SFTP delivery recorded: tst=%r status=%s remote=%s",
        tst_filename, status, remote_path,
    )
