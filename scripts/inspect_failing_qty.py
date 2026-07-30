#!/usr/bin/env python3
"""Inspect raw extraction_json for failing orders to understand quantity issue."""
import sqlite3
import json

conn = sqlite3.connect("data/file2edi.db")
conn.row_factory = sqlite3.Row

# Get orders with qty=0 and their extraction_json
failing_orders = conn.execute("""
    SELECT o.order_id, o.file_name, o.extraction_json
    FROM file2edi_orders o
    JOIN file2edi_order_lines l ON l.order_id = o.order_id
    WHERE (l.quantity IS NULL OR CAST(l.quantity AS FLOAT) = 0)
    GROUP BY o.order_id
    ORDER BY o.created_at DESC
    LIMIT 5
""").fetchall()

for o in failing_orders:
    fname = (o["file_name"] or "")[:60]
    print(f"\n{'='*70}")
    print(f"FILE: {fname}")
    print(f"{'='*70}")
    if not o["extraction_json"]:
        print("  No extraction_json stored")
        continue
    try:
        data = json.loads(o["extraction_json"])
        # Show raw line items before sanitization
        raw_lines = (
            data.get("order_lines")
            or data.get("line_items")
            or data.get("lignes")
            or data.get("lines")
            or []
        )
        print(f"  Raw lines extracted: {len(raw_lines)}")
        for i, l in enumerate(raw_lines[:6]):
            print(f"  [{i}] {json.dumps(l, ensure_ascii=False)}")
        # Show what keys exist
        print(f"  Keys in extraction_json: {list(data.keys())}")
    except Exception as e:
        print(f"  Error parsing: {e}")
        print(f"  Raw (first 500): {str(o['extraction_json'])[:500]}")

conn.close()
