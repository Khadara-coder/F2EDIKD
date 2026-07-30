📊 ANALYSE COMPLÈTE DES MOTS-CLÉS MANQUANTS
═════════════════════════════════════════════════════════════════════════════════════════

🎯 RÉSUMÉ EXÉCUTIF
──────────────────
Après analyse des 533 lignes et 221 commandes en base de données, nous avons identifié
plusieurs catégories de mots-clés et patterns manquants qui pourraient améliorer de 15-25%
la qualité d'extraction.

═════════════════════════════════════════════════════════════════════════════════════════
1️⃣  MOTS-CLÉS TROUVÉS DANS LES DÉSIGNATIONS (mais pas utilisés)
═════════════════════════════════════════════════════════════════════════════════════════

Fréquence totale (top 24):
┌──────────────────┬─────────────────────────────────────────────────────────┐
│ Mot-clé          │ Occurrences │ Catégorie                                   │
├──────────────────┼──────────────────────────────────────────────────────────┤
│ PIECE            │     55x     │ ✓ Unit (déjà géré)                          │
│ QTÉ / QUANTITÉ   │     28x     │ ⚠ À améliorer: regex pour variants          │
│ DÉSIGNATION      │     27x     │ ✓ Colonne (déjà géré)                       │
│ RÉF / RÉFÉRENCE  │    25x      │ ❌ Customer reference (0% - À AJOUTER)      │
│ FOURNISSEUR      │     20x     │ ⚠ Supplier code (parcellement)              │
│ KIT              │     19x     │ ✓ Product type (aucun impact)               │
│ LIVR* (livr...)  │     18x     │ ⚠ Delivery hints (À améliorer)              │
│ NET              │     18x     │ ⚠ Price type (HT/TTC - À ajouter)           │
│ R32 / R290       │     16x     │ ✓ Refrigerant codes (aucun impact)          │
│ TÉL / TÉLÉPHONE  │     15x     │ ❌ Contact info (0% - À AJOUTER)            │
│ UNITAIRE         │     14x     │ ⚠ Prix unitaire (peut aider le parsing)     │
│ GAZ              │     14x     │ ✓ Product property (aucun impact)           │
│ RUE              │     14x     │ ⚠ Delivery hint (already in anchors)        │
└──────────────────┴──────────────────────────────────────────────────────────┘

═════════════════════════════════════════════════════════════════════════════════════════
2️⃣  COLONNES À HAUTE PRIORITÉ (0% d'extraction)
═════════════════════════════════════════════════════════════════════════════════════════

🔴 CUSTOMER REFERENCE (client_reference) - Actuellement: 0% → Cible: 15%+
──────────────────────────────────────────────────────────────────
   Patterns à ajouter:
   ├─ r"(?:ref(?:erence)?|votre\s+ref|po\s+num|order\s+ref)\s*:?\s*([A-Z0-9-]{3,20})"
   ├─ r"(?:commande\s+client|client\s+ref|our\s+reference|customer\s+ref)\s*:?\s*([A-Z0-9-]{3,20})"
   ├─ r"(?:réf|ref|réference|reference)\s+(?:client|commande)\s*:?\s*([A-Z0-9-]{3,20})"
   └─ Mots-clés d'ancrage: "réf", "ref.", "votre référence", "commande client"

   Fichiers à modifier:
   ├─ app/line_items.py: Ajouter extraction dans _extract_table_quantity_and_unit()
   ├─ app/engines/order_lines.py: Enrichissement post-extraction
   └─ config/extraction.yaml: Ajouter anchors pour customer_reference

🔴 PAYMENT TERMS (conditions_paiement) - Actuellement: 0% → Cible: 10%+
──────────────────────────────────────────────────────────────────
   Patterns à ajouter:
   ├─ r"(?:conditions?\s+paiement|payment\s+terms?)\s*:?\s*(\w+(?:\s+\d+)?)"
   ├─ r"\b(NET|30[Jj]|60[Jj]|90[Jj]|COMPTANT|CRÉDIT|VIRMENT)\b"
   ├─ r"(?:delai\s+paiement|payment\s+terms?|terms?)\s*:?\s*(\d+\s+jours)"
   └─ Valeurs standardisées: NET, 30j, 60j, 90j, COMPTANT, VIREMENT, AUTRE

🔴 DELIVERY DATE / URGENCE - Actuellement: ~5% → Cible: 15%+
──────────────────────────────────────────────────────────────────
   Patterns à ajouter:
   ├─ r"(?:date\s+livraison|delivery\s+date|livrer\s+(?:le|avant))\s*:?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"
   ├─ r"(?:délai|deadline|urgent|express)\s*:?\s*(\d+\s+(?:jours|semaines))"
   ├─ r"\b(URGENT|EXPRESS|STANDARD|NORMAL|RAPIDE|LENT)\b"
   └─ Anchors: "date livraison", "urgent", "express", "délai"

🔴 SPECIAL INSTRUCTIONS - Actuellement: 0% → Cible: 5%+
──────────────────────────────────────────────────────────────────
   Patterns à ajouter:
   ├─ r"(?:notes|remarques|instructions|attention|important)\s*:?\s*(.{10,150}?)(?:\n|$)"
   ├─ r"(?:⚠️|⚡|🔴|❗|📌)\s*(.{5,100})"
   └─ Mots-clés: "notes", "remarques", "attention", "important", "spécial"

═════════════════════════════════════════════════════════════════════════════════════════
3️⃣  COLONNES À MOYENNE PRIORITÉ (Amélioration partielle)
═════════════════════════════════════════════════════════════════════════════════════════

⚡ QUANTITÉ VARIANTS - Actuellement: 25% → Cible: 50%+
──────────────────────────────────────────────────────────
   Ajouter variants de "quantité":
   ├─ Français: "qtés", "qty", "qté", "qnt", "quantités"
   ├─ Anglais: "qty", "quantity", "qte", "qtys", "quant."
   └─ Regex amélioré: r"(?:qté|qty|quantité|qtés?|quantity|qte)\s*:?\s*(\d+)"

⚡ PRIX UNITAIRE VARIANTS - Actuellement: 90% → Cible: 95%+
──────────────────────────────────────────────────────────
   Variantes trouvées en commentaires:
   ├─ "prix unitaire", "pu", "p.u.", "prix unit.", "unit price", "prix/pce"
   └─ Regex amélioré: r"(?:prix\s+unit|pu|p\.?u\.?|unit\s+price)\s*:?\s*"

⚡ SUPPLIER CODE - Actuellement: ~10% → Cible: 20%+
──────────────────────────────────────────────────────────
   Patterns:
   ├─ r"code\s+fournisseur\s*:?\s*(\d{4,})"
   ├─ r"sup(?:plier)?\s+code\s*:?\s*([A-Z0-9-]{3,15})"
   └─ "fournisseur" + code sur même ligne

═════════════════════════════════════════════════════════════════════════════════════════
4️⃣  AMÉLIORATION DES ANCHORS OCR (config/extraction.yaml)
═════════════════════════════════════════════════════════════════════════════════════════

À AJOUTER dans la section [delivery]:
  • "destinataire" ✓ (existe comme secondary)
  • "livrer au"
  • "livraison à"
  • "site de livraison"
  • "chantier" ✓ (existe)
  • "endroit de livraison"
  • "adresse chantier"

À AJOUTER dans une nouvelle section [payment]:
  • "conditions de paiement"
  • "payment terms"
  • "modalités de paiement"
  • "délai de paiement"
  • "net"

À AJOUTER dans une nouvelle section [instructions]:
  • "notes"
  • "remarques"
  • "instructions"
  • "attention"
  • "important"

═════════════════════════════════════════════════════════════════════════════════════════
5️⃣  PLAN D'IMPLÉMENTATION (PHASED)
═════════════════════════════════════════════════════════════════════════════════════════

PHASE 1 - EXTRACTION SIMPLE (1-2 jours) - Gain: +5-10%
─────────────────────────────────────────────────────
  Priority:
  1. ✅ [DONE] Quantité = amount/price (déjà fait)
  2. 🔲 Ajouter customer_reference extraction simple
  3. 🔲 Ajouter payment_terms detection basique
  4. 🔲 Améliorer quantity variants (qté, qty, etc.)
  
  Fichiers à modifier:
  ├─ app/extraction.py: _sanitize_order_lines() (ajouter ref/terms)
  ├─ app/line_items.py: _extract_table_quantity_and_unit() 
  └─ config/extraction.yaml: Ajouter anchors

PHASE 2 - EXTRACTION AVANCÉE (2-3 jours) - Gain: +10-15%
────────────────────────────────────────────────────────
  Priority:
  1. 🔲 Delivery date extraction
  2. 🔲 LLM-based payment terms parsing
  3. 🔲 Special instructions detection
  4. 🔲 Contact info extraction (phone/email)
  
  Fichiers à créer:
  ├─ app/engines/payment_terms.py (new)
  ├─ app/engines/special_instructions.py (new)
  └─ app/engines/delivery_date.py (improvements)

PHASE 3 - QUALITY & VALIDATION (1-2 jours) - Gain: +5%
──────────────────────────────────────────────────────
  Priority:
  1. 🔲 Regex pattern testing on 500+ real PDFs
  2. 🔲 Confidence scoring for new fields
  3. 🔲 False positive detection
  4. 🔲 Database migration + backfill

═════════════════════════════════════════════════════════════════════════════════════════
6️⃣  RECOMMENDATIONS
═════════════════════════════════════════════════════════════════════════════════════════

✅ QUICK WINS (peut être implémenté demain):
  • Ajouter "réf" / "ref" / "customer_reference" à la liste d'extraction
  • Améliorer regex pour "quantité" variants (qté, qty, etc.)
  • Ajouter "NET" / "30j" / "60j" patterns pour conditions paiement

⏳ MEDIUM TERM (cette semaine):
  • Créer moteur dédié pour extraction de dates
  • Ajouter extraction de termes de paiement
  • Implémenter instructions spéciales

🎯 LONG TERM (optimization):
  • Formation LLM sur nouveaux champs
  • Validation croisée inter-champs
  • Règles métier avancées (ex: si urgent → date livraison avant demain)

═════════════════════════════════════════════════════════════════════════════════════════

Fin de l'analyse | Généré le 2024-07-30
