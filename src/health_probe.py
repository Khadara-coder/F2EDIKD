"""Local health probe used by /api/health/system and proxy health."""

from __future__ import annotations

import os
from typing import Any


def build_proxy_health(
    *,
    sender_gln: str = "",
    receiver_gln: str = "",
    storage_mode: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build structured health payload without importing server."""
    from src.masterdata_runtime import CACHE, stats as masterdata_stats, sync_freshness
    from src.runtime_status import get_db_backend
    from src.sftp_delivery import is_configured_from_env

    local_md = masterdata_stats()
    md_sync = sync_freshness()
    md_rows_ok = all(v.get("rows", 0) > 0 for v in local_md.values()) if local_md else False
    md_schema_ok = all(
        v.get("schema_valid", True) is not False for v in local_md.values()
    ) if local_md else True

    pg_url = (os.environ.get("PG_DATABASE_URL") or "").strip()
    db_backend = get_db_backend()
    db_ok = False
    if pg_url:
        try:
            import psycopg
            from src.file2edi.store import _normalize_postgres_url

            with psycopg.connect(_normalize_postgres_url(pg_url), connect_timeout=2) as conn:
                conn.execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            db_ok = False

    storage = storage_mode or {"backend": db_backend, "persistent": bool(pg_url)}
    sender = sender_gln or os.environ.get("UNB_SENDER_GLN", "4399901876613")
    receiver = receiver_gln or os.environ.get("UNB_RECEIVER_GLN", "3015981600108")

    return {
        "ok": True,
        "status": "ok",
        "api": {"ok": True, "status": "ok", "version": "2.1.0"},
        "database": {
            "ok": db_ok,
            "status": "ok" if db_ok else "ERROR",
            "backend": db_backend if pg_url else storage.get("backend", "sqlite"),
        },
        "masterdata": {
            "ok": md_rows_ok,
            "schema_ok": md_schema_ok,
            "sync": md_sync,
        },
        "profile": {
            "name": "ELM_STANDARD",
            "syntax": "UNOC:3",
            "message": "ORDERS D.96A",
            "sender_gln": sender,
            "receiver_gln": receiver,
            "locked": True,
        },
        "storage_mode": storage,
        "local": {
            "status": "ok",
            "profile": "ELM_STANDARD",
            "sender_gln": sender,
            "receiver_gln": receiver,
        },
        "db_ok": db_ok,
        "sftp_configured": is_configured_from_env(),
        "f2edi_base": "local",
        "mc_status": {
            k: {"rows": v.get("rows", 0), "loaded_at": v.get("loaded_at")}
            for k, v in CACHE.items()
        },
        "masterdata_sync": md_sync,
    }
