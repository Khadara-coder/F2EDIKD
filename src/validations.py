"""Pre-generation validation rules for EDIFACT Orders Generator."""
from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Any

from . import (
    AUTHORISED_PROFILE_ID,
    AUTHORISED_SENDER_ID,
    AUTHORISED_RECEIVER_ID,
    FORBIDDEN_SENDER_IDS,
    FORBIDDEN_RECEIVER_IDS,
)
from .exceptions import ValidationError, ForbiddenProfileError, ConfigError

log = logging.getLogger("edifact.validations")


def validate_unb_profile_csv(unb_profiles_csv: str) -> None:
    """Validate that unb_profiles.csv has exactly one row and it is ELM_STANDARD.

    Raises:
        ForbiddenProfileError: If the file has more than one data row or invalid values.
        ConfigError: If the file cannot be read or is missing.
    """
    path = Path(unb_profiles_csv)
    if not path.exists():
        raise ConfigError(f"UNB profiles CSV not found: {unb_profiles_csv}")

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [row for row in reader if any(v.strip() for v in row.values())]

    if len(rows) != 1:
        raise ForbiddenProfileError(
            f"unb_profiles.csv must have exactly 1 data row. Found: {len(rows)}. "
            "No second UNB profile is permitted."
        )

    row = rows[0]
    profile_id = row.get("profile_id", "").strip()
    sender_id = row.get("sender_id", "").strip()
    receiver_id = row.get("receiver_id", "").strip()

    if profile_id != AUTHORISED_PROFILE_ID:
        raise ForbiddenProfileError(
            f"Profile ID must be {AUTHORISED_PROFILE_ID!r}. Found: {profile_id!r}"
        )
    if sender_id != AUTHORISED_SENDER_ID:
        raise ForbiddenProfileError(
            f"Sender ID must be {AUTHORISED_SENDER_ID!r}. Found: {sender_id!r}"
        )
    if receiver_id != AUTHORISED_RECEIVER_ID:
        raise ForbiddenProfileError(
            f"Receiver ID must be {AUTHORISED_RECEIVER_ID!r}. Found: {receiver_id!r}"
        )

    log.info("UNB profiles CSV validated: 1 row, ELM_STANDARD only.")


def validate_forbidden_strings_in_text(text: str, context: str = "") -> None:
    """Raise if any forbidden UNB sender/receiver appears in generated text."""
    for val in FORBIDDEN_SENDER_IDS | FORBIDDEN_RECEIVER_IDS:
        if val in text:
            raise ForbiddenProfileError(
                f"Forbidden value {val!r} detected in {context or 'generated output'}. "
                "This value is permanently prohibited."
            )


def validate_masterdata_paths(
    customers_csv: str,
    partners_csv: str,
    materials_csv: str,
) -> None:
    """Verify mandatory master-data CSV files exist.

    Raises:
        ConfigError: If any mandatory file is missing.
    """
    for label, path_str in [
        ("customers", customers_csv),
        ("partners", partners_csv),
        ("materials", materials_csv),
    ]:
        p = Path(path_str)
        if not p.exists():
            raise ConfigError(
                f"Mandatory master-data file not found [{label}]: {path_str}"
            )
        log.info("Master data file confirmed: %s -> %s", label, path_str)


def validate_order_data(order: dict[str, Any]) -> None:
    """Validate extracted order object before EDIFACT generation.

    Args:
        order: Structured order dict from pdf_extractor.

    Raises:
        ValidationError: If any mandatory field is absent or invalid.
    """
    if not order.get("order_number"):
        raise ValidationError("ORDER_NUMBER_MISSING: No order number found in PDF.")
    if not order.get("order_date"):
        raise ValidationError("ORDER_DATE_MISSING: No order date found in PDF.")
    lines = order.get("lines", [])
    if not lines:
        raise ValidationError("NO_ORDER_LINES: No order lines extracted from PDF.")
    for idx, line in enumerate(lines, 1):
        qty_raw = line.get("quantity", "")
        try:
            qty = float(str(qty_raw).replace(",", "."))
        except (ValueError, TypeError):
            raise ValidationError(
                f"INVALID_QUANTITY: Line {idx} has non-numeric quantity: {qty_raw!r}"
            )
        if qty <= 0:
            raise ValidationError(
                f"INVALID_QUANTITY: Line {idx} has non-positive quantity: {qty}"
            )
    log.info(
        "Order pre-validation passed: order_number=%s lines=%d",
        order["order_number"], len(lines),
    )


def validate_sftp_config(sftp_cfg: Any) -> None:
    """Validate SFTP config when SFTP is enabled.

    Args:
        sftp_cfg: SftpConfig dataclass instance.

    Raises:
        ConfigError: If required SFTP fields are absent.
    """
    if not sftp_cfg.enabled:
        log.info("SFTP is disabled in config. Skipping SFTP validation.")
        return
    missing = []
    if not sftp_cfg.host:
        missing.append("SFTP_HOST")
    if not sftp_cfg.username:
        missing.append("SFTP_USERNAME")
    if not sftp_cfg.remote_dir:
        missing.append("SFTP_REMOTE_DIR")
    # Must have password OR private key
    if not sftp_cfg.password and not sftp_cfg.private_key_path:
        missing.append("SFTP_PASSWORD or SFTP_PRIVATE_KEY_PATH")
    if missing:
        raise ConfigError(
            f"SFTP is enabled but missing required config/env: {', '.join(missing)}"
        )
    log.info("SFTP configuration validated: host=%s port=%d", sftp_cfg.host, sftp_cfg.port)


def validate_output_folders_writable(*folder_paths: str) -> None:
    """Ensure local output folders exist and are writable, creating them if needed.

    Raises:
        ValidationError: If a folder cannot be created or is not writable.
    """
    for folder in folder_paths:
        p = Path(folder)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationError(f"Cannot create output folder {folder}: {exc}") from exc
        test_file = p / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except OSError as exc:
            raise ValidationError(f"Output folder not writable {folder}: {exc}") from exc
    log.info("Output folders verified writable: %s", ", ".join(folder_paths))
