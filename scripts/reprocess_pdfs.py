#!/usr/bin/env python3
"""Reprocess all PDFs in data/intake/ to validate extraction improvements."""
import asyncio
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extraction import extract_purchase_order
from src.file2edi.store import File2EdiStore

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "file2edi.db"
INTAKE_PATH = Path(__file__).resolve().parents[1] / "data" / "intake"

store = File2EdiStore(str(DB_PATH), str(INTAKE_PATH))

def reprocess():
    """Reprocess PDFs and update database."""
    pdfs = list(INTAKE_PATH.glob("*.pdf"))
    print(f"\n{'='*80}")
    print(f"REPROCESSING {len(pdfs)} PDFs")
    print(f"{'='*80}\n")
    
    # Clear old data
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM file2edi_order_lines")
    conn.execute("DELETE FROM file2edi_orders")
    conn.execute("DELETE FROM file2edi_order_anomalies")
    conn.commit()
    conn.close()
    print(f"✓ Cleared database")
    
    processed = 0
    failed = 0
    
    for pdf_path in sorted(pdfs)[:50]:  # Limit to 50 for quick test
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            
            print(f"Processing {pdf_path.name}...", end=" ")
            
            # Extract order
            result = extract_purchase_order(
                pdf_bytes,
                pdf_path.name,
                source="api"  # Mark as from API for traceability
            )
            
            if result and result.get("order_id"):
                order_id = result["order_id"]
                review = {
                    "order": result,
                    "partners": result.get("partners", []),
                    "lines": result.get("lignes", []),
                }
                
                # Store order
                try:
                    store.save_order_review(order_id, review)
                    print(f"✓ {order_id} ({len(result.get('lignes', []))} lines)")
                    processed += 1
                except Exception as e:
                    print(f"❌ Store failed: {e}")
                    failed += 1
            else:
                print(f"❌ Extraction returned no order_id")
                failed += 1
        except Exception as e:
            print(f"❌ {e}")
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"DONE: {processed} processed, {failed} failed")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    reprocess()
