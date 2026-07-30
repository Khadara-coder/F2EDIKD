#!/usr/bin/env python3
"""Analyze recent order line item extractions from the SQLite database."""
import sqlite3
import json
from pathlib import Path
from collections import Counter

DB_CANDIDATES = [
    "data/file2edi.db",
    "data/edifact_standalone.db",
    "data/conversions.db",
]

def get_tables(db_path):
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    return tables

def analyze_db(db_path, table):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get column names
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    print(f"\n=== Table: {table} | Colonnes: {', '.join(cols[:10])} ===\n")

    # Find line items column
    line_col = next((c for c in cols if "line" in c.lower() or "item" in c.lower()), None)
    name_col = next((c for c in cols if "file" in c.lower() or "name" in c.lower()), None)
    status_col = next((c for c in cols if "status" in c.lower() or "decision" in c.lower()), None)
    date_col = next((c for c in cols if "creat" in c.lower() or "date" in c.lower() or "time" in c.lower()), None)

    print(f"  ligne_col={line_col}, name_col={name_col}, status_col={status_col}, date_col={date_col}\n")

    order_col = "rowid"
    select_cols = [c for c in [name_col, status_col, date_col, line_col] if c]
    if not select_cols:
        print("  Pas assez de colonnes identifiées.")
        conn.close()
        return

    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM {table} ORDER BY rowid DESC LIMIT 30"
    ).fetchall()

    total_lines = []
    missing_mat = 0
    missing_qty = 0
    zero_qty = 0
    orders_with_issues = []

    print(f"{'Fichier':<45} {'Statut':<12} {'Date':<20} {'#Lignes':<8} {'Problèmes'}")
    print("-" * 110)

    for row in rows:
        d = dict(zip(select_cols, row))
        fname = str(d.get(name_col) or "?")[:44]
        status = str(d.get(status_col) or "?")[:11]
        date = str(d.get(date_col) or "?")[:19]
        items = []
        if line_col and d.get(line_col):
            try:
                items = json.loads(d[line_col])
            except Exception:
                pass

        issues = []
        for item in items:
            mat = item.get("material_number") or item.get("material") or item.get("ean") or ""
            qty = item.get("quantity") or item.get("qty") or 0
            if not mat:
                missing_mat += 1
                issues.append("mat?")
            try:
                if float(qty) == 0:
                    zero_qty += 1
                    issues.append("qty=0")
            except Exception:
                if not qty:
                    missing_qty += 1
                    issues.append("qty?")
            total_lines.append(item)

        issue_str = ", ".join(set(issues))[:20] if issues else "OK"
        print(f"{fname:<45} {status:<12} {date:<20} {len(items):<8} {issue_str}")

        if issues:
            orders_with_issues.append({"file": fname, "issues": list(set(issues)), "n_items": len(items)})

    print(f"\n{'='*110}")
    print(f"  Total commandes analysées : {len(rows)}")
    print(f"  Total lignes extraites    : {len(total_lines)}")
    if total_lines:
        print(f"  Moy. lignes/commande      : {len(total_lines)/len(rows):.1f}")
    print(f"  Numéro matière manquant   : {missing_mat}")
    print(f"  Quantité manquante        : {missing_qty}")
    print(f"  Quantité = 0              : {zero_qty}")
    print(f"  Commandes avec problèmes  : {len(orders_with_issues)}")

    if orders_with_issues:
        print("\n  Détail des problèmes:")
        for o in orders_with_issues[:10]:
            print(f"    - {o['file']} | {o['issues']} | {o['n_items']} lignes")

    conn.close()


for db_path in DB_CANDIDATES:
    if not Path(db_path).exists():
        continue
    print(f"\n{'#'*60}")
    print(f"# Base: {db_path}")
    print(f"{'#'*60}")
    tables = get_tables(db_path)
    for table in tables:
        if table.startswith("sqlite_"):
            continue
        analyze_db(db_path, table)
