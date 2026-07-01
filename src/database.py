"""SQLite connection manager for EDIFACT Standalone Orchestrator.

Used in API/worker mode only. Batch mode uses CSV ledgers instead.
Schema lives in data/schema.sql relative to the project root.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def _project_root() -> Path:
    """Return the EDIFACT project root (parent of this src/ directory)."""
    return Path(__file__).resolve().parent.parent


def _get_db_path() -> Path:
    """Return the SQLite database path, env-overridable."""
    return Path(os.getenv("DB_PATH", str(_project_root() / "data" / "edifact_standalone.db")))


def _ensure_directories() -> None:
    """Create all runtime directories if they do not exist."""
    root = _project_root()
    dirs = [
        Path(os.getenv("DATA_DIR",      str(root / "data"))),
        Path(os.getenv("INTAKE_DIR",    str(root / "data" / "intake"))),
        Path(os.getenv("PROCESSED_DIR", str(root / "data" / "processed"))),
        Path(os.getenv("REJECT_DIR",    str(root / "data" / "reject"))),
        Path(os.getenv("OUTBOX_DIR",    str(root / "data" / "outbox"))),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield an auto-commit SQLite connection with Row factory."""
    _ensure_directories()
    conn = sqlite3.connect(str(_get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_database() -> None:
    """Create schema tables if they do not exist.

    Idempotent — safe to call on every startup.
    """
    _ensure_directories()
    schema_path = _project_root() / "data" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with get_connection() as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
