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
- **Check**: `/Workspace/Users/rsr1dy@bosch.com/masterdata/` accessible
- **Files**: `10564_Customers.csv`, `10564_Partners.csv`, `10564_Materials.csv` all present
- **Result**: [ ] PASS / [ ] FAIL

---

## Go/No-Go Criteria

All TC-01 through TC-12 must PASS before production cutover.
TC-13 and TC-14 are required for operational readiness.
