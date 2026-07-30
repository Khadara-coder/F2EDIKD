#!/usr/bin/env python3
"""
Test runner complet — Phase 1 + Phase 2 validation
Tests toutes les améliorations récentes:
- Extraction quantité (variants QTÉ/QTE/QTY/QNT)
- Customer reference extraction
- Payment terms extraction
- Delivery date extraction
- Special instructions extraction
- Health API endpoint
"""
import sys
import os

# Ensure /app is on the path when running inside Docker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import requests
import time

BASE_URL = "http://localhost:8000"

PASS = "✓"
FAIL = "✗"
results = []


def check(name, cond, actual=None):
    status = PASS if cond else FAIL
    results.append((status, name, actual))
    if not cond:
        print(f"  {FAIL}  FAILED: {name}")
        if actual is not None:
            print(f"         Got: {actual}")
    else:
        print(f"  {PASS}  {name}")




try:
    from app.engines.delivery_date import extract_delivery_date, extract_delivery_urgency, extract_delivery_info
    check("delivery_date module import", True)
except Exception as e:
    check("delivery_date module import", False, str(e))

try:
    from app.engines.special_instructions import extract_special_instructions, extract_warnings
    check("special_instructions module import", True)
except Exception as e:
    check("special_instructions module import", False, str(e))

try:
    from app.line_items import _extract_customer_reference, _extract_payment_terms, extract_line_items_from_text
    check("line_items new functions import", True)
except Exception as e:
    check("line_items new functions import", False, str(e))

try:
    from app.extraction import _sanitize_order_lines, _extract_qty_from_description
    check("extraction module import", True)
except Exception as e:
    check("extraction module import", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 2. DELIVERY DATE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("2. DELIVERY DATE ENGINE")
print("="*60)

try:
    # Test date format DD/MM/YYYY
    d = extract_delivery_date("Livraison le 31/12/2026")
    check("Date format DD/MM/YYYY", d == "2026-12-31", d)

    # Test date format DD-MM-YYYY
    d = extract_delivery_date("Livraison le 15-03-2026")
    check("Date format DD-MM-YYYY", d == "2026-03-15", d)

    # Test date format DD.MM.YYYY
    d = extract_delivery_date("Date: 01.06.2026")
    check("Date format DD.MM.YYYY", d == "2026-06-01", d)

    # Test urgency URGENT
    u = extract_delivery_urgency("URGENT livraison immédiate")
    check("Urgency keyword URGENT", u == "URGENT", u)

    # Test urgency EXPRESS
    u = extract_delivery_urgency("Livraison EXPRESS souhaitée")
    check("Urgency keyword EXPRESS", u == "EXPRESS", u)

    # Test no date → None
    d = extract_delivery_date("Produit standard 5 PCE")
    check("No date → None", d is None, d)

    # Test combined info
    info = extract_delivery_info("URGENT livraison le 25/07/2026")
    check("Delivery info combined", info.get("delivery_date") == "2026-07-25" and info.get("urgency") == "URGENT", info)

except Exception as e:
    check("delivery_date tests", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 3. SPECIAL INSTRUCTIONS ENGINE
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("3. SPECIAL INSTRUCTIONS ENGINE")
print("="*60)

try:
    # Test note section
    instr = extract_special_instructions("Remarques: livrer avant 17h")
    check("Note section extraction", instr is not None and len(instr) > 0, instr)

    # Test FRAGILE handling
    instr = extract_special_instructions("Produit FRAGILE à manipuler avec soin")
    check("FRAGILE instruction detection", instr and "FRAGILE" in instr, instr)

    # Test warning detection
    w = extract_warnings("⚠️ Attention URGENT")
    check("Warning ⚠️ detection", w and "⚠️" in w, w)

    # Test warning IMPORTANT
    w = extract_warnings("IMPORTANT: vérifier adresse")
    check("Warning IMPORTANT detection", w and "IMPORTANT" in w, w)

    # Test no instructions → None
    instr = extract_special_instructions("Article 7736901359 quantite 5")
    check("No instructions → None", instr is None, instr)

except Exception as e:
    check("special_instructions tests", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 4. CUSTOMER REFERENCE & PAYMENT TERMS (from line_items.py)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("4. REFERENCE & PAYMENT TERMS")
print("="*60)

try:
    ref = _extract_customer_reference("ref client: ABC123")
    check("Customer ref 'ref client: ABC123'", ref != "", ref)

    terms = _extract_payment_terms("Conditions paiement: NET 30J")
    check("Payment terms NET 30J", terms != "", terms)

    terms = _extract_payment_terms("Paiement: COMPTANT")
    check("Payment terms COMPTANT", terms != "", terms)

    # No ref → empty
    ref = _extract_customer_reference("Article 7736901359")
    check("No reference → empty", ref == "", ref)

except Exception as e:
    check("customer_reference/payment_terms tests", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 5. QUANTITY VARIANTS (new regex patterns)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("5. QUANTITY VARIANTS EXTRACTION")
print("="*60)

try:
    d = _extract_qty_from_description("5 PIECE 25,77 128,85")
    check("Qty from PIECE", d == 5.0, d)

    d = _extract_qty_from_description("3 PCE 100,00")
    check("Qty from PCE", d == 3.0, d)

    d = _extract_qty_from_description("Pas de quantite ici")
    check("No qty → None", d is None, d)

    # Test extraction from full text with QTÉ variant
    rows = extract_line_items_from_text(
        "2PCE MEGALIS 7736902448 1549,71€/ PCE",
        {"7736902448": "MEGALIS TEST"}
    )
    if rows:
        check("Article window parser", rows[0].get("customer_reference") is not None, rows[0].get("customer_reference"))
        check("Article window has payment_terms key", "payment_terms" in rows[0], list(rows[0].keys()))

except Exception as e:
    check("quantity_variants tests", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 6. SANITIZE PIPELINE (extraction.py)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("6. EXTRACTION PIPELINE (_sanitize_order_lines)")
print("="*60)

try:
    test_lines = [
        {
            "code_article": "7736901359",
            "description": "MEGALIS CONDENSATION 28kW",
            "quantite": 2,
            "prix_unitaire_ht": 500.00,
            "montant_ligne_ht": 1000.00,
            "customer_reference": "CMD-2024-001",
            "payment_terms": "NET 30J",
        },
        {
            "code_article": "7736504816",
            "description": "KIT ENTRETIEN",
            "quantite": None,
            "prix_unitaire_ht": 275.00,
            "montant_ligne_ht": 5500.00,
        }
    ]
    
    cleaned = _sanitize_order_lines(test_lines)
    check("Sanitize returns 2 lines", len(cleaned) == 2, len(cleaned))
    check("customer_reference field present", "customer_reference" in cleaned[0], list(cleaned[0].keys()))
    check("payment_terms field present", "payment_terms" in cleaned[0], list(cleaned[0].keys()))
    check("special_instructions field present", "special_instructions" in cleaned[0], list(cleaned[0].keys()))
    check("warnings field present", "warnings" in cleaned[0], list(cleaned[0].keys()))
    check("Qty calc from amount/price", cleaned[1]["quantite"] == 20.0, cleaned[1]["quantite"])

except Exception as e:
    check("_sanitize_order_lines tests", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 7. HEALTH API ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("7. API HEALTH CHECK")
print("="*60)

try:
    r = requests.get(f"{BASE_URL}/api/health/system", timeout=5)
    check("API health returns 200", r.status_code == 200, r.status_code)
    data = r.json()
    check("api field = connected", data.get("api") == "connected", data.get("api"))
    check("database field present", "database" in data, list(data.keys()))

except requests.exceptions.ConnectionError:
    check("API health (running?)", False, "Connection refused — API not running")
except Exception as e:
    check("API health", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

total = len(results)
passed = sum(1 for r in results if r[0] == PASS)
failed = total - passed

for status, name, _ in results:
    if status == FAIL:
        print(f"  {FAIL}  {name}")

print(f"\n  {passed}/{total} tests passed", end="")
if failed > 0:
    print(f"  ({failed} FAILED)")
else:
    print("  — ALL PASS ✓")

sys.exit(0 if failed == 0 else 1)
