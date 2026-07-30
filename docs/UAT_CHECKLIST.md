# UAT_CHECKLIST.md

## Pre-UAT Requirements

- [ ] `python validate_project.py` passes with no FAILs
- [ ] Master data files confirmed current
- [ ] SFTP credentials configured and tested
- [ ] `logs/edifact.log` writable

---

## Functional Test Cases

### TC-01: Standard ELM ORDERS
- **Input**: Valid PDF PO with a known Sold-to (ELM LEBLANC)
- **Expected**: `.tst` generated, ELM_STANDARD UNB, SFTP upload confirmed, PDF to PROCESSED
- **Pass criteria**: `UNB+UNOC:3+4399901876613+3015981600108` in first segment of `.tst`
- **Result**: [ ] PASS / [ ] FAIL

### TC-02: Multi-line Order
- **Input**: PDF with 3+ article lines
- **Expected**: `LIN+10`, `LIN+20`, `LIN+30` in `.tst`, `CNT+2:3`
- **Pass criteria**: Correct segment count in UNT
- **Result**: [ ] PASS / [ ] FAIL

### TC-03: Known Order 93711
- **Input**: PDF order 93711
- **Expected**: `.tst` filename contains `93711`, BGM+220+93711+9
- **Pass criteria**: File created and SFTP submitted
- **Result**: [ ] PASS / [ ] FAIL

### TC-04: EAN Lookup
- **Input**: PDF article with EAN-13 barcode matching lookup_ean_to_material.csv
- **Expected**: Material resolved by EAN, resolution_method=EAN in log
- **Result**: [ ] PASS / [ ] FAIL

### TC-05: Fourre-tout Correction
- **Input**: PDF article code in lookup_fourretout_to_material.csv
- **Expected**: Material resolved by FOURRETOUT mapping
- **Result**: [ ] PASS / [ ] FAIL

### TC-06: Discontinued Material Rejection
- **Input**: PDF with material in lookup_discontinued.csv
- **Expected**: PDF routed to PDF_ERROR, reason=DISCONTINUED_MATERIAL
- **Result**: [ ] PASS / [ ] FAIL

### TC-07: ROH Non-commercial Rejection
- **Input**: PDF with material in lookup_roh_noncommercial.csv
- **Expected**: PDF routed to PDF_ERROR, reason=ROH_NONCOMMERCIAL
- **Result**: [ ] PASS / [ ] FAIL

### TC-08: Unknown Material Rejection
- **Input**: PDF with article not in any lookup or master data
- **Expected**: PDF routed to PDF_ERROR, reason=UNKNOWN_MATERIAL
- **Result**: [ ] PASS / [ ] FAIL

### TC-09: Weak Ship-to Rejection
- **Input**: PDF delivery address with street-only evidence, no postal or city
- **Expected**: PDF routed to PDF_ERROR, reason=SHIPTO_WEAK_EVIDENCE
- **Result**: [ ] PASS / [ ] FAIL

### TC-10: Duplicate PDF Rejection
- **Input**: Submit same PDF twice (same hash)
- **Expected**: Second run routed to PDF_ERROR, reason=DUPLICATE_ORDER
- **Verify**: Duplicate ledger contains only one SFTP_SUBMITTED entry
- **Result**: [ ] PASS / [ ] FAIL

### TC-11: SFTP Upload Success
- **Input**: Valid PDF, SFTP credentials correct
- **Expected**: `.tst` uploaded, delivery_ledger.csv shows SFTP_SUBMITTED
- **Result**: [ ] PASS / [ ] FAIL

### TC-12: SFTP Upload Failure
- **Input**: Valid PDF, SFTP host unreachable
- **Expected**: PDF to PDF_ERROR, reason=SFTP_UPLOAD_FAILED, duplicate ledger NOT updated
- **Result**: [ ] PASS / [ ] FAIL

### TC-13: n8n Analysis Report Generation
- **Run**: `python src/edifact_orders_engine.py --analyse-n8n-only`
- **Expected**: `docs/N8N_ANALYSIS_REPORT.md` created/updated
- **Verify**: Report contains ELM_STANDARD, SFTP_SUBMITTED, partner matching rules
- **Result**: [ ] PASS / [ ] FAIL

### TC-14: Masterdata Folder Availability
- **Check**: `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/` accessible
- **Files**: `10564_Customers.csv`, `10564_Partners.csv`, `10564_Materials.csv` all present
- **Result**: [ ] PASS / [ ] FAIL

---

## Role and Audit UAT (Short-term Production)

### RC-01: Identity Resolution Endpoint
- **Input**: `GET /api/me` with header `x-forwarded-user: khadara@bosch.com`
- **Expected**: HTTP 200 with `actor=khadara@bosch.com` and a non-empty `role`
- **Result**: [ ] PASS / [ ] FAIL

### RC-02: Readonly Cannot Approve
- **Precondition**: `APP_READONLY_USERS` contains the test user
- **Input**: `POST /api/conversions/{id}/approve`
- **Expected**: HTTP 403, message `Votre profil est en lecture seule`
- **Result**: [ ] PASS / [ ] FAIL

### RC-03: Readonly Cannot Reject
- **Precondition**: `APP_READONLY_USERS` contains the test user
- **Input**: `POST /api/conversions/{id}/reject`
- **Expected**: HTTP 403
- **Result**: [ ] PASS / [ ] FAIL

### RC-04: Reviewer Can Save Review
- **Precondition**: `APP_REVIEW_USERS` contains the test user
- **Input**: `POST /api/conversions/{id}/review` with corrections payload
- **Expected**: HTTP 200 and conversion updated
- **Result**: [ ] PASS / [ ] FAIL

### RC-05: Operator Can Generate EDIFACT
- **Precondition**: `APP_REVIEW_USERS` or `APP_ADMIN_USERS` contains the test user
- **Input**: `POST /api/conversions/{id}/generate`
- **Expected**: HTTP 200, `generated=true` (if blockers resolved)
- **Result**: [ ] PASS / [ ] FAIL

### RC-06: Audit Contains Actor on Approval
- **Input**: Execute approve action, then `GET /api/conversions/{id}/audit`
- **Expected**: Event `user_approved` with `actor=<connected user>`
- **Result**: [ ] PASS / [ ] FAIL

### RC-07: Audit Contains Actor on SFTP Send
- **Input**: Execute `POST /api/conversions/{id}/send-sftp`
- **Expected**: Event `sftp_sent` or `sftp_failed` with `actor=<connected user>`
- **Result**: [ ] PASS / [ ] FAIL

### RC-08: Frontend Navigation by Role
- **Input**: Open UI as readonly, reviewer, admin
- **Expected**:
	- readonly: no access to Convertir/Revue/Paramètres actions
	- reviewer: access to Revue and Données maîtres
	- admin: access to all pages including Paramètres
- **Result**: [ ] PASS / [ ] FAIL

---

## Extraction Quality UAT (Phase 1+2+3)

### EQ-01: Quantité — Variantes keywords
- **Input**: PDF avec "QTÉ 5" ou "QTY 3" ou "QNT 2" dans les lignes
- **Expected**: `quantity` extrait correctement (pas NULL, pas 0)
- **Vérifier**: `scripts/test_random_pdfs.py` → colonne Qty ≥ 80%
- **Result**: [ ] PASS / [ ] FAIL

### EQ-02: Référence client
- **Input**: PDF avec "Réf client: ABC123" ou "PO number: XYZ"
- **Expected**: `customer_reference` = `ABC123` ou `XYZ` dans DB
- **Requête**: `SELECT customer_reference FROM file2edi_order_lines WHERE customer_reference != ''`
- **Result**: [ ] PASS / [ ] FAIL

### EQ-03: Conditions de paiement
- **Input**: PDF avec "Conditions paiement : NET 30J" ou "COMPTANT"
- **Expected**: `payment_terms` renseigné dans `file2edi_order_lines`
- **Result**: [ ] PASS / [ ] FAIL

### EQ-04: Date de livraison par ligne
- **Input**: PDF avec "Date livraison : 15/08/2026" ou "URGENT livraison le 25/07/2026"
- **Expected**: `delivery_date` = `2026-08-15` ou `2026-07-25` (format ISO)
- **Result**: [ ] PASS / [ ] FAIL

### EQ-05: Instructions spéciales
- **Input**: PDF avec "Remarques : fragile, ne pas plier"
- **Expected**: `special_instructions` non NULL dans DB
- **Result**: [ ] PASS / [ ] FAIL

### EQ-06: Avertissements (warnings)
- **Input**: PDF contenant "URGENT" ou "⚠️ ATTENTION"
- **Expected**: `warnings` = "URGENT" ou "⚠️ | ATTENTION"
- **Result**: [ ] PASS / [ ] FAIL

### EQ-07: Colonnes Phase 3 présentes en DB
- **Run**: `PRAGMA table_info(file2edi_order_lines)`
- **Expected**: colonnes `payment_terms`, `delivery_date`, `special_instructions`, `warnings` présentes
- **Result**: [ ] PASS / [ ] FAIL

### EQ-08: Migration idempotente
- **Run**: `python scripts/migrate_add_fields.py` deux fois de suite
- **Expected**: deuxième exécution → "toutes colonnes déjà présentes", aucune erreur
- **Result**: [ ] PASS / [ ] FAIL

### EQ-09: Test extraction batch 50 PDFs
- **Run**: `python scripts/test_random_pdfs.py --source "RAG Purchase Orders" --n 50`
- **Expected**: ≥ 75% docs traités, Qty ≥ 80%, Date livraison ≥ 80%
- **Résultats connus (seed=42)**: 39/50 (78%), Qty 100%, Dlv 84% ✓
- **Result**: [ ] PASS / [ ] FAIL

---

## Go/No-Go Criteria

All TC-01 through TC-12 must PASS before production cutover.
TC-13 and TC-14 are required for operational readiness.
RC-01 through RC-08 must PASS for role-based traceability readiness.
EQ-01 through EQ-09 required for Phase 1+2+3 extraction quality validation.
