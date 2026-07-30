#!/usr/bin/env python3
"""Analyze recent order line item extractions from file2edi.db."""
import sqlite3
from collections import Counter

conn = sqlite3.connect("data/file2edi.db")
conn.row_factory = sqlite3.Row

print("=" * 90)
print(f"COMMANDES ET LIGNES EXTRAITES — 20 dernieres (sur 221 total)")
print("=" * 90)

orders = conn.execute("""
    SELECT o.order_id, o.file_name, o.client_name, o.customer_order_number,
           o.order_date, o.status, o.global_confidence, o.line_count,
           COUNT(l.line_id) as nb_lines_real
    FROM file2edi_orders o
    LEFT JOIN file2edi_order_lines l ON l.order_id = o.order_id
    GROUP BY o.order_id
    ORDER BY o.created_at DESC LIMIT 20
""").fetchall()

total_lines = 0
no_bosch_art = 0
zero_qty = 0
nb_orders_ok = 0
status_counter = Counter()

for o in orders:
    status = o["status"] or "?"
    status_counter[status] += 1
    fname = (o["file_name"] or "")[:55]
    client = (o["client_name"] or "?")[:25]
    po = o["customer_order_number"] or "?"
    nb = o["nb_lines_real"] or 0
    conf = o["global_confidence"] or 0
    total_lines += nb
    conf_str = f"{float(conf)*100:.0f}%" if conf else "?"

    print(f"\n  [{status:<14}] {fname}")
    print(f"  Client: {client} | PO: {po} | Date: {o['order_date'] or '?'} | {nb} lignes | conf={conf_str}")

    lines = conn.execute("""
        SELECT line_number, customer_reference, bosch_article,
               designation, quantity, unit, unit_price, confidence, status
        FROM file2edi_order_lines WHERE order_id=?
        ORDER BY line_number
    """, [o["order_id"]]).fetchall()

    order_ok = True
    for l in lines:
        mat = l["bosch_article"] or ""
        qty = l["quantity"]
        try:
            qty_val = float(qty or 0)
        except Exception:
            qty_val = 0
        lconf = l["confidence"] or 0
        try:
            lconf_str = f"{float(lconf)*100:.0f}%"
        except Exception:
            lconf_str = "?"
        issues = []
        if not mat:
            no_bosch_art += 1
            issues.append("ART MANQUANT")
            order_ok = False
        if qty_val == 0:
            zero_qty += 1
            issues.append("QTY=0")
            order_ok = False
        flag = "  <<< " + " | ".join(issues) if issues else ""
        print(
            f"    L{str(l['line_number'] or '?'):>2}  "
            f"ref={str(l['customer_reference'] or ''):14} "
            f"bosch={str(mat or '(vide)'):12} "
            f"qty={str(qty or '?'):6} {str(l['unit'] or ''):4} "
            f"conf={lconf_str:5}  {str(l['designation'] or '')[:28]}"
            f"{flag}"
        )
    if nb > 0 and order_ok:
        nb_orders_ok += 1

print()
print("=" * 90)
print("RESUME GLOBAL (221 commandes / 533 lignes total en BDD)")
print("=" * 90)
print(f"  Commandes analysées (20)  : {len(orders)}")
print(f"  Total lignes (ces 20)     : {total_lines}")
print(f"  Moy. lignes/commande      : {total_lines / max(len(orders),1):.1f}")
print(f"  Lignes sans article Bosch : {no_bosch_art}")
print(f"  Lignes avec qty=0         : {zero_qty}")
print(f"  Commandes 100% OK         : {nb_orders_ok}")
print(f"  Statuts : {dict(status_counter)}")

# Global stats on all 221 orders
print()
print("  --- Stats globales (toutes les 221 commandes) ---")
all_stats = conn.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status='Généré' THEN 1 ELSE 0 END) as genere,
        SUM(CASE WHEN status='Revue requise' THEN 1 ELSE 0 END) as revue,
        SUM(CASE WHEN status='Rejeté' THEN 1 ELSE 0 END) as rejete,
        AVG(CASE WHEN global_confidence IS NOT NULL THEN CAST(global_confidence AS FLOAT) ELSE NULL END) as avg_conf
    FROM file2edi_orders
""").fetchone()
print(f"  Total commandes  : {all_stats['total']}")
print(f"  Generees (EDIFACT): {all_stats['genere']}")
print(f"  Revue requise    : {all_stats['revue']}")
print(f"  Rejetees         : {all_stats['rejete']}")
if all_stats["avg_conf"]:
    print(f"  Confiance moyenne : {float(all_stats['avg_conf'])*100:.1f}%")

# Top anomalies
print()
print("=" * 90)
print("TOP ANOMALIES (toutes commandes)")
print("=" * 90)
anoms = conn.execute("""
    SELECT field_name, severity, COUNT(*) as cnt, SUM(CASE WHEN status='Bloquante' THEN 1 ELSE 0 END) as bloquant
    FROM file2edi_order_anomalies
    GROUP BY field_name, severity
    ORDER BY cnt DESC LIMIT 15
""").fetchall()
for a in anoms:
    print(f"  {a['cnt']:4}x  [{a['severity']:<10}] {a['field_name']:<30} (bloquant: {a['bloquant']})")

# Lignes with issues
print()
print("=" * 90)
print("LIGNES AVEC PROBLEMES (article Bosch manquant ou qty=0)")
print("=" * 90)
bad_lines = conn.execute("""
    SELECT l.line_number, l.customer_reference, l.bosch_article, l.designation,
           l.quantity, l.confidence, o.file_name, o.status
    FROM file2edi_order_lines l
    JOIN file2edi_orders o ON o.order_id = l.order_id
    WHERE (l.bosch_article IS NULL OR l.bosch_article='')
       OR (l.quantity IS NULL OR CAST(l.quantity AS FLOAT)=0)
    ORDER BY o.created_at DESC LIMIT 20
""").fetchall()
if bad_lines:
    for l in bad_lines:
        mat = l["bosch_article"] or "(vide)"
        qty = l["quantity"] or "?"
        print(f"  L{l['line_number']:>2} bosch={mat:12} qty={qty:6}  ref={str(l['customer_reference'] or ''):14}  {str(l['file_name'] or '')[:40]}")
else:
    print("  Aucune ligne avec problème détecté !")

conn.close()
