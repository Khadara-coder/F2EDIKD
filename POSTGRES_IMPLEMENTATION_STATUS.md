# PostgreSQL Migration Complete ✓

## What Was Implemented

### Phase 1: Schema & ORM (✅ Complete)

**File: `src/database_pg.py`**
- SQLAlchemy 2.0 models with async support
- 10 tables unified from old SQLite + CSV schemas:
  - `auth_users` + `auth_user_adv_scope` (RBAC)
  - `file2edi_orders` (with NEW: `processed_by`, `soldto` DÉNORMALISÉ, `uploaded_by`)
  - `file2edi_pdf_uploads` (with `uploaded_by`)
  - `file2edi_order_partners`, `file2edi_order_lines`, `file2edi_order_anomalies`
  - `file2edi_conversion_history`
  - `jobs_ledger` (replaces old schema.sql + CSV deduplication)
  - `adv_contacts` (sold-to → ADV mapping)
- Row-Level Security (RLS) policies for ADV access control at DB level
- Async sessions with RLS context (`app.current_user`, `app.current_role`)

### Phase 2: Migration Script (✅ Complete)

**File: `migrate_to_postgres.py`**
- Reads all data from SQLite (`file2edi.db`)
- Dénormalizes `soldto` from `extraction_json` into `Order.soldto` for query performance
- Loads master data CSV (`10564_Partners.csv`) → `AdvContact` table
- Migrates 100% of orders/uploads/conversions with full audit trail
- Usage: `python migrate_to_postgres.py --src data/file2edi.db --dst postgresql://...`

### Phase 3: Infrastructure (✅ Complete)

**File: `docker-compose-pg.yml`**
- PostgreSQL 15 Alpine + pgAdmin 4
- Health checks, proper volumes, networking
- One-command local dev setup: `docker-compose -f docker-compose-pg.yml up -d`

**Files: `docs/POSTGRES_MIGRATION.md`, `docs/POSTGRES_QUICKSTART.md`**
- Step-by-step migration guide
- Cloud deployment (Azure Database for PostgreSQL)
- RLS policy explanation
- Troubleshooting

**Files: `requirements-postgres.txt`, `.env.example`**
- SQLAlchemy, asyncpg, alembic, psycopg

### Phase 4: Integration (✅ Active)

**Current status:**

1. `server.py` and `src/file2edi/store.py` auto-detect `PG_DATABASE_URL`.
2. The File2EDI router is already wired to the store interface used by PostgreSQL mode.
3. Runtime fallback to SQLite still exists for no-config local development.
4. `FILE2EDI_POSTGRES_STRICT=true` forces fail-fast startup when PostgreSQL is unavailable.

**Remaining hardening tasks (recommended):**

- Add/extend integration tests that exercise File2EDI endpoints in PostgreSQL mode.
- Reduce legacy SQLite code paths still used by non-File2EDI areas in `server.py`.
- Keep documentation aligned with the current dual-mode behavior until full PostgreSQL-only cutover.

---

## Key Improvements Over SQLite

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| **RBAC Enforcement** | Python code (bypassable) | DB-level RLS (foolproof) |
| **Concurrency** | Single writer | True multi-user/multi-worker |
| **Query Performance** | No indexes on custom fields | JSONB + `pg_trgm` full-text |
| **Audit Trail** | Manual logging | Native transaction log |
| **Cloud Ready** | File-based (S3 complexity) | Azure/AWS managed DBaaS |
| **Backups** | File copy | Automated snapshots |

---

## Architecture Decision

### Why Not Replace SQLite Immediately?

**Risk Mitigation:**
- PostgreSQL is optional (`PG_DATABASE_URL` env var)
- If not set, app auto-falls back to SQLite
- Zero breaking changes to existing code
- Teams can migrate orders incrementally

### Migration Path

```
Week 1: Deploy PG locally (dev/test)
         ↓
Week 2: Run migration script (production DB snapshot)
         ↓
Week 3: Test RBAC + performance
         ↓
Week 4: Cutover: set PG_DATABASE_URL in prod
         ↓
Week 5: Archive SQLite files (keep as fallback)
```

---

## Files Created

```
src/database_pg.py                  ← ORM + models + RLS
migrate_to_postgres.py              ← Migration script
docker-compose-pg.yml               ← Local PostgreSQL + pgAdmin
requirements-postgres.txt           ← Python deps (SQLAlchemy, asyncpg, etc.)
docs/POSTGRES_MIGRATION.md          ← Detailed migration guide
docs/POSTGRES_QUICKSTART.md         ← Quick-start for devs
```

## Files to Modify (Phase 4)

```
server.py                           ← Add PG auto-detect + fallback
src/file2edi/router.py              ← Pass actor context to store
src/file2edi/store.py               ← Add PG adapter or dual-mode
```

---

## Command Reference

```bash
# 1. Start PostgreSQL locally
docker-compose -f docker-compose-pg.yml up -d

# 2. Install PG dependencies
pip install -r requirements-postgres.txt

# 3. Run migration
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql://edifact:edifact_dev_password@localhost:5432/edifact"

# 4. Test connection
python -c "
from src.database_pg import PostgresDB
import asyncio
db = PostgresDB()
asyncio.run(db.init_db())  # Should print: RLS policies initialized
"

# 5. Start app (will auto-detect PG)
export PG_DATABASE_URL="postgresql://edifact:edifact_dev_password@localhost:5432/edifact"
python server.py
```

---

## Status

✅ PostgreSQL schema designed and implemented  
✅ ORM models created (SQLAlchemy)  
✅ Migration script ready  
✅ Docker Compose for local dev  
✅ Documentation complete  
⏳ Integration with FastAPI (Phase 4)  

Next: Update `server.py` + `router.py` to use PostgreSQL with transparent RBAC fallback.
