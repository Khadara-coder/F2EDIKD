"""Runtime status helpers shared by API health and diagnostics."""

from __future__ import annotations

import os


def is_postgres_strict() -> bool:
    """Return True when PostgreSQL must be available at startup."""
    return os.environ.get("FILE2EDI_POSTGRES_STRICT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_db_backend() -> str:
    """Detect configured database backend: 'postgres' or 'sqlite'."""
    pg_url = (os.environ.get("PG_DATABASE_URL") or "").strip()
    if not pg_url:
        return "sqlite"
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        return "sqlite"
    return "postgres"
