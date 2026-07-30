#!/usr/bin/env python3
"""Analyze extraction quality for all line item columns."""
import sqlite3
import json

conn = sqlite3.connect("data/file2edi.db")
conn.row_factory = sqlite3.Row

print("=" * 100)
print("QUALITE EXTRACTION — TOUTES LES COLONNES LIGNES DE COMMANDE")
print("=" * 100)

# Stats sur 533 lignes totales
all_stats = conn.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN bosch_article IS NOT NULL AND bosch_article<>'' THEN 1 ELSE 0 END) as has_article,
        SUM(CASE WHEN quantity IS NOT NULL AND CAST(quantity AS FLOAT)>0 THEN 1 ELSE 0 END) as has_qty,
        SUM(CASE WHEN unit_price IS NOT NULL AND CAST(unit_price AS FLOAT)>0 THEN 1 ELSE 0 END) as has_price,
        SUM(CASE WHEN amount IS NOT NULL AND CAST(amount AS FLOAT)>0 THEN 1 ELSE 0 END) as has_amount,
        SUM(CASE WHEN designation IS NOT NULL AND designation<>'' THEN 1 ELSE 0 END) as has_desc,
        SUM(CASE WHEN customer_reference IS NOT NULL AND customer_reference<>'' THEN 1 ELSE 0 END) as has_ref,
        ROUND(AVG(CASE WHEN confidence IS NOT NULL THEN CAST(confidence AS FLOAT) ELSE NULL END), 3) as avg_confidence
    FROM file2edi_order_lines
""").fetchone()

total = all_stats["total"] or 1
has_article = all_stats["has_article"] or 0
has_qty = all_stats["has_qty"] or 0
has_price = all_stats["has_price"] or 0
has_amount = all_stats["has_amount"] or 0
has_desc = all_stats["has_desc"] or 0
has_ref = all_stats["has_ref"] or 0

print(f"\n  Total lignes en DB : {total}")
print(f"\n  Colonne              | Complétées | % | Qualité")
print(f"  " + "-" * 65)
print(f"  Article Bosch        | {has_article:10} | {100*has_article//total:3}% | {'✓ Bon' if has_article/total > 0.95 else '⚠ À améliorer' if has_article/total > 0.80 else '❌ Mauvais'}")
print(f"  Quantité             | {has_qty:10} | {100*has_qty//total:3}% | {'✓ Bon' if has_qty/total > 0.95 else '⚠ À améliorer' if has_qty/total > 0.80 else '❌ Mauvais'}")
print(f"  Prix unitaire        | {has_price:10} | {100*has_price//total:3}% | {'✓ Bon' if has_price/total > 0.95 else '⚠ À améliorer' if has_price/total > 0.80 else '❌ Mauvais'}")
print(f"  Montant ligne        | {has_amount:10} | {100*has_amount//total:3}% | {'✓ Bon' if has_amount/total > 0.95 else '⚠ À améliorer' if has_amount/total > 0.80 else '❌ Mauvais'}")
print(f"  Désignation          | {has_desc:10} | {100*has_desc//total:3}% | {'✓ Bon' if has_desc/total > 0.95 else '⚠ À améliorer' if has_desc/total > 0.80 else '❌ Mauvais'}")
print(f"  Référence client     | {has_ref:10} | {100*has_ref//total:3}% | {'✓ Bon' if has_ref/total > 0.95 else '⚠ À améliorer' if has_ref/total > 0.80 else '❌ Mauvais'}")
print(f"  Confiance moyenne    | —          | —   | {float(all_stats['avg_confidence'] or 0)*100:.0f}% " + ('✓' if float(all_stats['avg_confidence'] or 0) > 0.80 else '⚠'))

# Exemples de lignes incomplètes
print(f"\n{'='*100}")
print("EXEMPLES DE LIGNES AVEC DONNEES MANQUANTES (20 premiers)")
print("=" * 100)

bad_lines = conn.execute("""
    SELECT l.line_number, l.bosch_article, l.quantity, l.unit_price, l.amount,
           l.designation, l.customer_reference, l.confidence, l.status, o.file_name
    FROM file2edi_order_lines l
    JOIN file2edi_orders o ON o.order_id = l.order_id
    WHERE (
        l.bosch_article IS NULL OR l.bosch_article=''
        OR l.quantity IS NULL OR CAST(l.quantity AS FLOAT) <= 0
        OR l.unit_price IS NULL OR CAST(l.unit_price AS FLOAT) <= 0
        OR l.amount IS NULL OR CAST(l.amount AS FLOAT) <= 0
        OR l.designation IS NULL OR l.designation=''
    )
    ORDER BY o.created_at DESC LIMIT 20
""").fetchall()

for l in bad_lines:
    missing = []
    if not l["bosch_article"]:
        missing.append("article")
    try:
        if not l["quantity"] or float(l["quantity"]) <= 0:
            missing.append("qty")
    except:
        missing.append("qty(invalid)")
    try:
        if not l["unit_price"] or float(l["unit_price"]) <= 0:
            missing.append("prix")
    except:
        missing.append("prix(invalid)")
    try:
        if not l["amount"] or float(l["amount"]) <= 0:
            missing.append("montant")
    except:
        missing.append("montant(invalid)")
    if not l["designation"]:
        missing.append("desc")
    
    fname = (l["file_name"] or "")[:40]
    print(f"  L{l['line_number']:02d} | {l['bosch_article'] or '(vide)':12} | {missing} | {fname}")

# Lignes par statut
print(f"\n{'='*100}")
print("REPARTITION PAR STATUT DE VALIDATION")
print("=" * 100)

status_stats = conn.execute("""
    SELECT status, COUNT(*) as count, ROUND(AVG(CAST(confidence AS FLOAT)), 3) as avg_conf
    FROM file2edi_order_lines
    GROUP BY status
    ORDER BY count DESC
""").fetchall()

for s in status_stats:
    print(f"  {str(s['status'] or '?'):20} | {s['count']:3} lignes | conf={float(s['avg_conf'] or 0)*100:5.0f}%")

# Lignes sans montant alors qu'elles ont qty et prix
print(f"\n{'='*100}")
print("ANOMALIES DETECTEES")
print("=" * 100)

# Qty et prix OK mais montant manquant/=0
missing_amount = conn.execute("""
    SELECT COUNT(*) as cnt
    FROM file2edi_order_lines
    WHERE quantity IS NOT NULL AND CAST(quantity AS FLOAT) > 0
      AND unit_price IS NOT NULL AND CAST(unit_price AS FLOAT) > 0
      AND (amount IS NULL OR CAST(amount AS FLOAT) <= 0)
""").fetchone()

# Qty manquant mais prix et montant OK
missing_qty_calc = conn.execute("""
    SELECT COUNT(*) as cnt
    FROM file2edi_order_lines
    WHERE (quantity IS NULL OR CAST(quantity AS FLOAT) <= 0)
      AND unit_price IS NOT NULL AND CAST(unit_price AS FLOAT) > 0
      AND amount IS NOT NULL AND CAST(amount AS FLOAT) > 0
""").fetchone()

print(f"  Qty+Prix OK mais montant manquant : {missing_amount['cnt']} (recalculable)")
print(f"  Qty manquant mais Prix+Montant OK  : {missing_qty_calc['cnt']} (déductible)")
print(f"  → Potentiel de récalcul : {missing_amount['cnt'] + missing_qty_calc['cnt']} lignes")

conn.close()
