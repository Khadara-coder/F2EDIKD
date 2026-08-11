#!/usr/bin/env python3
"""
Backfill Phase 3 - Reprocesser les lignes existantes avec les nouveaux extracteurs.

Pour chaque ligne dans file2edi_order_lines:
- Extrait payment_terms et special_instructions depuis la designation
- Extrait delivery_date depuis la designation ou les champs existants
- Extrait warnings depuis la designation
- Met à jour la ligne si des valeurs sont trouvées

Idempotent: ne remplace que les valeurs NULL.
"""
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.environ.get("DB_PATH", "/app/data/file2edi.db")


def backfill(db_path: str):
    from app.engines.delivery_date import extract_delivery_date, extract_delivery_urgency
    from app.engines.special_instructions import extract_special_instructions, extract_warnings
    from app.line_items import _extract_customer_reference, _extract_payment_terms

    print(f"Backfill → {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT line_id, designation, customer_reference,
               payment_terms, delivery_date, special_instructions, warnings
        FROM file2edi_order_lines
    """).fetchall()

    print(f"  {len(rows)} lignes à traiter")

    updated = 0
    for row in rows:
        line_id = row["line_id"]
        text = row["designation"] or ""

        updates = {}

        # payment_terms - uniquement si NULL et designation a du contenu
        if row["payment_terms"] is None and text:
            terms = _extract_payment_terms(text)
            if terms:
                updates["payment_terms"] = terms

        # delivery_date - uniquement si NULL
        if row["delivery_date"] is None and text:
            ddate = extract_delivery_date(text)
            if ddate:
                updates["delivery_date"] = ddate

        # special_instructions - uniquement si NULL
        if row["special_instructions"] is None and text:
            instr = extract_special_instructions(text)
            if instr:
                updates["special_instructions"] = instr

        # warnings - uniquement si NULL
        if row["warnings"] is None and text:
            warn = extract_warnings(text)
            if warn:
                updates["warnings"] = warn

        # customer_reference - backfill si NULL et designation contient une ref
        if not row["customer_reference"] and text:
            ref = _extract_customer_reference(text)
            if ref:
                updates["customer_reference"] = ref

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [line_id]
            conn.execute(f"UPDATE file2edi_order_lines SET {set_clause} WHERE line_id = ?", values)
            updated += 1
            print(f"  ✓  {line_id[:20]}... → {list(updates.keys())}")

    conn.commit()
    conn.close()

    print(f"\n  ✓ Backfill terminé - {updated}/{len(rows)} lignes mises à jour")

    # Stats après backfill
    conn2 = sqlite3.connect(db_path)
    for col in ["customer_reference", "payment_terms", "delivery_date", "special_instructions", "warnings"]:
        n = conn2.execute(f"SELECT COUNT(*) FROM file2edi_order_lines WHERE {col} IS NOT NULL AND {col} != ''").fetchone()[0]
        total = conn2.execute("SELECT COUNT(*) FROM file2edi_order_lines").fetchone()[0]
        pct = round(n / total * 100) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"    {col:<25}  [{bar}]  {pct:3d}%  ({n}/{total})")
    conn2.close()


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    if not os.path.exists(db):
        print(f"❌ Base introuvable: {db}")
        sys.exit(1)
    backfill(db)
