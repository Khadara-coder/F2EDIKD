#!/usr/bin/env python3
"""Analyze recent order line item extractions."""
import sqlite3

conn = sqlite3.connect("data/edifact_standalone.db")
conn.row_factory = sqlite3.Row

print("=" * 80)
print("COMMANDES ET LIGNES EXTRAITES (20 dernieres)")
print("=" * 80)

orders = conn.execute("""
    SELECT o.order_id, o.file_name, o.client_name, o.customer_order_number,
           o.order_date, o.status,
           COUNT(l.line_id) as nb_lines
    FROM file2edi_orders o
    LEFT JOIN file2edi_order_lines l ON l.order_id = o.order_id
    GROUP BY o.order_id
    ORDER BY o.rowid DESC LIMIT 20
""").fetchall()

total_lines = 0
no_bosch_art = 0
zero_qty = 0
nb_orders_ok = 0

for o in orders:
    status = o["status"] or "?"
    fname = (o["file_name"] or "")[:55]
    client = o["client_name"] or "?"
    po = o["customer_order_number"] or "?"
    date = o["order_date"] or "?"
    nb = o["nb_lines"] or 0
    total_lines += nb
    print()
    print(f"  [{status}] {fname}")
    print(f"  Client: {client} | PO: {po} | Date: {date} | {nb} lignes")

    lines = conn.execute("""
        SELECT line_number, customer_reference, bosch_article,
               designation, quantity, unit, unit_price, amount
        FROM file2edi_order_lines
        WHERE order_id=?
        ORDER BY line_number
    """, [o["order_id"]]).fetchall()

    order_issues = []
    for l in lines:
        mat = l["bosch_article"] or ""
        qty = l["quantity"]
        try:
            qty_val = float(qty or 0)
        except Exception:
            qty_val = 0
        issues = []
        if not mat:
            no_bosch_art += 1
            issues.append("mat manquant")
        if qty_val == 0:
            zero_qty += 1
            issues.append("qty=0")
        flag = "  <<< " + ", ".join(issues) if issues else ""
        print(
            f"    L{l['line_number'] or '?':>2}  ref={str(l['customer_reference'] or ''):12} "
            f"bosch={str(mat or ''):12} qty={str(qty or ''):6} {str(l['unit'] or ''):4} "
            f"prix={str(l['unit_price'] or ''):8}  {str(l['designation'] or '')[:25]}"
            f"{flag}"
        )
        order_issues.extend(issues)

    if nb > 0 and not order_issues:
        nb_orders_ok += 1

print()
print("=" * 80)
print("RESUME")
print("=" * 80)
print(f"  Commandes analysées     : {len(orders)}")
print(f"  Total lignes extraites  : {total_lines}")
if orders:
    print(f"  Moy. lignes/commande    : {total_lines / len(orders):.1f}")
print(f"  Commandes sans problème : {nb_orders_ok}")
print(f"  Lignes sans article Bosch: {no_bosch_art}")
print(f"  Lignes qty=0 ou manquant : {zero_qty}")

print()
print("=" * 80)
print("ANOMALIES RECENTES (20 dernieres)")
print("=" * 80)
anoms = conn.execute("""
    SELECT a.field_name, a.severity, a.message, a.status, a.created_at, o.file_name
    FROM file2edi_order_anomalies a
    LEFT JOIN file2edi_orders o ON o.order_id = a.order_id
    ORDER BY a.rowid DESC LIMIT 20
""").fetchall()

for a in anoms:
    sev = a["severity"] or "?"
    field = a["field_name"] or "?"
    msg = (a["message"] or "")[:50]
    st = a["status"] or "?"
    fname = (a["file_name"] or "")[:35]
    print(f"  [{sev:<10}] {field:<25} {msg:<50} | {st} | {fname}")

conn.close()
