"""SQLite repository for EDIFACT Standalone Orchestrator.

All writes are transactional via get_connection() context manager.
Dedupe key uses the 3-component n8n rule: order_number + soldto + pdf_sha256.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .database import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _file_sha256(path: Path) -> str:
    """Return SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------ #
# Job CRUD
# ------------------------------------------------------------------ #

def create_job(
    source_filename: str,
    source_path: Path,
    po_number: str | None = None,
    soldto: str | None = None,
) -> str:
    """Insert a new job row and a JOB_CREATED event. Return the job UUID."""
    job_id = str(uuid.uuid4())
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
              id, source_filename, source_path, po_number, soldto, status,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'RECEIVED', ?, ?)
            """,
            (job_id, source_filename, str(source_path), po_number, soldto, now, now),
        )
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, details, created_at) VALUES (?, ?, ?, ?)",
            (job_id, "JOB_CREATED", json.dumps({"source_filename": source_filename}), now),
        )
    return job_id


def list_jobs(limit: int = 100) -> list[dict]:
    """Return the most recent `limit` jobs, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id: str) -> dict | None:
    """Return a single job row or None."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def update_job_status(
    job_id: str,
    status: str,
    *,
    rejection_reason: str | None = None,
    output_filename: str | None = None,
    output_path: str | None = None,
    error_message: str | None = None,
    soldto: str | None = None,
) -> None:
    """Update job status and append a JOB_STATUS_CHANGED event."""
    now = _now_iso()
    with get_connection() as conn:
        if soldto is not None:
            conn.execute(
                """
                UPDATE jobs
                SET status=?, rejection_reason=?, output_filename=?, output_path=?,
                    error_message=?, soldto=?, updated_at=?
                WHERE id=?
                """,
                (status, rejection_reason, output_filename, output_path,
                 error_message, soldto, now, job_id),
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET status=?, rejection_reason=?, output_filename=?, output_path=?,
                    error_message=?, updated_at=?
                WHERE id=?
                """,
                (status, rejection_reason, output_filename, output_path,
                 error_message, now, job_id),
            )
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, details, created_at) VALUES (?, ?, ?, ?)",
            (
                job_id,
                "JOB_STATUS_CHANGED",
                json.dumps({
                    "status": status,
                    "rejection_reason": rejection_reason,
                    "output_filename": output_filename,
                    "error_message": error_message,
                }),
                now,
            ),
        )


def append_event(job_id: str, event_type: str, details: dict | None = None) -> None:
    """Append an audit event to job_events."""
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, details, created_at) VALUES (?, ?, ?, ?)",
            (job_id, event_type, json.dumps(details or {}), now),
        )


def reserve_next_job() -> dict | None:
    """Atomically claim the oldest RECEIVED/RETRY job. Return it or None."""
    now = _now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('RECEIVED','RETRY') ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]
        conn.execute(
            "UPDATE jobs SET status='PROCESSING', updated_at=? WHERE id=?",
            (now, job_id),
        )
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, details, created_at) VALUES (?, ?, '{}', ?)",
            (job_id, "JOB_RESERVED", now),
        )
    return get_job(job_id)


# ------------------------------------------------------------------ #
# Dedupe ledger
# ------------------------------------------------------------------ #

def check_and_record_duplicate(
    po_number: str,
    soldto: str,
    source_path: Path,
) -> bool:
    """Return True if this (po_number, soldto, pdf_sha256) triple was already seen.

    3-component key per n8n duplicate detection rules.
    If first occurrence, inserts a dedupe_ledger row and returns False.
    """
    file_hash = _file_sha256(source_path)
    dedupe_key = f"{po_number}:{soldto}:{file_hash}"
    now = _now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, hit_count FROM dedupe_ledger WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE dedupe_ledger SET hit_count=?, last_seen_at=? WHERE id=?",
                (row["hit_count"] + 1, now, row["id"]),
            )
            return True
        conn.execute(
            """
            INSERT INTO dedupe_ledger
              (dedupe_key, po_number, soldto, source_hash, first_seen_at, last_seen_at, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (dedupe_key, po_number, soldto, file_hash, now, now),
        )
        return False
