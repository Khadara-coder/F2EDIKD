#!/usr/bin/env python3
"""Deep inspect of extraction_json lines for failing orders."""
import sqlite3
import json

conn = sqlite3.connect("data/file2edi.db")
conn.row_factory = sqlite3.Row

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
        raw_str = o["extraction_json"]
        if isinstance(raw_str, bytes):
            raw_str = raw_str.decode()
        data = json.loads(raw_str)
        # Find lines in nested structure
        def find_lines(d, depth=0):
            if isinstance(d, list):
                for item in d:
                    if isinstance(item, dict):
                        keys = set(item.keys())
                        if any(k in keys for k in ("code_article", "article", "quantite", "quantity", "bosch_article")):
                            print(f"  {'  '*depth}LINE: {json.dumps(item, ensure_ascii=False)[:200]}")
                        else:
                            find_lines(item, depth+1)
            elif isinstance(d, dict):
                for k, v in d.items():
                    if k in ("order_lines", "line_items", "lignes", "lines", "items"):
                        print(f"  Key '{k}': {len(v) if isinstance(v, list) else type(v).__name__}")
                        find_lines(v, depth+1)
                    elif isinstance(v, (dict, list)):
                        find_lines(v, depth+1)
        find_lines(data)
    except Exception as e:
        print(f"  Error: {e}")
        import traceback; traceback.print_exc()

conn.close()
