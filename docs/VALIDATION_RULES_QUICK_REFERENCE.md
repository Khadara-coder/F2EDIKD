# Résumé des Règles de Validation - Quick Reference

**Version:** Phase 4 (2026-09-14)  
**Pour:** Managers, consultants, product owners  
**Détails complets:** voir [VALIDATION_RULES_ANALYSIS.md](VALIDATION_RULES_ANALYSIS.md)

---

## 🎯 Les 10 Catégories de Validation

```
PDF Upload
   ↓
1. [CLASSIFICATION] Est-ce une commande valide?
   ├─ NOT_AN_ORDER ❌ → REJECT
   ├─ CONTRACT_KEYWORD ❌ → REJECT
   └─ ORDER_CHANGE ❌ → REJECT
   
   ↓
2. [EXTRACTION] Champs présents & valides?
   ├─ ORDER_KEY_MISSING ❌ → REJECT
   ├─ ORDER_DATE_INVALID ❌ → REJECT
   ├─ PDF_PARSE_FAILURE ⚠️ → REVIEW (retry OCR)
   └─ QUANTITY_INVALID ❌ → REJECT
   
   ↓
3. [MATCHING] Sold-to & Ship-to found?
   ├─ SOLDTO_NOT_FOUND ❌ → REJECT
   ├─ SOLDTO_CONFIDENCE < 75% ⚠️ → REVIEW
   ├─ SHIPTO_NO_STRONG_MATCH ❌ → REJECT
   └─ SHIPTO_CONFIDENCE < 80% ⚠️ → REVIEW
   
   ↓
4. [MATERIEL] Articles valides & dispo?
   ├─ ARTICLE_NOT_FOUND ❌ → REJECT
   ├─ DISCONTINUED_MATERIAL ❌ → REJECT
   ├─ ROH_NONCOMMERCIAL ❌ → REJECT
   └─ QUANTITY_INVALID ❌ → REJECT
   
   ↓
5. [EDIFACT] Format & segments obligatoires?
   ├─ UNB format invalide ❌ → REJECT
   ├─ MISSING_BGM (message header) ❌ → REJECT
   ├─ MISSING_DTM_137 (date) ❌ → REJECT
   ├─ MISSING_NAD_BY (sold-to) ❌ → REJECT
   ├─ MISSING_NAD_DP (ship-to) ❌ → REJECT
   └─ MISSING_LIN (≥1 ligne) ❌ → REJECT
   
   ↓
6. [DEDUP] Commande déjà soumise?
   └─ DUPLICATE_DETECTED → LOG (non-bloquant)
   
   ↓
7. [SFTP] Upload réussi?
   └─ DELIVERY_SFTP_FAILED ❌ → RETRY + REJECT
   
   ✅ SUCCESS → Envoyé à SAP
```

---

## 📊 Tableau des Sévérités

| Code | Catégorie | Sévérité | Utilisateur Voit | Action |
|------|-----------|----------|------------------|--------|
| NOT_AN_ORDER | Classification | 🔴 REJECT | ❌ "Pas une commande" | Rejeter + envoyer email |
| ORDER_KEY_MISSING | Extraction | 🔴 REJECT | ❌ "N° commande absent" | Revue manuelle |
| SOLDTO_CONFIDENCE_MIN | Matching | 🟡 REVIEW | ⚠️ "Client confiance faible" | Approuver ou corriger |
| ARTICLE_NOT_FOUND | Matière | 🔴 REJECT | ❌ "Article absent" | Revue + correction |
| EDIFACT_MISSING_BGM | EDIFACT | 🔴 REJECT | ❌ "Erreur format" | Technique → DIK1DY |
| DUPLICATE_DETECTED | Dédup | ℹ️ INFO | ℹ️ (log seulement) | Traiter quand même |
| DELIVERY_SFTP_FAILED | SFTP | 🔴 REJECT | ❌ "Upload échoué" | Retry auto (3x) |

---

## 🔢 Chiffres-Clés

| Métrique | Valeur | Source |
|----------|--------|--------|
| **Documents traités** (test) | 78% | 39/50 PDFs |
| **Taux rejet SOLDTO** | 35% | Prod stats |
| **Taux rejet SHIPTO** | 25% | Prod stats |
| **Taux rejet Article** | 20% | Prod stats |
| **Exactitude N° commande** | 100% | Test seed=42 |
| **Exactitude Quantité** | 100% | Test seed=42 |
| **Exactitude Prix** | 100% | Test seed=42 |
| **Exactitude Code Article** | 100% | Test seed=42 |

---

## 🎬 Flow Décision Simplifié

```
PDF Chargé
   ↓
EST COMMANDE? ──→ Non ──→ ❌ REJECT (NOT_AN_ORDER)
   ↓ Oui
CHAMPS OK? ──→ Non ──→ ❌ REJECT (ORDER_KEY_MISSING, etc)
   ↓ Oui
CLIENT TROUVÉ? ──→ Non ──→ ❌ REJECT (SOLDTO_NOT_FOUND)
   ↓ Oui
CLIENT CONFIANCE ≥ 75%? ──→ Non ──→ ⚠️ REVIEW
   ↓ Oui
ADRESSE LIVR TROUVÉE? ──→ Non ──→ ❌ REJECT (SHIPTO_NO_MATCH)
   ↓ Oui
ADRESSE CONFIANCE ≥ 80%? ──→ Non ──→ ⚠️ REVIEW
   ↓ Oui
ARTICLES VALIDES? ──→ Non ──→ ❌ REJECT (ARTICLE_NOT_FOUND, etc)
   ↓ Oui
EDIFACT OK? ──→ Non ──→ ❌ REJECT (FORMAT_ERROR)
   ↓ Oui
DOUBLON? ──→ Oui ──→ ℹ️ LOG (non-bloquant)
   ↓ Non
UPLOAD SFTP ──→ Échoué ──→ ❌ RETRY + REJECT
   ↓ OK
✅ SUCCESS → SUBMITTED
```

---

## 📈 Matrice Blocage/Revue

| Étape | Critère | Blocage | Revue | Récupération |
|-------|---------|---------|-------|--------------|
| **Classif** | Document type | ✅ | ❌ | Non |
| **Extraction** | Champs header | ✅ | ❌ | LLM fallback |
| **Matching** | Sold-to found | ✅ | ❌ | Revue + LLM |
| **Matching** | Sold-to confiance ≥75% | ❌ | ✅ | User approve |
| **Matching** | Ship-to found | ✅ | ❌ | Revue + LLM |
| **Matching** | Ship-to confiance ≥80% | ❌ | ✅ | User approve |
| **Article** | Article found | ✅ | ❌ | Non |
| **Article** | Article status | ✅ | ❌ | Non |
| **Article** | Quantité valide | ✅ | ❌ | Inférer du montant |
| **EDIFACT** | Format segments | ✅ | ❌ | Non |
| **Dédup** | Doublon detected | ❌ | ❌ | Log + continuer |
| **SFTP** | Upload réussi | ✅ | ❌ | Retry auto |

---

## 🎯 Cas d'Usage: Quand Revue Obligatoire?

### Cas 1: Client Faible Confiance
```
PDF: "Merci de nous envoyer la facture à PARIS"
Extraction: SOLDTO = "Inconnu (confiance 45%)"
Système: ⚠️ REVIEW_REQUIRED
Utilisateur: Voir dropdown "SOLDTO proposés", choisir bon client
Approuver: Continue normalement
```

### Cas 2: Adresse Livraison Ambiguë
```
PDF: "Livrer à l'atelier"
Extraction: SHIPTO = "Ambiguous (5 candidats)"
Système: ⚠️ REVIEW_REQUIRED
Utilisateur: Voir dropdown, choisir adresse correcte
Approuver: Continue
```

### Cas 3: Article Absent
```
PDF: "1 x MYSTERIEUX-2024"
Extraction: ARTICLE_NOT_FOUND
Système: ❌ REJECT
Utilisateur: Mapper article absent → article existant dans revue
Approuver: Relancer extraction
```

### Cas 4: Format EDIFACT Erreur
```
PDF: Validation OK mais EDIFACT build échoue (rare)
Système: ❌ REJECT + email à DIK1DY (tech escalation)
Utilisateur: Attendre fix code
```

---

## 💡 Recommandations

### Pour les Managers
- **Cible de traitement:** 85%+ orders auto-acceptés (pas revue)
- **Cible SLA revue:** < 1h délai utilisateur
- **Monitoring:** Dashboard [Cockpit] affiche rejet breakdown

### Pour les Opérateurs
- **Revue rapide:** 2-3 minutes par order (dropdown pre-rempli)
- **Escalade technique:** Si ❌ REJECT répeté même sévérité
  → Contacter DIK1DY + partager PDF sample
- **Quality audit:** 1x/semaine analyser PDF rejectés par type

### Pour les Developers
- **Ajouter règle:** Éditer `app/engines/rejection_engine.py` + `src/rejection_catalog.py`
- **Tester:** `pytest tests/test_rejection_engine.py -k <new_rule>`
- **Deploy:** Merger PR → Auto-apply en staging (pas restart requis)

---

## 🔗 Related Docs

- [VALIDATION_RULES_ANALYSIS.md](VALIDATION_RULES_ANALYSIS.md) - **FULL REFERENCE** (toutes les règles détaillées)
- [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md) - Flowchart complet PDF → EDIFACT
- [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md) - Troubleshooting ops
- [RUN_ME.md](RUN_ME.md) - Quick commands

---

## 📞 Questions Fréquentes

**Q: Pourquoi mon PDF est rejeté "SOLDTO_NOT_FOUND"?**  
A: Client absent de `10564_Customers.csv`. Ajouter client dans masterdata.

**Q: Peut-on modifier confiance min 75% → 60%?**  
A: Oui, éditer `config/extraction.yaml` (`confidence.soldto_min: 60`) + restart.

**Q: Un doublon est-il bloquant?**  
A: Non, INFO log seulement. Continue traitement si première occurrence EDIFACT.

**Q: Upload SFTP échoue — que faire?**  
A: Système retry auto 3x. Si encore échoue → vérifier SFTP_HOST/USER/PASS dans .env.

**Q: Ai-je le droit de modifier règles de validation?**  
A: Oui, admins uniquement. Éditer code + tester + merger PR.
