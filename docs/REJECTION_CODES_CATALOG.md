# Catalogue Complet des Codes Rejection

**Version:** Phase 4 (2026-09-14)  
**Généré depuis:** `src/rejection_catalog.py` + `app/engines/rejection_engine.py`  
**Mapping:** Code → Business Impact → Message FR → Message EN

---

## Index par Sévérité

### 🔴 BLOCKING (REJECT Immédiat)

| Code | Domaine | Étape | Message FR | Message EN | Impact |
|------|---------|--------|-----------|-----------|--------|
| NOT_AN_ORDER | DOCUMENT | CLASSIFICATION | "Le document n'est pas une commande" | "Document is not an order" | Rejeter file |
| CONTRACT_KEYWORD | DOCUMENT | CLASSIFICATION | "Contrat/accord détecté" | "Contract/agreement detected" | Rejeter file |
| ORDER_CHANGE | DOCUMENT | CLASSIFICATION | "Commande modifiée détectée" | "Change order detected" | Revue manuelle |
| PDF_PARSE_FAILURE | DOCUMENT | INGESTION | "Impossible d'extraire texte du PDF" | "Cannot extract text from PDF" | Retry OCR ou rejeter |
| ORDER_KEY_MISSING | ORDER | EXTRACTION | "N° de commande absent" | "Order number missing" | Rejeter + user input |
| ORDER_DATE_INVALID | ORDER | EXTRACTION | "Date de commande invalide" | "Order date invalid format" | Rejeter + manual fix |
| ARTICLE_QUANTITY_INVALID | ARTICLE | EXTRACTION | "Quantité non-entière ou ≤ 0" | "Quantity not natural integer or ≤ 0" | Rejeter ligne |
| SOLDTO_NOT_FOUND | PARTNER | MATCHING | "Client (Sold-to) absent de masterdata" | "Customer (Sold-to) not in masterdata" | Revue + add customer |
| SHIPTO_NO_STRONG_MATCH | DELIVERY | MATCHING | "Adresse livraison non trouvée" | "Delivery address not found" | Revue + LLM salvage |
| ARTICLE_NOT_FOUND | ARTICLE | MATCHING | "Article/matière absent de masterdata" | "Article/material not in masterdata" | Rejeter ligne |
| DISCONTINUED_MATERIAL | ARTICLE | BUSINESS_VALIDATION | "Article discontinué" | "Article discontinued" | Proposer remplacement |
| ROH_NONCOMMERCIAL | ARTICLE | BUSINESS_VALIDATION | "Article ROH non-commercialisable" | "Article ROH non-commercial" | Rejeter ligne |
| EDIFACT_MISSING_BGM | EDI | EDI_VALIDATION | "Header EDIFACT absent" | "EDIFACT header missing" | Escalade technique |
| EDIFACT_MISSING_DTM_137 | EDI | EDI_VALIDATION | "Date commande EDIFACT absent" | "Order date EDIFACT missing" | Escalade technique |
| EDIFACT_MISSING_NAD_BY | EDI | EDI_VALIDATION | "Acheteur EDIFACT absent" | "Buyer EDIFACT missing" | Escalade technique |
| EDIFACT_MISSING_NAD_DP | EDI | EDI_VALIDATION | "Livraison EDIFACT absent" | "Delivery EDIFACT missing" | Escalade technique |
| EDIFACT_MISSING_LIN | EDI | EDI_VALIDATION | "Aucune ligne EDIFACT" | "No EDIFACT line items" | Escalade technique |
| DUPLICATE_ALREADY_SENT | DUPLICATE | DELIVERY | "EDIFACT pour ce N° commande déjà livré SAP" | "EDIFACT for this order already sent to SAP" | Rejeter + log |
| DELIVERY_SFTP_FAILED | DELIVERY | DELIVERY | "Échec upload SFTP" | "SFTP upload failed" | Retry auto 3x puis reject |

---

### 🟡 WARNING (REVIEW Required)

| Code | Domaine | Étape | Message FR | Message EN | Action Utilisateur |
|------|---------|--------|-----------|-----------|-------------------|
| EXTRACTION_LLM_SALVAGE | DOCUMENT | EXTRACTION | "Extraction LLM fallback utilisé — revue recommandée" | "LLM extraction fallback used — manual review recommended" | Vérifier + approuver |
| RESUBMISSION_DETECTED | DUPLICATE | INGESTION | "Doublon détecté (même PDF + même N° commande)" | "Duplicate detected (same PDF + same order)" | Log + continuer (non-bloquant) |
| PRICE_MISSING | ARTICLE | EXTRACTION | "Prix unitaire absent pour cette ligne" | "Unit price missing for this line item" | Corriger ou estimer |
| AMOUNT_MISMATCH | ARTICLE | EXTRACTION | "Montant ligne incohérent (Qty × Prix ≠ Total)" | "Line amount mismatch (Qty × Price ≠ Total)" | Corriger quantité ou prix |
| NO_DELIVERY_ADDRESS | DELIVERY | EXTRACTION | "Aucune adresse livraison détectée" | "No delivery address detected" | Importer de facturation |
| SHIPTO_AMBIGUOUS_MATCH | DELIVERY | MATCHING | "Adresse livraison ambiguë (> 1 candidat)" | "Delivery address ambiguous (>1 candidate)" | Choisir dans dropdown |

---

### ℹ️ INFO (Log Only)

| Code | Domaine | Étape | Message FR | Message EN | Impact |
|------|---------|--------|-----------|-----------|--------|
| RESUBMISSION_DETECTED | DUPLICATE | INGESTION | "Même PDF resoumis" | "Same PDF resubmitted" | Log, continue |
| ORDER_PARTIAL_EXTRACTION | ORDER | EXTRACTION | "Certains champs manquants mais commande continuable" | "Some fields missing but order can proceed" | Flag revue optionnelle |
| MASTERDATA_SYNC_STALE | PARTNER | MATCHING | "Masterdata n'a pas été syncé depuis > 24h" | "Masterdata not synced for >24h" | Alert ops |

---

## Mapping Complet: Code → Tableau d'Impact Métier

### R001: NOT_AN_ORDER
```
Condition déclenchement: 
  - Pas "commande", "order", "PO", "purchase" en texte
  - OU classifier LLM ≠ "ORDERS"
  
Sévérité: BLOCKING
Domaine: DOCUMENT / Classification
Retry possible: Non (rejet définitif)

Impact métier:
  - Client reçoit email "Votre document n'est pas une commande"
  - Fichier archivé, pas EDIFACT envoyé
  - Stats: Count += 1 dans "Rejected_NOT_AN_ORDER"

Récupération:
  - Client redoit envoyer vrai commande
  - Ou admin peut forcer classification via UI (rare)

Test case:
  PDF = invoice.pdf → NOT_AN_ORDER
  PDF = quotation.pdf → NOT_AN_ORDER
  PDF = po.pdf + "COMMANDE" → OK (not rejected)
```

### R002: ORDER_KEY_MISSING
```
Condition déclenchement:
  - Extraction find_order_number() retourne None
  - OU extraction trouvaille < 2 caractères
  
Sévérité: BLOCKING
Domaine: ORDER / Extraction
Retry possible: LLM salvage (fallback)

Impact métier:
  - Impossible croiser avec PO history SAP
  - Revue manuelle : utilisateur doit saisir N° dans UI
  - Sans N° → impossible continuer
  
Récupération:
  - Utilisateur manuellement saisit N° dans UI revue
  - Relance extraction avec N° corrigé
  - Ou LLM salvage tenté si enabled

Test case:
  PDF sans numéro → ORDER_KEY_MISSING
  PDF avec numéro "ABC" → OK
  PDF avec "#123" → OK (pas < 2 chars)
```

### R003: SOLDTO_CONFIDENCE_MIN
```
Condition déclenchement:
  - Sold-to matching score < 75%
  - Score = (exact_match * 100) OR (fuzzy_match * 75) OR (vat_match * 80)
  
Sévérité: WARNING (REVIEW required)
Domaine: PARTNER / Matching
Retry possible: Utilisateur approuve + LLM validation

Impact métier:
  - Order en "Revue" dans Cockpit
  - Utilisateur voit dropdown des 3-5 clients candidats
  - Sélectionne bon client → approuve → continue
  - SLA revue: < 1h recommandé

Récupération:
  - Utilisateur choisit bon client dans dropdown
  - Approve action → score boosté à 100%
  - Continue normal flow

Cause commune:
  - Client postal code/city manquant PDF
  - Client VAT not in masterdata
  - Masterdata STALE

Test case:
  PDF confiance=45% → SOLDTO_CONFIDENCE_MIN
  PDF confiance=75% → OK (borderline)
  PDF confiance=76% → OK
  User approves 45% score → Continue OK
```

### R004: ARTICLE_NOT_FOUND
```
Condition déclenchement:
  Material resolution priority 1-4 tous échouent:
  1. EAN lookup miss
  2. Fourre-tout lookup miss
  3. Direct MATNR lookup miss
  4. Fuzzy description match < 65%
  
Sévérité: BLOCKING per ligne
Domaine: ARTICLE / Matching
Retry possible: Admin mapping + reprocess

Impact métier:
  - Ligne rejetée (article ambiguous)
  - Order incomplete si > 1 ligne reject
  - Si ALL lignes reject → full order reject
  
Récupération:
  - Admin dans UI: "Map this article"
  - Saisir MATNR correct → relance extraction
  - Ou add article to masterdata 10564_Materials.csv

Cause commune:
  - Article custom client vs SAP MATNR différent
  - Masterdata Materials.csv outdated
  - Fuzzy threshold trop strict

Test case:
  Article="MYSTERIEUX-2024" not in DB → ARTICLE_NOT_FOUND
  Article="123456" in DB → OK
  Article="Slightly off description" (65% match) → OK
  Article="Very different description" (30% match) → ARTICLE_NOT_FOUND
  
Workaround:
  - Add EAN or Fourretout mapping
  - Lower fuzzy threshold to 55% (risky)
  - Manual admin mapping via UI
```

### R005: DISCONTINUED_MATERIAL
```
Condition déclenchement:
  MATNR resolved OK, BUT MATNR in lookups/lookup_discontinued.csv
  
Sévérité: BLOCKING per ligne
Domaine: ARTICLE / Business Validation
Retry possible: YES (propose replacement)

Impact métier:
  - Ligne rejetée
  - UI shows "Article discontinued — use X instead"
  - Customer informed → order revise avec remplacement

Récupération:
  - CSV includes replacement mapping: OLD_MATNR → NEW_MATNR
  - UI auto-proposes replacement
  - User approves new article → relance
  - OU customer manually reorder avec article remplacé

Test case:
  MATNR=123 in discontinued.csv with replacement=456 → DISCONTINUED
  UI proposes 456 → user approve → relaunch with MATNR=456
```

### R006-R009: EDIFACT Errors
```
All EDIFACT validations are BLOCKING + Technical escalation

EDIFACT_MISSING_BGM: Pas message header ORDERS
  → Escalade DIK1DY, pas recoverable by user

EDIFACT_MISSING_DTM_137: Pas date commande
  → Technique issue, retry extraction

EDIFACT_MISSING_NAD_BY: Pas acheteur
  → Should not happen if SOLDTO_CONFIDENCE OK
  → Escalade technique

EDIFACT_MISSING_NAD_DP: Pas livraison
  → Should not happen if SHIPTO_CONFIDENCE OK
  → Escalade technique

EDIFACT_MISSING_LIN: Aucune ligne
  → All articles rejected
  → Fix articles first, retry

Impact: Order stuck, requires dev fix or retry
```

### R010: DUPLICATE_ALREADY_SENT
```
Condition déclenchement:
  Composite key (order_number, soldto, pdf_hash) exists in DB
  AND EDIFACT for same key already sent to SAP
  
Sévérité: BLOCKING (prevent duplicate SAP orders)
Domaine: DUPLICATE / Delivery
Retry possible: Admin can force resend if needed

Impact métier:
  - Prevent accidental duplicate SAP orders
  - Customer gets "This order already sent" message
  - Admin can override if intentional re-send

Récupération:
  - Check SAP PO history
  - If duplicate: reject user order
  - If new order (false positive): admin override

Test case:
  Upload PDF1 → order_key=123, EDIFACT sent OK
  Upload PDF1 again (duplicate) → DUPLICATE_ALREADY_SENT
  Upload PDF2 (new, same order_key?) → Requires manual check
```

### R011: DELIVERY_SFTP_FAILED
```
Condition déclenchement:
  SFTP upload fails after 3 retries:
  - Connection timeout
  - Auth failed
  - Disk full
  - Network unreachable
  
Sévérité: BLOCKING (order not sent to SAP)
Domaine: DELIVERY / Delivery
Retry possible: YES (auto retry 3x + manual retry)

Impact métier:
  - Order queued in retry bucket
  - SFTP channel monitored 24/7
  - Customer order delayed until upload succeeds

Récupération:
  - System auto-retries 3x (exponential backoff)
  - If still fail → ops alert
  - Admin can manually trigger retry once SFTP fixed

Cause common:
  - SFTP server down (maintenance)
  - Network issue (firewall)
  - Disk full on SAP SFTP

SLA: Should recover within 2-4 hours

Test case:
  SFTP_HOST unreachable → retry 3x → DELIVERY_SFTP_FAILED
  SFTP recover → manual admin trigger → OK
```

---

## Issue Taxonomy (Business Classification)

### Domains
- **DOCUMENT** - PDF parsing, classification
- **PARTNER** - Sold-to, Ship-to, customer master data
- **ORDER** - Order header extraction
- **ARTICLE** - Article resolution, line items
- **EDI** - EDIFACT format validation
- **DUPLICATE** - Duplicate detection
- **DELIVERY** - SFTP, upload, SAP integration
- **TECHNICAL** - OCR, LLM, system errors

### Stages
- **INGESTION** - PDF upload, file validation
- **EXTRACTION** - Text/number extraction from PDF
- **CLASSIFICATION** - Document type determination
- **MATCHING** - Partner/Article lookup & validation
- **BUSINESS_VALIDATION** - Masterdata status checks
- **EDI_VALIDATION** - EDIFACT format validation
- **REVIEW** - User manual approval
- **DELIVERY** - SFTP upload, SAP integration

### Blocking Decision
- **BLOCKING** - Order/line rejected automatically
- **WARNING** - Requires user review/approval
- **INFO** - Logged, order continues

### Requires User Input
- **NO** - System handles automatically
- **YES** - User must choose/approve/correct

---

## Code Aliases (Legacy → Canonical)

```
Legacy Code              → Canonical Code
PO_NUMBER_MISSING       → ORDER_KEY_MISSING
CUSTOMER_NOT_FOUND      → SOLDTO_NOT_FOUND
DELIVERY_NOT_FOUND      → SHIPTO_NO_STRONG_MATCH
MATERIAL_UNKNOWN        → ARTICLE_NOT_FOUND
MATERIAL_DISCONTINUED   → DISCONTINUED_MATERIAL
MATERIAL_NON_COMMERCIAL → ROH_NONCOMMERCIAL
EDIFACT_FORMAT_ERROR    → EDIFACT_BUILD_ERROR
NETWORK_ERROR           → DELIVERY_SFTP_FAILED
QUANTITY_INVALID        → ARTICLE_QUANTITY_INVALID
INVALID_QUANTITY        → ARTICLE_QUANTITY_INVALID
```

---

## Implementation Notes

### Adding New Rejection Rule

**File:** `app/engines/rejection_engine.py`
```python
def _check_your_new_rule(self, structured, masterdata, materials):
    """Check your custom business rule."""
    violations = []
    
    if some_condition_fails:
        violations.append({
            'code': 'YOUR_NEW_CODE',
            'message': 'User-friendly message',
            'severity': 'BLOCKING',  # or WARNING
            'details': {'context': 'helpful_info'}
        })
    
    return violations

# Register in check_rejections():
all_violations.extend(self._check_your_new_rule(...))
```

**File:** `src/rejection_catalog.py`
```python
'YOUR_NEW_CODE': RejectionEntry(
    severity='BLOCKING',
    business_status='REJECTED',
    retry_allowed=False,
    manual_review_required=True,
    message_fr='Votre message en français',
    message_en='Your message in English',
),
```

**Test:** `pytest tests/test_rejection_engine.py::test_check_your_new_rule`

---

## Monitoring & Alerts

### Dashboard Metrics
- Total PDF processed: count
- Rejection rate by code: chart
- Avg resolution time (REVIEW → APPROVED): graph
- SFTP success rate: %
- Masterdata freshness: last sync timestamp

### Alerts (Email to ops@bosch)
- DELIVERY_SFTP_FAILED × 3 retries → escalate
- EXTRACTION_LLM_SALVAGE > 20% daily → investigate
- SOLDTO_CONFIDENCE_MIN > 50% daily → update masterdata
- Masterdata sync STALE > 24h → trigger manual sync

### Audit Trail
All validations logged to `file2edi_conversion_history`:
```sql
INSERT INTO file2edi_conversion_history 
  (order_id, action, actor, timestamp, details_json)
VALUES 
  ($1, 'VALIDATION_FAIL', 'system', now(), 
   '{"rejections": [{"code": "...", "message": "..."}]}');
```

---

## FAQ: Rejection Codes

**Q: Why is my order rejected "ORDER_KEY_MISSING" if I see a number?**  
A: Number must be ≥ 2 characters AND match specific formats (8-10 digits, alphanumeric). Single digit or "1" alone rejected.

**Q: Can I override a BLOCKING rejection?**  
A: No for BLOCKING. BLOCKING must be fixed before proceeding. For WARNING, yes (user approves).

**Q: How long do rejected orders stay in the system?**  
A: 30 days in database. Archived after → moved to storage.coldbox. Check SUPPORT_GUIDE.md for archive procedures.

**Q: What if a valid article shows "DISCONTINUED_MATERIAL"?**  
A: Check `lookups/lookup_discontinued.csv` — may need update. Or use `lookups/lookup_fourretout_to_material.csv` mapping to current article.

**Q: Does DUPLICATE_DETECTED prevent order from being sent?**  
A: No, INFO only. Order sent normally. But check if intentional re-send or actual duplicate.

---

