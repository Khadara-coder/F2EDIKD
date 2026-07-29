"""PostgreSQL database layer for EDIFACT File2EDI.

Uses SQLAlchemy ORM + Row-Level Security (RLS) for RBAC enforcement at DB level.
Replaces src/file2edi/store.py for production; SQLite fallback remains for local dev.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

log = logging.getLogger(__name__)

Base = declarative_base()


# ─────────────────────────────────────────────────────────────────────────────
# ORM Models
# ─────────────────────────────────────────────────────────────────────────────


class AuthUser(Base):
    """Application user with role and ADV scope."""

    __tablename__ = "auth_users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    role = Column(String(10), nullable=False, default="adv")  # 'admin' or 'adv'
    active = Column(Integer, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    adv_scopes = relationship("AuthUserAdvScope", back_populates="user", cascade="all, delete-orphan")


class AuthUserAdvScope(Base):
    """Maps an ADV user to their allowed sold-to codes."""

    __tablename__ = "auth_user_adv_scope"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("auth_users.id"), nullable=False, index=True)
    soldto = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    user = relationship("AuthUser", back_populates="adv_scopes")


class PdfUpload(Base):
    """PDF file upload metadata."""

    __tablename__ = "file2edi_pdf_uploads"

    upload_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    uploaded_by = Column(String(255), nullable=False, default="operator")
    status = Column(String(20), default="RECEIVED")

    # Relationship
    orders = relationship("Order", back_populates="upload")


class Order(Base):
    """File2EDI order (unified view of extraction + conversions)."""

    __tablename__ = "file2edi_orders"

    order_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String(36), ForeignKey("file2edi_pdf_uploads.upload_id"), nullable=True, index=True)
    
    # Order identifiers
    file_name = Column(String(255), nullable=True)
    client_name = Column(String(255), nullable=True)
    customer_order_number = Column(String(100), nullable=True)
    document_reference = Column(String(100), nullable=True)
    
    # Dates
    order_date = Column(String(20), nullable=True)
    requested_delivery_date = Column(String(20), nullable=True)
    
    # Terms
    currency = Column(String(3), default="EUR")
    incoterm = Column(String(10), default="DAP")
    delivery_mode = Column(String(50), nullable=True)
    message_type = Column(String(20), default="ORDERS")
    
    # Extraction metadata
    vendor = Column(String(255), nullable=True)
    total_amount = Column(Float, default=0.0)
    global_confidence = Column(Float, default=0.0)
    line_count = Column(Integer, default=0)
    
    # PDF tracking
    pdf_hash = Column(String(64), nullable=True)
    pdf_path = Column(String(512), nullable=True)
    
    # EDIFACT output
    edifact_content = Column(Text, nullable=True)
    edifact_filename = Column(String(255), nullable=True)
    
    # Extraction & corrections (JSONB in PG, TEXT in SQLite)
    extraction_json = Column(JSON, nullable=True)
    corrections_json = Column(JSON, nullable=True)
    
    # RBAC & Workflow
    status = Column(String(50), default="Revue requise", index=True)
    review_required = Column(Integer, default=1)
    
    # ← NEW: RBAC fields
    processed_by = Column(String(255), nullable=True, index=True)  # email/actor assigned to process this
    soldto = Column(String(20), nullable=True, index=True)  # DENORMALIZED from extraction for query performance
    uploaded_by = Column(String(255), nullable=False, default="operator")
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    upload = relationship("PdfUpload", back_populates="orders")
    partners = relationship("OrderPartner", back_populates="order", cascade="all, delete-orphan")
    lines = relationship("OrderLine", back_populates="order", cascade="all, delete-orphan")
    anomalies = relationship("OrderAnomaly", back_populates="order", cascade="all, delete-orphan")


class OrderPartner(Base):
    """Order partner (buyer, vendor, ship-to, etc.)."""

    __tablename__ = "file2edi_order_partners"

    partner_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("file2edi_orders.order_id"), nullable=False, index=True)
    
    # Partner data
    partner_function = Column(String(10), nullable=False)  # 'soldto', 'shipto', 'vendor', etc.
    partner_code = Column(String(20), nullable=True)
    partner_name = Column(String(255), nullable=True)
    
    # Address
    address_line_1 = Column(String(255), nullable=True)
    address_line_2 = Column(String(255), nullable=True)
    postal_code = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="FR")
    
    # Extraction metadata
    confidence = Column(Float, default=0.0)
    manually_edited = Column(Integer, default=0)
    edited_fields_json = Column(JSON, nullable=True)
    previous_value = Column(Text, nullable=True)

    # Relationship
    order = relationship("Order", back_populates="partners")


class OrderLine(Base):
    """Order line item."""

    __tablename__ = "file2edi_order_lines"

    line_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("file2edi_orders.order_id"), nullable=False, index=True)
    
    # Line data
    line_number = Column(Integer, nullable=False)
    customer_reference = Column(String(100), nullable=True)
    bosch_article = Column(String(50), nullable=True)
    designation = Column(String(255), nullable=True)
    
    # Quantities
    quantity = Column(Float, default=0.0)
    unit = Column(String(10), default="PCE")
    unit_price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    
    # Extraction metadata
    confidence = Column(Float, default=0.0)
    status = Column(String(20), default="OK")
    comment = Column(Text, nullable=True)
    manually_edited = Column(Integer, default=0)

    # Relationship
    order = relationship("Order", back_populates="lines")


class OrderAnomaly(Base):
    """Order-level or line-level anomaly/validation issue."""

    __tablename__ = "file2edi_order_anomalies"

    anomaly_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("file2edi_orders.order_id"), nullable=False, index=True)
    line_id = Column(String(36), nullable=True)  # NULL if order-level
    
    severity = Column(String(20), default="warning")  # 'warning', 'error', 'critical'
    field_name = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="Ouverte")
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    order = relationship("Order", back_populates="anomalies")


class ConversionHistory(Base):
    """EDIFACT conversion history (one row per generation)."""

    __tablename__ = "file2edi_conversion_history"

    conversion_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("file2edi_orders.order_id"), nullable=False, index=True)
    
    file_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    edifact_path = Column(String(512), nullable=True)
    
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_by = Column(String(255), default="system")


class JobsLedger(Base):
    """Legacy jobs ledger (replaces old schema.sql jobs table + CSV deduplication)."""

    __tablename__ = "jobs_ledger"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_filename = Column(String(255), nullable=False)
    source_path = Column(String(512), nullable=False)
    po_number = Column(String(100), nullable=True, index=True)
    soldto = Column(String(20), nullable=True, index=True)
    
    status = Column(String(20), nullable=False, default="RECEIVED")  # RECEIVED | PROCESSING | COMPLETED | REJECTED | DUPLICATE | FAILED
    rejection_reason = Column(Text, nullable=True)
    
    output_filename = Column(String(255), nullable=True)
    output_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdvContact(Base):
    """ADV contact (maps sold-to → ADV email/department)."""

    __tablename__ = "adv_contacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    soldto = Column(String(20), nullable=False, index=True)
    dept = Column(String(10), nullable=True)  # postal[0:2] DEPT code
    email = Column(String(255), nullable=False)
    active = Column(Integer, default=1)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Database Connection Manager
# ─────────────────────────────────────────────────────────────────────────────


class PostgresDB:
    """PostgreSQL connection manager with RLS support."""

    def __init__(self, database_url: str | None = None):
        """
        Args:
            database_url: e.g., 'postgresql+psycopg://user:pass@host/dbname'
                         if None, uses PG_DATABASE_URL env var or falls back to SQLite
        """
        self.database_url = database_url or os.getenv("PG_DATABASE_URL")
        self.is_postgres = self.database_url and "postgresql" in self.database_url
        
        if self.is_postgres:
            # Async engine for production
            self.engine = create_async_engine(
                self.database_url,
                echo=os.getenv("SQL_ECHO", "false").lower() == "true",
                pool_size=10,
                max_overflow=20,
            )
            self.SessionLocal = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
            )
        else:
            log.warning("PostgreSQL not configured; using SQLite fallback")
            self.engine = None
            self.SessionLocal = None

    async def init_db(self) -> None:
        """Create all tables and initialize RLS policies."""
        if not self.is_postgres:
            log.info("Skipping DB init (SQLite mode)")
            return

        # Step 1: create tables (own transaction)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Step 2: RLS setup (idempotent, separate transaction per statement)
        rls_statements = [
            "ALTER TABLE file2edi_orders ENABLE ROW LEVEL SECURITY;",
            """
            DO $$ BEGIN
              CREATE POLICY adv_orders_select ON file2edi_orders
              FOR SELECT USING (
                current_setting('app.current_role', true)::TEXT = 'admin'
                OR processed_by = current_setting('app.current_user', true)::TEXT
                OR soldto IN (
                  SELECT soldto FROM auth_user_adv_scope
                  WHERE user_id = (SELECT id FROM auth_users
                                   WHERE email = current_setting('app.current_user', true)::TEXT)
                )
              );
            EXCEPTION WHEN duplicate_object THEN NULL; END $$;
            """,
            """
            DO $$ BEGIN
              CREATE POLICY adv_orders_update ON file2edi_orders
              FOR UPDATE USING (
                current_setting('app.current_role', true)::TEXT = 'admin'
                OR processed_by = current_setting('app.current_user', true)::TEXT
                OR soldto IN (
                  SELECT soldto FROM auth_user_adv_scope
                  WHERE user_id = (SELECT id FROM auth_users
                                   WHERE email = current_setting('app.current_user', true)::TEXT)
                )
              );
            EXCEPTION WHEN duplicate_object THEN NULL; END $$;
            """,
        ]
        for stmt in rls_statements:
            try:
                async with self.engine.begin() as conn:
                    await conn.execute(text(stmt))
            except Exception as e:
                log.warning(f"RLS policy init (may already exist): {e}")
        log.info("RLS policies initialized")

    @asynccontextmanager
    async def get_session(self, actor: str | None = None, role: str = "adv") -> AsyncGenerator[AsyncSession, None]:
        """
        Yield an async session with RLS context set for the given actor.
        
        Args:
            actor: User email/identifier for RLS filtering
            role: 'admin' or 'adv' (controls which RLS policies apply)
        """
        if not self.is_postgres:
            raise RuntimeError("PostgreSQL not configured")

        async with self.SessionLocal() as session:
            # Set RLS context variables before queries (parameterised to prevent injection)
            if actor:
                await session.execute(text("SELECT set_config('app.current_user', :v, true)"), {"v": actor})
                await session.execute(text("SELECT set_config('app.current_role', :v, true)"), {"v": role})
            
            yield session

    async def get_orders(
        self, session: AsyncSession, actor: str | None = None, 
        status_filter: str | None = None, limit: int = 200
    ) -> list[Order]:
        """
        Fetch orders, respecting RLS for ADV users.
        If actor is None or role='admin', no additional filtering.
        """
        query = select(Order).order_by(Order.created_at.desc()).limit(limit)
        
        if status_filter:
            query = query.where(Order.status == status_filter)
        
        result = await session.execute(query)
        return result.scalars().all()

    async def get_order_by_id(self, session: AsyncSession, order_id: str) -> Order | None:
        """Fetch a single order by ID (RLS checks access)."""
        result = await session.execute(
            select(Order).where(Order.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def save_order(self, session: AsyncSession, order_data: dict) -> Order:
        """Create or update an order."""
        order_id = order_data.get("order_id") or str(uuid.uuid4())
        
        stmt = select(Order).where(Order.order_id == order_id)
        existing = await session.scalar(stmt)
        
        if existing:
            for key, val in order_data.items():
                if key != "order_id":
                    setattr(existing, key, val)
            order = existing
        else:
            order = Order(**order_data, order_id=order_id)
            session.add(order)
        
        await session.flush()
        return order

    async def close(self) -> None:
        """Close the database connection pool."""
        if self.engine:
            await self.engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Global instance
# ─────────────────────────────────────────────────────────────────────────────

_db_instance: PostgresDB | None = None


def get_db() -> PostgresDB:
    """Get or create the global DB instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PostgresDB()
    return _db_instance
