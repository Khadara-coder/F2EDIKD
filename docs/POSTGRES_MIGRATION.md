# PostgreSQL Migration Guide

## Overview

This guide explains how to migrate your EDIFACT File2EDI application from SQLite to PostgreSQL with full Row-Level Security (RLS) RBAC enforcement.

## Why PostgreSQL?

1. **RBAC at DB Level**: RLS policies enforce ADV access control at the database layer, making it impossible to bypass
2. **Concurrency**: Multiple workers, multiple users, true transaction isolation
3. **Production-Ready**: Better monitoring, performance tuning, cloud deployment
4. **JSONB**: Native support for extraction_json and corrections_json as queryable data

## Prerequisites

- PostgreSQL 15+ (local via Docker or cloud-hosted)
- Python 3.11+
- Docker & Docker Compose (for local dev)

## Step-by-Step Migration

### 1. Start PostgreSQL locally (development)

```bash
# Start PG + pgAdmin in Docker
docker-compose -f docker-compose-pg.yml up -d

# Wait for health check
docker-compose -f docker-compose-pg.yml logs -f postgres
# When you see "database system is ready to accept connections", proceed
```

Access pgAdmin at `http://localhost:5050`:
- Email: `admin@edifact.local`
- Password: `admin`

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-postgres.txt
```

### 3. Run the migration script

```bash
# Make sure your SQLite file exists at data/file2edi.db
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql://edifact:edifact_dev_password@localhost:5432/edifact" \
  --masterdata data/masterdata

# Output:
# [INFO] Creating PostgreSQL schema...
# [INFO] Loading master data...
# [INFO] Migrating PDF uploads...
# [INFO] Migrated 45 uploads
# [INFO] Migrating orders...
# [INFO] Migrated 1250 orders
# ...
# [INFO] ✓ Migration completed successfully!
```

### 4. Seed authentication users (if needed)

Create an admin user and ADV users in PostgreSQL:

```bash
python -c "
from src.database_pg import PostgresDB, AuthUser, AuthUserAdvScope
import asyncio

async def seed_users():
    db = PostgresDB('postgresql://edifact:edifact_dev_password@localhost:5432/edifact')
    async with db.get_session() as session:
        # Create admin user
        admin = AuthUser(email='admin@bosch.com', role='admin')
        session.add(admin)
        
        # Create ADV users
        adv1 = AuthUser(email='adv.pierre@bosch.com', role='adv')
        adv2 = AuthUser(email='adv.marie@bosch.com', role='adv')
        session.add(adv1)
        session.add(adv2)
        
        await session.commit()
        print('✓ Users seeded')

asyncio.run(seed_users())
"
```

### 5. Update environment variables

Create or update `.env`:

```bash
# PostgreSQL connection (required for File2EDI runtime)
PG_DATABASE_URL="postgresql+psycopg://edifact:edifact_dev_password@localhost:5432/edifact"

# Logging
SQL_ECHO=false

# Optional: Cloud PostgreSQL (Azure Database for PostgreSQL)
# PG_DATABASE_URL="postgresql+psycopg://user:password@your-server.postgres.database.azure.com:5432/edifact?sslmode=require"
```

### 6. Test the connection

```bash
# Python repl
python

>>> from src.database_pg import PostgresDB
>>> import asyncio
>>> db = PostgresDB()
>>> asyncio.run(db.init_db())
# Should print: "RLS policies initialized"
```

### 7. Start the app with PostgreSQL

```bash
# Existing server.py/run_local.ps1 will auto-detect PG_DATABASE_URL
python server.py

# Logs should show:
# [INFO] Database: PostgreSQL (edifact @ localhost:5432)
# [INFO] RLS enabled for ADV users
```

### 8. Verify RBAC works

```bash
# Test 1: Admin should see all orders
curl -H "X-Forwarded-User: admin@bosch.com" \
     -H "X-Forwarded-Role: admin" \
     http://localhost:8000/api/orders

# Test 2: ADV should see only their assigned orders
curl -H "X-Forwarded-User: adv.pierre@bosch.com" \
     -H "X-Forwarded-Role: adv" \
     http://localhost:8000/api/orders
# Only returns orders where processed_by = "adv.pierre@bosch.com" 
# OR soldto matches auth_user_adv_scope
```

## RLS Policies Explained

### Policy 1: Select Access

An ADV user can SELECT an order if:
- They are ADMIN (role='admin'), OR
- They are assigned to process it (`processed_by = current_user`), OR
- The sold-to is in their master-data scope (`soldto IN auth_user_adv_scope`)

```sql
CREATE POLICY adv_orders_select ON file2edi_orders
FOR SELECT USING (
  current_setting('app.current_role')::TEXT = 'admin'
  OR processed_by = current_setting('app.current_user')::TEXT
  OR soldto IN (
    SELECT soldto FROM auth_user_adv_scope
    WHERE user_id = (SELECT id FROM auth_users WHERE email = current_setting('app.current_user')::TEXT)
  )
);
```

### Policy 2: Update Access

Same logic for UPDATE - can only modify orders they can see.

## SQLite note (tests / scripts only)

File2EDI runtime requires PostgreSQL (`PG_DATABASE_URL`). There is no automatic
SQLite fallback. The `File2EdiStore` SQLite class remains for unit tests and
local diagnostic scripts only. To migrate historical `data/file2edi.db` data,
use `migrate_to_postgres.py`.

## Troubleshooting

### "FATAL: remaining connection slots are reserved for non-replication superuser connections"

PostgreSQL ran out of connection slots. Check:
```bash
docker-compose -f docker-compose-pg.yml logs postgres
```

Increase `max_connections` in docker-compose-pg.yml:
```yaml
POSTGRES_INITDB_ARGS: "-c max_connections=500"
```

### "relation "auth_users" does not exist"

Schema wasn't created. Re-run migration:
```bash
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql://edifact:edifact_dev_password@localhost:5432/edifact"
```

### RLS policies not applying to ADV users

Check that `current_setting('app.current_user')` is set before queries:

```python
# In router.py, before calling store methods:
async with db.get_session(actor=user_email, role=user_role) as session:
    orders = await db.get_orders(session)
```

## Cloud Deployment (Azure)

For production on Azure Database for PostgreSQL:

```bash
# Create managed PostgreSQL
az postgres flexible-server create \
  --resource-group my-rg \
  --name edifact-pg \
  --admin-user edifact \
  --admin-password YourSecurePassword123! \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32

# Update PG_DATABASE_URL
export PG_DATABASE_URL="postgresql+psycopg://edifact:YourSecurePassword123!@edifact-pg.postgres.database.azure.com:5432/edifact?sslmode=require"

# Run migration
python migrate_to_postgres.py --dst "$PG_DATABASE_URL"
```

## Next Steps

1. ✅ PostgreSQL deployed + migrated
2. ✅ RBAC policies active
3. ⚠️ Monitor query performance (add indexes as needed)
4. ⚠️ Set up automated backups (Azure backup, pg_dump schedule)
5. ⚠️ Enable query logging / pgAdmin monitoring for long queries

## Support

For issues or questions, check:
- PostgreSQL logs: `docker-compose -f docker-compose-pg.yml logs postgres`
- pgAdmin UI: http://localhost:5050
- Python app logs: `python server.py` (check stderr)
