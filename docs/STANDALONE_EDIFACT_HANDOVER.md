# STANDALONE EDIFACT HANDOVER

Date: 2026-06-26
Scope: Run EDIFACT generation as an independent Python stack without n8n workflow orchestration.
Project: /Workspace/Users/rsr1dy@bosch.com/EDIFACT

## 1. Executive Summary
The EDIFACT generation capability is fully implemented in `src/` and can run outside n8n.
This stack adds a FastAPI + SQLite orchestration layer on top of the existing batch engine.
Two modes are supported:
- **API/Worker mode**: FastAPI intake + SQLite job queue + worker process
- **Batch mode**: Direct PDF_INBOX scan via `src/edifact_orders_engine.py` (Windows .exe)

## 2. Project Structure
- `src/` — processing engine (pdf_extractor, matcher, pompac_rules, edifact_builder, sftp_delivery, ...)
- `src/engine_adapter.py` — bridge between worker and src.* modules
- `src/api.py` — FastAPI app (intake + status)
- `src/worker.py` — job processing loop
- `src/database.py` + `src/repository.py` — SQLite persistence
- `data/schema.sql` — SQLite schema (jobs, job_events, dedupe_ledger, adv_contacts)
- `run_api.py` / `run_worker.py` — entrypoints
- `Dockerfile` / `docker-compose.yml` — container deployment

## 3. Quick Start (API/Worker Mode)
```bash
pip install -r requirements.txt
cp .env.example .env  # fill in secrets
python -c "from src.database import initialize_database; initialize_database()"
python run_api.py       # terminal 1
python run_worker.py    # terminal 2
```

## 4. API Endpoints
- `GET  /health` — service status + config summary
- `POST /jobs` — upload PDF (multipart/form-data, field: pdf)
- `GET  /jobs` — list recent jobs
- `GET  /jobs/{job_id}` — job detail + status
- `POST /jobs/{job_id}/retry` — requeue a failed job

## 5. Docker Deployment
```bash
docker compose up -d
```
Sets up API (port 8088) + worker. Data persisted in `edifact_data` volume.

## 6. n8n Function To Standalone Mapping
- n8n form submission → `POST /jobs` API endpoint
- n8n LedgerOrderSeen Data Table → `dedupe_ledger` SQLite table (3-component key)
- n8n ADV contacts Data Table → `adv_contacts` SQLite table
- n8n SFTP nodes → `src/sftp_delivery.upload_tst()` (temp-rename + verify)
- n8n branch logic → `src/engine_adapter.process_pdf_to_edifact()` status enum

## 7. Migration Plan
### Phase 1 (Week 1): Parallel Validation
- Deploy standalone in staging
- Process same PDFs through both n8n and standalone
- Compare .tst payloads and rejection classes
- Exit: output parity, no critical regression

### Phase 2 (Week 2): Persistence Replacement
- SQLite schema initialized and duplicate behavior validated
- Replay-safe processing keys confirmed
- Exit: duplicate flow works without n8n data tables

### Phase 3 (Week 3): Notification and Delivery
- SFTP delivery confirmed in standalone
- Retry policy and dead-letter handling verified
- Exit: end-to-end flow outside n8n

### Phase 4 (Week 4): Controlled Cutover
- Freeze n8n changes
- 2-3 days supervised parallel mode
- Switch production trigger to standalone intake
- Keep n8n fallback for rollback window

## 8. UNB Profile Safety
The ELM_STANDARD profile is enforced at all layers:
- `lookups/unb_profiles.csv` — single row guard
- `config.ini` [edi] section — validated at startup
- `src/config_loader._validate_edi_profile()` — raises ForbiddenProfileError on violation
- `src/edifact_builder.build_orders_message()` — final forbidden-string scan
- `validate_project.py` — full project health check

Forbidden values (must never appear in output): `3020810000707`, `54209794400681`

## 9. Risk Matrix
1. Missing SFTP credentials — set `SFTP_ENABLED=false` until confirmed
2. Master data stale — define refresh SLA; run `validate_project.py` after each refresh
3. SQLite concurrent writes — WAL mode enabled; use PostgreSQL for multi-instance
4. PDF_INBOX UNC share — only accessible from Windows hosts; use API mode for cloud intake

## 10. Rollback
1. Stop `run_api.py` / `run_worker.py`
2. Restore n8n trigger
3. Replay queued PDFs from `data/intake/` through n8n
4. Reconcile `dedupe_ledger` vs `data/duplicate_ledger.csv`

---
Handover status: finalized for standalone Python implementation without n8n orchestration.
