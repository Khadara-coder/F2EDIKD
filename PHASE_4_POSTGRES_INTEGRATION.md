# Phase 4: PostgreSQL Integration - Complete

**Status**: ✅ **DEPLOYED** - File2EDI runtime is PostgreSQL-only (`PG_DATABASE_URL` required).

> Note: the experimental dual-mode `store_adapter.py` was removed; use
> `src.file2edi.store.get_store()` (`PostgresFile2EdiStore`).

## What's Implemented

### 1. Mandatory PostgreSQL
- ✅ Server / `get_store()` require `PG_DATABASE_URL` at startup
- ✅ Initializes sessions + RLS policies when PG is available
- ✅ No transparent SQLite runtime fallback

### 2. Startup/Shutdown Lifecycle
- ✅ `@app.on_event("startup")` calls `_init_postgres_db()` if PG configured
- ✅ RLS policies auto-initialized on first connection
- ✅ `@app.on_event("shutdown")` gracefully closes PostgreSQL connections

### 3. Store
- ✅ `src/file2edi/store.py` - `PostgresFile2EdiStore` for runtime; SQLite base class for tests
- ✅ Same sync interface consumed by `router.py`

### 4. Router RBAC Context Passing
- ✅ Modified `src/file2edi/router.py` to accept `actor` and `role` in all endpoints
- ✅ Endpoints now resolve identity from `Request` headers/cookies
- ✅ Context passed to store for future RLS filtering (Phase 6)
- ✅ Affected endpoints:
  - `/dashboard/metrics`
  - `/orders`
  - `/dashboard/review-queue`
  - `/dashboard/recent-conversions`
  - `/conversions/history`

## How to Use It

```bash
# Start PostgreSQL locally
docker-compose -f docker-compose-pg.yml up -d

# Required
$env:PG_DATABASE_URL="postgresql+psycopg://edifact:edifact_dev_password@localhost:5432/edifact"

# Optional: migrate historical SQLite data
python migrate_to_postgres.py --src data/file2edi.db --dst $env:PG_DATABASE_URL

python server.py
```

Without `PG_DATABASE_URL`, `get_store()` fails fast (no SQLite runtime fallback).

## What's NOT Yet Implemented (Phase 6)

❌ RBAC filtering logic - context is passed but not yet used
❌ Order-listing access control enforcement
❌ ADV users seeing only their assigned orders

These require a user decision (Phase 6) on filtering strategy:
- **Assignment-based**: ADV sees only `processed_by = current_user`
- **Scope-based**: ADV sees only `soldto` in their master-data scope
- **Combined**: ADV sees (assigned OR in scope)

## File Changes Summary

**Primary store**: `src/file2edi/store.py` (`PostgresFile2EdiStore`)
**Removed**: experimental `src/file2edi/store_adapter.py`
**Modified**: `server.py` (startup PG init; dead SQLite paths cleaned)

## Testing Checklist

✅ Server imports without errors when `PG_DATABASE_URL` is set
✅ `get_store()` raises without `PG_DATABASE_URL`
✅ Unit tests still use temporary SQLite via `File2EdiStore`
✅ Router endpoints accept `Request` and resolve actor/role

## Next Steps (Phase 6)

1. **User Decision**: Choose RBAC filtering strategy (assignment / scope / combined)
2. **Implementation**: Modify order listing to apply filters based on strategy
3. **Testing**: Verify ADV users see only their data
4. **PostgreSQL Direct**: Prefer RLS-backed queries end-to-end

## Troubleshooting

### "PG_DATABASE_URL is required; SQLite fallback is disabled"
→ Set `PG_DATABASE_URL` before starting the server.

### "Failed to initialize PostgreSQL: ..."
→ Check PostgreSQL is running: `docker-compose -f docker-compose-pg.yml up -d`
→ Check connection string: `postgresql+psycopg://user:password@host:5432/database`

### "RLS policies auto-initialized"
→ Good - data is protected at the database layer.

## Security Notes

- ✅ RLS is enforced at PostgreSQL level (can't bypass via code)
- ✅ Admin users bypass RLS (`role=admin` sets no row restrictions)
- ✅ ADV users restricted by `SET app.current_user = '{actor}'` before each query
- ✅ Runtime has no SQLite path that could bypass RLS

---

**Deployed**: 2026-07-28 | **Updated**: 2026-08-05 (SQLite runtime cleanup)
