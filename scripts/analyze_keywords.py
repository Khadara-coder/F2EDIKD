#!/usr/bin/env python3
"""
Analyse complète des documents et des mots-clés.
Recense les patterns et keywords manquants qui pourraient améliorer l'extraction.
"""
import re
import sqlite3
from pathlib import Path
from collections import Counter
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "file2edi.db"

# Mots-clés déjà utilisés dans les moteurs
KNOWN_KEYWORDS = {
    # Anchors de livraison
    "adresse de livraison", "lieu de livraison", "livrer a", "ship to", "chantier",
    "destinataire", "delivery address", "dresse de livraison",
    
    # Anchors de facturation (negative)
    "facture a", "bill to", "adresse de facturation", "payer a",
    
    # Commande
    "commande", "order", "numero", "reference", "bon de commande",
    
    # Dates
    "date", "livraison", "expedition", "delai",
    
    # Montants
    "total", "montant", "prix", "ht", "ttc", "devise", "tva",
    
    # Articles/Lignes
    "article", "designation", "quantite", "unite", "pu",
    
    # Stop words
    "page", "facture", "plusieurs", "agence",
}

# Mots-clés à ignorer (trop génériques)
IGNORE_WORDS = {
    "de", "et", "la", "le", "les", "des", "par", "pour", "sur", "un", "une",
    "du", "a", "au", "dans", "avec", "sans", "ou", "est", "sont", "ne", "pas",
    "qui", "que", "en", "ses", "son", "sa", "ce", "tel", "fax", "email", "www",
}

def analyze_db_texts():
    """Analyser les descriptions et désignations stockées dans la DB."""
    print("\n" + "="*90)
    print("ANALYSE 1: MOTS-CLÉS DANS LES DESCRIPTIONS DE LIGNES DE COMMANDE")
    print("="*90 + "\n")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Récupérer toutes les désignations
    rows = conn.execute("""
        SELECT designation, comment, customer_reference
        FROM file2edi_order_lines
        WHERE designation IS NOT NULL OR comment IS NOT NULL
        LIMIT 500
    """).fetchall()
    
    word_freq = Counter()
    prefix_freq = Counter()  # Prefixes (mots avant "article", "qty", etc)
    
    for row in rows:
        desc = (row["designation"] or "") + " " + (row["comment"] or "")
        if not desc.strip():
            continue
        
        # Split et count
        words = re.findall(r"\b\w+\b", desc.lower())
        for word in words:
            if len(word) > 2 and word not in IGNORE_WORDS:
                word_freq[word] += 1
        
        # Chercher les patterns commençant chaque ligne
        if ":" in desc:
            parts = desc.split(":")
            if len(parts[0].strip()) < 20:
                prefix_freq[parts[0].strip().lower()] += 1
    
    print(f"Top 30 mots-clés manquants (>3 occurrences):")
    print("-" * 90)
    for word, count in word_freq.most_common(30):
        if word not in KNOWN_KEYWORDS and count > 3:
            print(f"  • {word:30} | {count:4} occurrences")
    
    print(f"\n\nPrefixes de désignations (première partie avant ':'):")
    print("-" * 90)
    for prefix, count in prefix_freq.most_common(15):
        if count > 2:
            print(f"  • {prefix:50} | {count:3}x")
    
    conn.close()

def analyze_extraction_patterns():
    """Analyser les patterns d'extraction existants."""
    print("\n" + "="*90)
    print("ANALYSE 2: PATTERNS D'EXTRACTION EXISTANTS")
    print("="*90 + "\n")
    
    extraction_py = Path(__file__).resolve().parents[1] / "app" / "extraction.py"
    content = extraction_py.read_text(encoding="utf-8")
    
    # Find all regex patterns
    patterns = re.findall(r'r"([^"]{20,})"', content)
    print("Patterns regex actuellement utilisés:")
    for i, pattern in enumerate(patterns[:15], 1):
        # Clean up pattern
        clean = pattern.replace(r"(?:", "").replace(r"\b", "").replace(r"\s+", " ").replace(r"\d", "#")
        print(f"  {i:2}. {clean[:80]}")

def analyze_ocr_anchors():
    """Analyser les anchors utilisés."""
    print("\n" + "="*90)
    print("ANALYSE 3: ANCHORS ACTUELLEMENT CONFIGURÉS")
    print("="*90 + "\n")
    
    config_yaml = Path(__file__).resolve().parents[1] / "config" / "extraction.yaml"
    content = config_yaml.read_text(encoding="utf-8")
    
    # Extract anchor blocks
    in_anchors = False
    current_section = None
    for line in content.splitlines():
        if line.startswith("anchors:"):
            in_anchors = True
            print("📍 ANCHORS (Points d'ancrage pour OCR):")
            continue
        if in_anchors and line.startswith("  ") and ":" in line:
            current_section = line.split(":")[0].strip()
            print(f"\n  [{current_section}]")
            continue
        if in_anchors and line.startswith("    - "):
            keyword = line.split("- ", 1)[1].strip()
            print(f"    • {keyword}")
        if in_anchors and line.startswith("postal"):
            break

def suggest_new_keywords():
    """Suggérer des nouveaux mots-clés à ajouter."""
    print("\n" + "="*90)
    print("ANALYSE 4: SUGGESTIONS DE NOUVEAUX MOTS-CLÉS À AJOUTER")
    print("="*90 + "\n")
    
    suggestions = {
        "Référence Client": [
            "ref client",
            "votre reference",
            "our reference",
            "client ref",
            "ref.",
            "commande client",
            "po number",
            "purchase order",
        ],
        "Conditions de Livraison": [
            "delai de livraison",
            "date livraison souhaitee",
            "urgent",
            "express",
            "standard",
            "franco",
            "conditions",
            "mode livraison",
        ],
        "Conditions de Paiement": [
            "conditions paiement",
            "payment terms",
            "delai paiement",
            "modalites",
            "net",
            "30 jours",
            "60 jours",
        ],
        "Notes / Instructions": [
            "notes",
            "remarques",
            "instructions",
            "attention",
            "important",
            "special",
            "confidentiel",
            "urgent",
        ],
        "Validations": [
            "bon pour accord",
            "bon pour execution",
            "lu et approuve",
            "signe",
            "visa",
            "approuve",
            "validé",
        ],
        "Références Internes": [
            "projet",
            "chantier",
            "devis",
            "convention",
            "marche",
            "appel d'offres",
            "avis marche",
        ],
    }
    
    for category, keywords in suggestions.items():
        print(f"🔍 {category}:")
        for kw in keywords:
            status = "✓" if kw in KNOWN_KEYWORDS else "✗"
            print(f"  {status} {kw}")
        print()

def suggest_column_extraction_patterns():
    """Suggérer des patterns pour les colonnes manquantes."""
    print("\n" + "="*90)
    print("ANALYSE 5: PATTERNS POUR COLONNES MANQUANTES")
    print("="*90 + "\n")
    
    patterns = {
        "Customer Reference": {
            "patterns": [
                r"(?:ref(?:\.|erence)?(?:\s+client)?|votre\s+ref|po\s+num)\s*:?\s*([A-Z0-9-]{3,20})",
                r"(?:commande\s+client|client\s+ref|our\s+reference)\s*:?\s*([A-Z0-9-]{3,20})",
            ],
            "examples": ["ref: ABC123", "votre reference: DEF-456", "commande client: XYZ789"],
            "current_rate": "0%",
        },
        "Delivery Date": {
            "patterns": [
                r"(?:date\s+livraison|delivery\s+date|livrer\s+le)\s*:?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
                r"(?:delai|deadline)\s*:?\s*(\d{1,2}\s+(?:jours|days|semaines|weeks))",
            ],
            "examples": ["date livraison: 15/08/2024", "délai: 5 jours"],
            "current_rate": "~5%",
        },
        "Payment Terms": {
            "patterns": [
                r"(?:conditions?\s+paiement|payment\s+terms?)\s*:?\s*(\w+(?:\s+\d+)?)",
                r"(?:net|30j|60j|90j|comptant|credit)\b",
            ],
            "examples": ["conditions paiement: Net 30j", "Comptant"],
            "current_rate": "0%",
        },
        "Special Instructions": {
            "patterns": [
                r"(?:notes|remarques|instructions|attention|important)\s*:?\s*(.{10,100}?)(?:\n|$)",
                r"⚠️|⚡|🔴|URGENT|EXPRESS",
            ],
            "examples": ["Notes: Livraison le matin", "URGENT"],
            "current_rate": "0%",
        },
    }
    
    for field, info in patterns.items():
        print(f"📊 {field} (taux d'extraction: {info['current_rate']})")
        print(f"   Patterns proposés:")
        for pat in info["patterns"]:
            print(f"     • {pat[:70]}")
        print(f"   Exemples: {', '.join(info['examples'][:2])}")
        print()

if __name__ == "__main__":
    analyze_db_texts()
    analyze_extraction_patterns()
    analyze_ocr_anchors()
    suggest_new_keywords()
    suggest_column_extraction_patterns()
    
    print("\n" + "="*90)
    print("FIN DE L'ANALYSE")
    print("="*90 + "\n")
