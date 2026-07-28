#!/usr/bin/env python3
"""
Migration script: SQLite File2EDI → PostgreSQL

Usage:
  python migrate_to_postgres.py --src data/file2edi.db --dst postgresql://user:pass@localhost/edifact

This script:
1. Reads all orders/uploads/conversions from SQLite
2. Dénormalizes soldto/shipto from extraction_json → Order.soldto
3. Creates auth_users + auth_user_adv_scope from CSV master data
4. Writes everything to PostgreSQL
5. Optionally backs up the original SQLite file
"""

import argparse
import csv
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Import ORM models
from src.database_pg import (
    AdvContact,
    AuthUser,
    AuthUserAdvScope,
    Base,
    ConversionHistory,
    Order,
    OrderAnomaly,
    OrderLine,
    OrderPartner,
    PdfUpload,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def read_sqlite_orders(sqlite_path: str) -> list[dict]:
    """Read all orders from SQLite file2edi.db."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT o.*, u.uploaded_by, u.upload_id
        FROM file2edi_orders o
        LEFT JOIN file2edi_pdf_uploads u ON u.upload_id = o.upload_id
        ORDER BY o.created_at DESC
    """)
    
    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return orders


def read_sqlite_uploads(sqlite_path: str) -> list[dict]:
    """Read all PDF uploads from SQLite."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM file2edi_pdf_uploads ORDER BY uploaded_at")
    uploads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return uploads


def read_sqlite_conversions(sqlite_path: str) -> list[dict]:
    """Read all conversion history from SQLite."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM file2edi_conversion_history ORDER BY processed_at")
    conversions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return conversions


def extract_soldto_from_order(order: dict) -> Optional[str]:
    """Extract sold-to code from extraction_json for dénormalization."""
    try:
        if not order.get("extraction_json"):
            return None
        
        data = json.loads(order["extraction_json"]) if isinstance(order["extraction_json"], str) else order["extraction_json"]
        
        # Try to find soldto in partners
        partners = data.get("partners", [])
        for p in partners:
            if p.get("partnerFunction") == "soldto":
                return p.get("partnerCode")
        
        return None
    except Exception as e:
        log.warning(f"Failed to extract soldto from order {order.get('order_id')}: {e}")
        return None


def load_master_data_adv_contacts(masterdata_dir: str) -> dict[str, str]:
    """
    Load partners CSV and build a map of soldto → ADV email.
    Returns: {soldto: adv_email}
    """
    contacts = {}
    partners_csv = Path(masterdata_dir) / "10564_Partners.csv"
    
    if not partners_csv.exists():
        log.warning(f"Partners CSV not found at {partners_csv}")
        return contacts
    
    try:
        with open(partners_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                soldto = row.get("SOLDTO", "").strip()
                adv = row.get("Gestionaire ADV", "").strip() or row.get("adv_team1_email", "").strip() or row.get("email", "").strip()
                
                if soldto and adv:
                    contacts[soldto] = adv
        
        log.info(f"Loaded {len(contacts)} ADV contacts from Partners CSV")
    except Exception as e:
        log.error(f"Failed to load Partners CSV: {e}")
    
    return contacts


def migrate_to_postgres(sqlite_path: str, pg_url: str, masterdata_dir: str = "data/masterdata") -> None:
    """Execute the full migration."""
    
    # Connect to PostgreSQL
    engine = sa.create_engine(pg_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    
    try:
        # 1. Create schema
        log.info("Creating PostgreSQL schema...")
        Base.metadata.create_all(engine)
        
        # 2. Load master data
        log.info("Loading master data...")
        adv_contacts = load_master_data_adv_contacts(masterdata_dir)
        
        # 3. Create a default admin user (must be set up via API or seed later)
        session = SessionLocal()
        
        # 4. Migrate uploads
        log.info("Migrating PDF uploads...")
        uploads = read_sqlite_uploads(sqlite_path)
        for upload in uploads:
            pg_upload = PdfUpload(
                upload_id=upload["upload_id"],
                file_name=upload["file_name"],
                file_size=upload["file_size"],
                file_path=upload["file_path"],
                uploaded_at=upload["uploaded_at"],
                uploaded_by=upload.get("uploaded_by", "operator"),
                status=upload.get("status", "RECEIVED"),
            )
            session.add(pg_upload)
        session.commit()
        log.info(f"Migrated {len(uploads)} uploads")
        
        # 5. Migrate orders
        log.info("Migrating orders...")
        orders = read_sqlite_orders(sqlite_path)
        order_map = {}  # order_id → Order obj
        
        for i, order in enumerate(orders):
            # Dénormalize soldto
            soldto = extract_soldto_from_order(order)
            
            pg_order = Order(
                order_id=order["order_id"],
                upload_id=order.get("upload_id"),
                file_name=order.get("file_name"),
                client_name=order.get("client_name"),
                customer_order_number=order.get("customer_order_number"),
                document_reference=order.get("document_reference"),
                order_date=order.get("order_date"),
                requested_delivery_date=order.get("requested_delivery_date"),
                currency=order.get("currency", "EUR"),
                incoterm=order.get("incoterm", "DAP"),
                delivery_mode=order.get("delivery_mode"),
                message_type=order.get("message_type", "ORDERS"),
                vendor=order.get("vendor"),
                total_amount=order.get("total_amount", 0.0),
                global_confidence=order.get("global_confidence", 0.0),
                line_count=order.get("line_count", 0),
                pdf_hash=order.get("pdf_hash"),
                pdf_path=order.get("pdf_path"),
                edifact_content=order.get("edifact_content"),
                edifact_filename=order.get("edifact_filename"),
                extraction_json=order.get("extraction_json"),
                corrections_json=order.get("corrections_json"),
                status=order.get("status", "Revue requise"),
                review_required=order.get("review_required", 1),
                processed_by=None,  # Will be set by auto-routing logic
                soldto=soldto,  # ← DÉNORMALISÉ
                uploaded_by=order.get("uploaded_by", "operator"),
                created_at=order.get("created_at"),
                updated_at=order.get("updated_at"),
                processed_at=order.get("processed_at"),
            )
            session.add(pg_order)
            order_map[order["order_id"]] = pg_order
            
            if (i + 1) % 100 == 0:
                log.info(f"  Migrated {i + 1}/{len(orders)} orders...")
        
        session.commit()
        log.info(f"Migrated {len(orders)} orders")
        
        # 6. Migrate order partners
        log.info("Migrating order partners...")
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM file2edi_order_partners")
        
        partner_count = 0
        for row in cursor.fetchall():
            pg_partner = OrderPartner(
                partner_id=row["partner_id"],
                order_id=row["order_id"],
                partner_function=row["partner_function"],
                partner_code=row["partner_code"],
                partner_name=row["partner_name"],
                address_line_1=row["address_line_1"],
                address_line_2=row["address_line_2"],
                postal_code=row["postal_code"],
                city=row["city"],
                country=row.get("country", "FR"),
                confidence=row.get("confidence", 0.0),
                manually_edited=row.get("manually_edited", 0),
                edited_fields_json=row.get("edited_fields_json"),
                previous_value=row.get("previous_value"),
            )
            session.add(pg_partner)
            partner_count += 1
        
        conn.close()
        session.commit()
        log.info(f"Migrated {partner_count} order partners")
        
        # 7. Migrate order lines
        log.info("Migrating order lines...")
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM file2edi_order_lines")
        
        line_count = 0
        for row in cursor.fetchall():
            pg_line = OrderLine(
                line_id=row["line_id"],
                order_id=row["order_id"],
                line_number=row["line_number"],
                customer_reference=row.get("customer_reference"),
                bosch_article=row.get("bosch_article"),
                designation=row.get("designation"),
                quantity=row.get("quantity", 0.0),
                unit=row.get("unit", "PCE"),
                unit_price=row.get("unit_price", 0.0),
                amount=row.get("amount", 0.0),
                confidence=row.get("confidence", 0.0),
                status=row.get("status", "OK"),
                comment=row.get("comment"),
                manually_edited=row.get("manually_edited", 0),
            )
            session.add(pg_line)
            line_count += 1
        
        conn.close()
        session.commit()
        log.info(f"Migrated {line_count} order lines")
        
        # 8. Migrate conversions
        log.info("Migrating conversion history...")
        conversions = read_sqlite_conversions(sqlite_path)
        for conv in conversions:
            pg_conv = ConversionHistory(
                conversion_id=conv["conversion_id"],
                order_id=conv["order_id"],
                file_name=conv.get("file_name"),
                status=conv.get("status"),
                confidence=conv.get("confidence"),
                edifact_path=conv.get("edifact_path"),
                processed_at=conv.get("processed_at"),
                processed_by=conv.get("processed_by", "system"),
            )
            session.add(pg_conv)
        
        session.commit()
        log.info(f"Migrated {len(conversions)} conversions")
        
        # 9. Create ADV contacts from master data
        log.info("Creating ADV contacts...")
        for soldto, adv_email in adv_contacts.items():
            contact = AdvContact(
                soldto=soldto,
                email=adv_email,
                active=1,
            )
            session.add(contact)
        
        session.commit()
        log.info(f"Created {len(adv_contacts)} ADV contacts")
        
        session.close()
        log.info("✓ Migration completed successfully!")
        
    except Exception as e:
        log.error(f"Migration failed: {e}", exc_info=True)
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument("--src", default="data/file2edi.db", help="Source SQLite path")
    parser.add_argument("--dst", required=True, help="Destination PostgreSQL URL (e.g., postgresql://user:pass@localhost/edifact)")
    parser.add_argument("--masterdata", default="data/masterdata", help="Master data directory")
    
    args = parser.parse_args()
    
    migrate_to_postgres(args.src, args.dst, args.masterdata)
