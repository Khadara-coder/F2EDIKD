# PROJECT STATUS - File2EDI (2026-09-14)

**Version complète :** Phase 4 (PostgreSQL) + Phase 5+ (RBAC migration)

---

## 📊 État Général du Projet

### ✅ Livré & Fonctionnel

| Phase | Component | Status | Details |
|-------|-----------|--------|---------|
| **Core** | Application Web | ✅ | React SPA + FastAPI, responsive UI |
| **Core** | PDF Extraction | ✅ | OCR (Tesseract) + LLM + règles métier |
| **Core** | EDIFACT Generator | ✅ | Format D.96A (`.tst`), profile ELM_STANDARD |
| **Core** | SFTP Delivery | ✅ | Upload SAP (temp+rename), duplicate ledger |
| **Core** | Masterdata Sync | ✅ | GitHub webhook, cron n8n quotidien |
| **Phase 1** | Order Lines Schema | ✅ | customer_reference, payment_terms |
| **Phase 2** | Delivery Date | ✅ | Per-line extraction + urgency detection |
| **Phase 2** | Special Instructions | ✅ | Remarks, warnings, flags |
| **Phase 3** | PostgreSQL ORM | ✅ | 10 tables unifiées, async-ready SQLAlchemy |
| **Phase 4** | PG Mandatory Runtime | ✅ | No SQLite fallback, RLS policies |
| **Phase 4** | RBAC Context Passing | ✅ | Actor/role through all endpoints |
| **Infra** | Docker Compose | ✅ | Prod stack (file2edi + postgres) |
| **Infra** | Databricks Integration | ✅ | Model Serving LLM endpoint (distant) |
| **Ops** | Tests & CI | ✅ | 371 unit tests passing |

### 🔄 En Cours

| Phase | Component | Status | Details |
|-------|-----------|--------|---------|
| **Phase 5** | RBAC Filtering | 🔄 | Decision needed: assignment/scope/combined |
| **Phase 5** | ADV User Restrictions | 🔄 | View-level filtering (prepared, awaiting decision) |
| **Phase 6** | RLS Enforcement | ⏳ | Full DB-level RBAC (queued for Phase 5 decision) |

### ❌ Non Utilisé (Intentionnel)

| Component | Status | Reason |
|-----------|--------|--------|
| Databricks App Hosting | ❌ | VM Docker choisi à la place |
| Databricks Volumes (data) | ❌ | PostgreSQL pour persistance |
| Databricks Compute | ❌ | N/A (app n'est pas sur Databricks) |
| SQLite (runtime) | ❌ | PostgreSQL mandatory, no fallback |

---

## 🏗️ Architecture Actuelle

```
VM Azure (Docker Compose)
    ├── React SPA (port 8090)
    │   ├── Cockpit (stats, orders overview)
    │   ├── Convertir (upload PDFs, auto-extract)
    │   ├── Revue (review conversions before SFTP)
    │   ├── Historique (order history, filters)
    │   ├── Données maîtres (masterdata admin)
    │   └── Paramètres (settings, AI config, RBAC)
    │
    ├── FastAPI Server (port 8000 / exposed via nginx to 8090)
    │   ├── REST API (/api/*)
    │   ├── LLM Gateway (Databricks Model Serving)
    │   ├── File2EDI Engine (PDF → EDIFACT)
    │   ├── RBAC Middleware
    │   └── Static file serving (React build)
    │
    ├── PostgreSQL 15
    │   ├── RLS policies (ADV users, admin bypass)
    │   ├── 10 unified tables
    │   └── Audit trail (file2edi_conversion_history)
    │
    └── Services
        ├── Tesseract OCR
        ├── SFTP upload (SAP delivery)
        └── Masterdata sync (GitHub webhook)

External Services (HTTP/REST):
    ├── Databricks Model Serving (LLM endpoint)
    ├── GitHub (masterdata repo)
    └── SFTP Server (SAP inbox)
```

---

## 📦 Database Schema (PostgreSQL)

### Auth Tables
- `auth_users` - User identity (email, role: admin|adv, active)
- `auth_user_adv_scope` - ADV assignment to sold-to (customer mapping)

### File2EDI Tables
- `file2edi_orders` - Order header (order_number, soldto, uploaded_by, processed_by)
- `file2edi_pdf_uploads` - Upload audit (file_hash, uploaded_by, timestamp)
- `file2edi_order_partners` - Ship-to details (ship_to, soldto per order)
- `file2edi_order_lines` - Order items (article, quantity, price, confidence)
- `file2edi_order_anomalies` - Data quality flags (anomaly_type, severity)
- `file2edi_conversion_history` - Audit trail (action, actor, timestamp)

### Reference Tables
- `jobs_ledger` - Duplicate detection (order_key: order_number + soldto + hash)
- `adv_contacts` - Master data (soldto, shipto, name)

### RLS Policies
```sql
-- Applied to file2edi_orders, file2edi_order_lines, etc.
-- ADV users: SELECT/UPDATE only where:
--   current_user = processed_by, OR
--   soldto IN (SELECT soldto FROM auth_user_adv_scope WHERE user = current_user)
-- ADMIN: no row restrictions
```

---

## 🔐 RBAC Current State

### Roles (Current 4-role model)

| Role | Access | Pages |
|------|--------|-------|
| **admin** | All operations, all data | All pages (+ Paramètres) |
| **reviewer** | Review conversions, approve/reject | Revue, Historique, Données maîtres |
| **operator** | Upload, convert files | Convertir, Cockpit |
| **readonly** | View only, no mutations | Cockpit, Historique |

### Roles (Target 2-role model)

| Role | Access | Pages |
|------|--------|-------|
| **admin** | All operations, all data | All pages |
| **adv** | Assigned orders + scope only | Convertir, Revue, Historique |

### Enforcement Layers

1. **Frontend Routes** - minRole guards on page access
2. **API Middleware** - Request auth, role check
3. **Store Filtering** - (Awaiting Phase 5 decision on strategy)
4. **Database RLS** - (Prepared, activated in Phase 6)

---

## 🚀 Deployment Workflow

```
Local (dev)
    ↓ git push bosch dev
Staging (VM Azure)
    ↓ (PR dev → staging, merge)
    ↓ git pull staging
Production (VM Azure)
    ↓ (PR staging → main, merge)
    ↓ git pull main
```

All environments use `docker-compose.file2edi.yml` + `.env`

---

## 📊 Testing & Quality

### Test Coverage
- **371 unit tests** passing (pytest)
- Extraction: PDF parsing, OCR, LLM fallback, rejection engine
- Matching: sold-to, ship-to, material resolution
- EDIFACT: format validation, UNB profile
- SFTP: upload strategy, duplicate detection
- RBAC: role enforcement, access control

### Smoke Tests
```bash
# API
python scripts/smoke_file2edi_api.py

# Browser (Playwright)
npx playwright test scripts/browser_smoke.mjs

# Random PDFs (quality)
python scripts/test_random_pdfs.py --source "RAG Purchase Orders" --n 50
```

### Quality Targets
| Metric | Target |
|--------|--------|
| bosch_article extraction | 99%+ |
| quantity extraction | 80%+ |
| unit_price extraction | 90%+ |
| amount extraction | 85%+ |
| delivery_date extraction | 84%+ |

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| [README.md](README.md) | Project overview & quick start |
| [docs/RUN_ME.md](docs/RUN_ME.md) | Quick reference (Docker, Python, deploy) |
| [docs/FILE2EDI_DEPLOYMENT.md](docs/FILE2EDI_DEPLOYMENT.md) | Full deployment guide (local, staging, prod) |
| [docs/POSTGRES_MIGRATION.md](docs/POSTGRES_MIGRATION.md) | PostgreSQL setup & migration |
| [docs/POSTGRES_IMPLEMENTATION_STATUS.md](docs/POSTGRES_IMPLEMENTATION_STATUS.md) | DB architecture & Phase 5 decision |
| [docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md) | PDF processing flowchart |
| [docs/SUPPORT_GUIDE.md](docs/SUPPORT_GUIDE.md) | Operations, monitoring, troubleshooting |
| [docs/SFTP_DELIVERY.md](docs/SFTP_DELIVERY.md) | SFTP upload strategy |
| [databricks/README.md](databricks/README.md) | Databricks role (LLM only) |

---

## 🎯 Next Steps (Priority Order)

### Phase 5: RBAC Filtering
**Decision Needed:** Choose filtering strategy
1. **Option A (assignment-based)**: ADV sees orders they uploaded/processed
2. **Option B (scope-based)**: ADV sees customers in their master-data scope
3. **Option C (combined)**: ADV sees (assigned OR in scope)

**Once decided:**
- Implement filtering in `PostgresFile2EdiStore.get_orders()`
- Test RBAC enforcement
- Enable RLS in production

### Phase 6: Full RLS Enforcement
- Activate PostgreSQL RLS policies
- All queries enforce row-level filtering
- Audit trail automatic (via triggers)

### Phase 7: Analytics
- Read-only replica for reporting
- Materialized views for dashboards

---

## ⚠️ Known Limitations & Workarounds

| Issue | Status | Workaround |
|-------|--------|-----------|
| Databricks catalog permissions | ⏳ | Service Principal needs admin grant (MANAGE on catalog/schema) |
| RBAC filtering not active | 🔄 | Manual assignment until Phase 5 decision |
| No read replicas (HA) | ⏳ | Single PostgreSQL instance (Phase 7 upgrade) |

---

## 🆘 Support

- **Primary Contact:** DIK1DY (dik1dy@bosch.com)
- **Emergency Escalation:** See [SUPPORT_GUIDE.md](docs/SUPPORT_GUIDE.md#escalade)
- **Documentation:** All docs in `/docs/` folder

---

## 📝 Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-09-14 | Phase 4+ | Documentation update for PostgreSQL + RBAC state |
| 2026-07-27 | Phase 4 | PostgreSQL mandatory runtime, RLS policies ready |
| 2026-06-15 | Phase 3 | ORM models, migration script, docker-compose-pg.yml |
| 2026-05-XX | Phase 2 | Delivery date, special instructions extraction |
| 2026-04-XX | Phase 1 | Customer reference, payment terms fields |
| 2026-01-XX | Core | Initial app, EDIFACT generator, SFTP delivery |
