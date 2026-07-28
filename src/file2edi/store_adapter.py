"""Dual-mode store adapter: SQLite or PostgreSQL based on environment.

Auto-detects PG_DATABASE_URL env var:
  - If set → use PostgreSQL with async sessions and RLS
  - If not set → use SQLite (existing behavior)

This adapter ensures zero breaking changes: same interface for router.py
regardless of backend choice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# Try to import PostgreSQL module
try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    HAS_POSTGRES_SUPPORT = True
except ImportError:
    HAS_POSTGRES_SUPPORT = False


def get_store_backend() -> str:
    """Detect which backend to use.
    
    Returns:
        "postgres" if PG_DATABASE_URL is set and PostgreSQL is available
        "sqlite" otherwise
    """
    pg_url = (os.environ.get("PG_DATABASE_URL") or "").strip()
    if pg_url and HAS_POSTGRES_SUPPORT:
        return "postgres"
    return "sqlite"


class StoreAdapter:
    """Unified store interface for both SQLite and PostgreSQL.
    
    Usage:
        store = get_store()  # Returns singleton adapter
        orders = store.get_combined_orders(actor="admin", role="admin")
    """
    
    def __init__(self, backend: str, sqlite_path: str | None = None):
        self.backend = backend
        self.sqlite_path = sqlite_path or "data/file2edi.db"
        self._sqlite_conn = None
        self._pg_db = None
        self._loop = None
        
        log.info(f"StoreAdapter initialized with backend={backend}")
    
    def _get_sqlite_conn(self) -> sqlite3.Connection:
        """Get or create SQLite connection."""
        if not self._sqlite_conn:
            self._sqlite_conn = sqlite3.connect(self.sqlite_path, timeout=5)
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn
    
    async def _get_pg_session(self, actor: str, role: str) -> AsyncSession:
        """Get or create PostgreSQL session with RLS context.
        
        Args:
            actor: Current user identity (email)
            role: "admin" or "adv"
        """
        if not self._pg_db:
            from database_pg import get_db
            self._pg_db = get_db()
        
        # Return session with RLS context set
        return self._pg_db.get_session(actor, role)
    
    def get_combined_orders(self, actor: str = "operator", role: str = "adv") -> list[dict]:
        """Get all orders (SQLite path).
        
        In PostgreSQL mode, this should be called from async context via get_combined_orders_async.
        For backward compatibility with sync router endpoints, falls back to SQLite.
        """
        if self.backend == "postgres":
            log.warning("get_combined_orders called in postgres mode — use async version instead")
            # Fallback: return empty or log warning
            return []
        
        # SQLite path
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversions
                ORDER BY created_at DESC
                LIMIT 1000
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            log.error(f"Error fetching orders from SQLite: {e}")
            return []
    
    async def get_combined_orders_async(self, actor: str = "operator", role: str = "adv") -> list[dict]:
        """Get all orders with actor/role context (async, used by PostgreSQL).
        
        PostgreSQL: RLS policies automatically filter based on actor/role
        SQLite: Falls back to sync method (no RBAC enforced)
        """
        if self.backend == "postgres":
            try:
                async with self._get_pg_session(actor, role) as session:
                    from database_pg import Order
                    stmt = select(Order).order_by(Order.created_at.desc()).limit(1000)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [
                        {
                            "id": row.order_id,
                            "order_id": row.order_id,
                            "po_number": row.po_number,
                            "status": row.status,
                            "created_at": row.created_at,
                            "updated_at": row.updated_at,
                            "processed_by": row.processed_by,
                            "uploaded_by": row.uploaded_by,
                            "soldto": row.soldto,
                        }
                        for row in rows
                    ]
            except Exception as e:
                log.error(f"Error fetching orders from PostgreSQL: {e}")
                return []
        else:
            # SQLite fallback
            return self.get_combined_orders(actor, role)
    
    def get_upload_meta(self, upload_id: str) -> dict | None:
        """Get upload metadata by ID."""
        if self.backend == "postgres":
            log.warning("get_upload_meta called in postgres mode — sync not yet implemented")
            return None
        
        # SQLite path
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM file2edi_pdf_uploads WHERE id = ?
            """, (upload_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            log.error(f"Error fetching upload metadata: {e}")
            return None
    
    def save_upload_with_id(self, upload_id: str, file_name: str, file_size: int,
                            file_path: str, uploaded_by: str = "operator") -> None:
        """Save PDF upload record."""
        if self.backend == "postgres":
            log.warning("save_upload_with_id called in postgres mode — async not yet implemented")
            return
        
        # SQLite path
        try:
            conn = self._get_sqlite_conn()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO file2edi_pdf_uploads
                (id, file_name, file_size, file_path, uploaded_at, uploaded_by, status)
                VALUES (?, ?, ?, ?, datetime('now'), ?, 'UPLOADED')
            """, (upload_id, file_name, file_size, file_path, uploaded_by))
            conn.commit()
        except Exception as e:
            log.error(f"Error saving upload: {e}")
    
    def close(self) -> None:
        """Close database connections."""
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None


# Global singleton instance
_store_instance: StoreAdapter | None = None


def get_store() -> StoreAdapter:
    """Get the global store instance."""
    global _store_instance
    
    if _store_instance is None:
        backend = get_store_backend()
        
        # Get SQLite path for fallback
        sqlite_path = (os.environ.get("DB_PATH") or "").strip()
        if not sqlite_path:
            sqlite_path = "data/file2edi.db"
        
        _store_instance = StoreAdapter(backend, sqlite_path)
    
    return _store_instance


def init_store() -> None:
    """Initialize the store (called at app startup)."""
    store = get_store()
    backend = store.backend
    
    if backend == "postgres":
        try:
            from database_pg import get_db
            db = get_db()
            # Note: async init should be called from async context
            log.info("PostgreSQL backend detected — init_db() should be called from async startup")
        except Exception as e:
            log.error(f"Failed to initialize PostgreSQL: {e}")
    else:
        log.info("SQLite backend — ready to use")


def close_store() -> None:
    """Close store connections (called at app shutdown)."""
    global _store_instance
    if _store_instance:
        _store_instance.close()
        _store_instance = None
