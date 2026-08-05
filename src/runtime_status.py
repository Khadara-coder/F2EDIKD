"""Runtime status helpers shared by API health and diagnostics."""

from __future__ import annotations

import os


def is_postgres_strict() -> bool:
    """Return True when PostgreSQL must be available at startup.

    File2EDI always requires PG_DATABASE_URL; this flag remains for
    compose/CI compatibility and health diagnostics.
    """
    return os.environ.get("FILE2EDI_POSTGRES_STRICT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_db_backend() -> str:
    """Detect configured database backend: 'postgres' or 'unconfigured'."""
    pg_url = (os.environ.get("PG_DATABASE_URL") or "").strip()
    if not pg_url:
        return "unconfigured"
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        return "unconfigured"
    return "postgres"
