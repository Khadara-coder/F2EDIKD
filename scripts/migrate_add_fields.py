#!/usr/bin/env python3
"""
Migration Phase 3 - Ajout des nouvelles colonnes d'extraction.

Ajoute à file2edi_order_lines:
  - payment_terms       TEXT   (conditions de paiement)
  - delivery_date       TEXT   (date de livraison souhaitée par ligne)
  - special_instructions TEXT  (instructions spéciales / remarques)
  - warnings            TEXT   (avertissements détectés)

Idempotent: ne fait rien si les colonnes existent déjà.
"""
import sqlite3
import os
import sys

DB_PATH = os.environ.get("DB_PATH", "/app/data/file2edi.db")

NEW_COLUMNS = [
    ("payment_terms",        "TEXT",  None),
    ("delivery_date",        "TEXT",  None),
    ("special_instructions", "TEXT",  None),
    ("warnings",             "TEXT",  None),
]


def migrate(db_path: str):
    print(f"Migration → {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    existing = {row[1] for row in conn.execute("PRAGMA table_info(file2edi_order_lines)").fetchall()}
    print(f"  Colonnes existantes: {sorted(existing)}")

    added = []
    for col_name, col_type, col_default in NEW_COLUMNS:
        if col_name in existing:
            print(f"  ⏭  {col_name} déjà présente - skip")
            continue
        default_clause = f" DEFAULT {col_default}" if col_default is not None else ""
        sql = f"ALTER TABLE file2edi_order_lines ADD COLUMN {col_name} {col_type}{default_clause}"
        conn.execute(sql)
        added.append(col_name)
        print(f"  ✓  Colonne ajoutée: {col_name} {col_type}")

    conn.commit()

    # Verify
    final_cols = [row[1] for row in conn.execute("PRAGMA table_info(file2edi_order_lines)").fetchall()]
    print(f"\n  Colonnes finales: {final_cols}")
    conn.close()

    if added:
        print(f"\n  ✓ Migration terminée - {len(added)} colonnes ajoutées: {added}")
    else:
        print(f"\n  ✓ Aucune modification - toutes les colonnes déjà présentes")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    if not os.path.exists(db):
        print(f"❌ Base introuvable: {db}")
        sys.exit(1)
    migrate(db)
