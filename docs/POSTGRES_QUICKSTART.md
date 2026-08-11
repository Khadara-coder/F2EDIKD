# Quick Start with PostgreSQL

## Development Setup (Docker)

```bash
# 1. Start PostgreSQL + pgAdmin
docker-compose -f docker-compose-pg.yml up -d

# 2. Install dependencies
pip install -r requirements.txt -r requirements-postgres.txt

# 3. Optional: migrate historical SQLite data into PG
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql://edifact:edifact_dev_password@localhost:5432/edifact"

# 4. Set environment (required - no SQLite runtime fallback)
export PG_DATABASE_URL="postgresql+psycopg://edifact:edifact_dev_password@localhost:5432/edifact"

# 5. Start server
python server.py

# 6. Open browser
# UI: http://localhost:8000
# pgAdmin: http://localhost:5050 (admin@edifact.local / admin)
```

## Verify RBAC Works

```bash
# As ADMIN: should see all orders
curl -H "X-Forwarded-User: admin@bosch.com" -H "X-Forwarded-Role: admin" \
  http://localhost:8000/api/orders | jq '.[] | .order_id' | wc -l

# As ADV: should see only assigned + scope orders
curl -H "X-Forwarded-User: adv.pierre@bosch.com" -H "X-Forwarded-Role: adv" \
  http://localhost:8000/api/orders | jq '.[] | .order_id' | wc -l
```

## Production Deployment (Azure)

See [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md#cloud-deployment-azure) for Azure Database for PostgreSQL setup.

## Troubleshooting

**App fails at startup / store init?**
- Check: `echo $PG_DATABASE_URL` - must be set before `python server.py`
- Install drivers: `pip install -r requirements-postgres.txt`
- `get_store()` raises if `PG_DATABASE_URL` is missing (SQLite fallback disabled)

**RLS not restricting?**
- Check postgres logs: `docker-compose -f docker-compose-pg.yml logs postgres`
- Verify `auth_users` table populated: `docker exec edifact-postgres psql -U edifact edifact -c "SELECT * FROM auth_users;"`

## Architecture

```
┌─────────────────────────────────────┐
│     FastAPI server.py               │
│  (src/file2edi/router.py)           │
└──────────────┬──────────────────────┘
               │
         PG_DATABASE_URL (required)
               │
          [PostgreSQL]
        + RLS Policies
        + auth_users
        + auth_user_adv_scope
```

SQLite remains only for unit tests (`File2EdiStore` base class) and optional standalone/scripts - not for File2EDI runtime.

For details, see [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md).
