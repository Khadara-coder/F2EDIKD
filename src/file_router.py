"""PDF file routing: moves PDFs to processed or error folders."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .exceptions import FileRoutingError

log = logging.getLogger("edifact.router")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def move_to_processed(pdf_path: Path, processed_dir: str) -> Path:
    """Move a PDF to the processed folder after successful SFTP submission.

    Args:
        pdf_path: Source PDF path.
        processed_dir: Destination folder path string.

    Returns:
        Destination path.

    Raises:
        FileRoutingError: If the move fails.
    """
    dest_dir = Path(processed_dir)
    try:
        _ensure_dir(dest_dir)
        dest = dest_dir / pdf_path.name
        shutil.move(str(pdf_path), str(dest))
        log.info("PDF moved to PROCESSED: %s -> %s", pdf_path.name, dest)
        return dest
    except Exception as exc:
        raise FileRoutingError(
            f"Cannot move PDF to processed: {pdf_path} -> {processed_dir}: {exc}"
        ) from exc


def move_to_error(pdf_path: Path, error_dir: str, reason: str = "") -> Path:
    """Move a PDF to the error folder.

    Args:
        pdf_path: Source PDF path.
        error_dir: Destination folder path string.
        reason: Error reason string appended to log.

    Returns:
        Destination path.

    Raises:
        FileRoutingError: If the move fails.
    """
    dest_dir = Path(error_dir)
    try:
        _ensure_dir(dest_dir)
        dest = dest_dir / pdf_path.name
        shutil.move(str(pdf_path), str(dest))
        log.info(
            "PDF moved to ERROR: %s -> %s reason=%r",
            pdf_path.name, dest, reason,
        )
        return dest
    except Exception as exc:
        raise FileRoutingError(
            f"Cannot move PDF to error folder: {pdf_path} -> {error_dir}: {exc}"
        ) from exc


def archive_tst_submitted(tst_path: Path, archive_dir: str) -> None:
    """Copy a .tst file to the SFTP-submitted archive folder."""
    dest_dir = Path(archive_dir)
    try:
        _ensure_dir(dest_dir)
        dest = dest_dir / tst_path.name
        shutil.copy2(str(tst_path), str(dest))
        log.info("TST archived to sftp_submitted: %s", tst_path.name)
    except Exception as exc:
        log.warning("Could not archive .tst to submitted folder: %s", exc)


def archive_tst_failed(tst_path: Path, archive_dir: str) -> None:
    """Copy a .tst file to the SFTP-failed archive folder."""
    dest_dir = Path(archive_dir)
    try:
        _ensure_dir(dest_dir)
        dest = dest_dir / tst_path.name
        shutil.copy2(str(tst_path), str(dest))
        log.info("TST archived to sftp_failed: %s", tst_path.name)
    except Exception as exc:
        log.warning("Could not archive .tst to failed folder: %s", exc)


def list_pdfs(inbox_dir: str) -> list[Path]:
    """Return sorted list of PDF files in the inbox directory."""
    p = Path(inbox_dir)
    if not p.exists():
        log.warning("PDF inbox does not exist: %s", inbox_dir)
        return []
    pdfs = sorted(p.glob("*.pdf")) + sorted(p.glob("*.PDF"))
    log.info("PDF inbox scan: %s -> %d file(s)", inbox_dir, len(pdfs))
    return pdfs


def write_local_tst_atomically(content: str, dest_path: Path) -> None:
    """Write EDIFACT .tst content atomically using a temp file.

    Args:
        content: EDIFACT message string.
        dest_path: Final destination path for the .tst file.

    Raises:
        FileRoutingError: If write fails.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(dest_path)
        log.info("TST written atomically: %s (%d bytes)", dest_path.name, len(content))
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise FileRoutingError(
            f"Cannot write .tst file {dest_path}: {exc}"
        ) from exc
