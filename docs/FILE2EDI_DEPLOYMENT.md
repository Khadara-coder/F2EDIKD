# File2EDI - Build & Deployment Guide

## Architecture Actuelle

**Version:** Phase 4 (PostgreSQL mandatory) + Phase 5+ (RBAC 2-role transition)  
**Production Stack:** Docker Compose + PostgreSQL 15 + FastAPI + React SPA  
**External Services:** Databricks Model Serving (LLM), GitHub (masterdata)

```
┌─ Local (dev) ─┐      ┌─ VM Azure Staging ─┐      ┌─ VM Azure Prod ─┐
│  docker-comp. │  →   │  docker-compose.    │  →   │  docker-compose. │
│  + PostgreSQL │      │  file2edi.yml       │      │  file2edi.yml    │
│  (dev env)    │      │  (staging env)      │      │  (prod env)      │
└───────────────┘      └─────────────────────┘      └──────────────────┘
```

---

## Prerequisites

- **Docker & Docker Compose** (v2.20+)
- **PostgreSQL 15** (via Docker or cloud-hosted)
- **Python 3.11+** (for native runs)
- **Node.js 18+** (for frontend dev)

---

## ✅ Environment Variables

All environments require these core variables. Create `.env` from `.env.example`:

### Create the environment file

The repository contains one template only. The real `.env` is local to each machine and is ignored by Git.

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Fill in the values for the target environment, especially `PG_DATABASE_URL`,
`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `SFTP_*`, and `APP_ADMIN_USERS`.
Do not commit `.env` or copy production secrets into the repository.

### Database (Mandatory)
```bash
PG_DATABASE_URL=postgresql+psycopg://edifact:password@postgres:5432/edifact
FILE2EDI_POSTGRES_STRICT=true
```

### LLM (Optional - Databricks or OpenAI)
```bash
F2EDI_LLM_PROVIDER=databricks        # or: openai, ollama, custom
F2EDI_LLM_ENABLED=1
DATABRICKS_HOST=https://<workspace>.azuredatabricks.net
DATABRICKS_MODEL_ENDPOINT=databricks-gpt-oss-120b
DATABRICKS_TOKEN=dapi...
```

### SFTP Delivery (Prod only)
```bash
SFTP_ENABLED=true
SFTP_HOST=<host>
SFTP_USERNAME=<user>
SFTP_PASSWORD=<pass>          # or SFTP_PRIVATE_KEY_PATH
SFTP_REMOTE_DIR=/edi/in
```

### RBAC & Auth
```bash
APP_REQUIRE_AUTH=true
APP_ADMIN_USERS=admin@bosch.com,dik1dy@bosch.com
APP_API_KEYS=<n8n-secret>
APP_API_ACTOR=n8n
APP_API_ROLE=adv
```

### Masterdata Sync
```bash
MASTERDATA_REPO_URL=https://github.boschdevcloud.com/RSR1DY/masterdata.git
MASTERDATA_REPO_BRANCH=main
MASTERDATA_SOURCE_DIR=/app/data/masterdata
MASTERDATA_RUNTIME_DIR=/app/data/masterdata
```

---

## 🔧 Local Development

### Start PostgreSQL + pgAdmin

```bash
docker compose -f docker-compose-pg.yml up -d

# Wait for health check
sleep 5
docker compose -f docker-compose-pg.yml logs postgres | head -20
```

Access:
- PostgreSQL: `localhost:5432` (edifact / edifact_dev_password)
- pgAdmin: `http://localhost:5050` (admin@edifact.local / admin)

### Start Full Stack

```bash
# Docker (all-in-one, recommended)
docker compose -f docker-compose.file2edi.yml up --build -d

# Verify
curl http://localhost:8090/api/health/system
docker compose -f docker-compose.file2edi.yml logs file2edi --tail 20
```

### Native Python (dev only)

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-postgres.txt

# Build frontend
cd frontend
npm install
npm run build
cd ..

# Start server (requires PG_DATABASE_URL in .env)
python server.py
# UI & API: http://localhost:8000
```

### Development Database Migration

If migrating from SQLite historical data:

```bash
# Ensure PostgreSQL is running
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql+psycopg://edifact:edifact_dev_password@localhost:5432/edifact"

# Verify migration
curl http://localhost:8000/api/orders | head -20
```

---

## 🌐 Staging Deployment

### Prerequisites on Staging VM

```bash
# Clone repo once
sudo git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git /root/GenieCommande
sudo chown -R $USER:$USER /root/GenieCommande
cd /root/GenieCommande
git remote add bosch https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
```

### Deploy Latest Code

```bash
cd /root/GenieCommande
git fetch bosch
git checkout staging
git pull bosch staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

### Verification

```bash
# Health check
curl http://127.0.0.1:8090/api/health/system | jq .

# Logs
docker compose -f docker-compose.file2edi.yml logs file2edi -f --tail 50

# OCR ready
docker compose -f docker-compose.file2edi.yml exec file2edi tesseract --version

# DB connection
docker compose -f docker-compose.file2edi.yml exec file2edi python -c \
  "from src.file2edi.store import get_store; s=get_store(); print('DB OK')"

# Test API endpoint
curl -H "Authorization: Bearer test-key" \
  http://127.0.0.1:8090/api/orders | jq '.total'
```

---

## 🏭 Production Deployment

### Scheduled Procedure

1. **Code merge** (GitHub)
   - PR `staging → main`, get approval, merge
   - CI/CD validates (if configured)

2. **VM deployment** (production server)
   ```bash
   cd /root/GenieCommande
   git fetch bosch
   git checkout main
   git pull bosch main
   
   # Stop current containers (with grace period)
   docker compose -f docker-compose.file2edi.yml down
   
   # Start new version
   docker compose -f docker-compose.file2edi.yml up --build -d
   ```

3. **Health verification**
   ```bash
   sleep 30
   curl http://127.0.0.1:8090/api/health/system
   # Must see: "status":"ok", "ocr":"connected"
   
   # Check logs for errors
   docker compose -f docker-compose.file2edi.yml logs file2edi | grep ERROR
   
   # Monitor SFTP delivery
   docker compose -f docker-compose.file2edi.yml logs file2edi | grep SFTP
   ```

### Emergency Rollback

```bash
cd /root/GenieCommande

# Restore previous version
git checkout main~1  # or specific tag
docker compose -f docker-compose.file2edi.yml down
docker compose -f docker-compose.file2edi.yml up --build -d

# Notify team
```

---

## 📊 Monitoring

### Daily Checks

```bash
# Processing status
docker compose -f docker-compose.file2edi.yml logs file2edi | grep -E "PDF|EDIFACT|SFTP" | tail -20

# Data freshness
curl http://127.0.0.1:8090/api/masterdata/stats

# Recent errors
docker compose -f docker-compose.file2edi.yml logs file2edi | grep ERROR | tail -10

# DB size & health
docker compose -f docker-compose.file2edi.yml exec postgres psql -U edifact -d edifact_prod \
  -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datname='edifact_prod';"
```

### Disk Space

```bash
# Check volumes
docker system df

# Cleanup old images
docker image prune -a -f --filter "until=72h"
```

---

## 🔄 CI/CD Integration (Optional)

GitHub Actions example (`.github/workflows/deploy.yml`):

```yaml
name: Deploy to Staging

on:
  push:
    branches: [staging]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: SSH Deploy to VM
        env:
          SSH_KEY: ${{ secrets.STAGING_SSH_KEY }}
          SSH_HOST: ${{ secrets.STAGING_SSH_HOST }}
        run: |
          mkdir -p ~/.ssh
          echo "$SSH_KEY" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh -i ~/.ssh/id_ed25519 $SSH_HOST \
            "cd /root/GenieCommande && \
             git pull bosch staging && \
             docker compose -f docker-compose.file2edi.yml up --build -d"
```

---

## 🆘 Troubleshooting

### "PG_DATABASE_URL is required"
→ Set `PG_DATABASE_URL` in `.env` or container environment  
→ Connection format: `postgresql+psycopg://user:pass@host:5432/dbname`

### "Connection refused"
→ PostgreSQL may not be running  
→ `docker compose -f docker-compose-pg.yml up -d`  
→ Wait 10s for startup

### "docker: permission denied"
→ Add user to docker group: `sudo usermod -aG docker $USER`  
→ Restart docker daemon

### "Module not found" (Python)
→ Rebuild container: `docker compose -f docker-compose.file2edi.yml up --build -d`  
→ Or reinstall: `pip install -r requirements.txt -r requirements-postgres.txt`

### "SFTP connection failed"
→ Verify `SFTP_HOST`, `SFTP_USERNAME`, `SFTP_PASSWORD`  
→ Test manually: `sftp -o Port=22 user@host`  
→ Check firewall rules from VM

### "OCR not connected"
→ Check Tesseract installation: `docker compose -f docker-compose.file2edi.yml exec file2edi tesseract --version`  
→ Rebuild image if missing: `docker compose -f docker-compose.file2edi.yml build --no-cache file2edi`

---

## Reference: Docker Compose Commands

```bash
# Start
docker compose -f docker-compose.file2edi.yml up -d

# Start with rebuild
docker compose -f docker-compose.file2edi.yml up --build -d

# Stop
docker compose -f docker-compose.file2edi.yml down

# View logs (live)
docker compose -f docker-compose.file2edi.yml logs -f file2edi

# Execute command in container
docker compose -f docker-compose.file2edi.yml exec file2edi bash

# View services status
docker compose -f docker-compose.file2edi.yml ps

# Resource usage
docker compose -f docker-compose.file2edi.yml stats
```

---

## Related Documentation

- [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) - DB setup & migration
- [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md) - Operations & troubleshooting
- [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md) - PDF processing flow
- [SFTP_DELIVERY.md](SFTP_DELIVERY.md) - SFTP upload strategy
- [README.md](../README.md) - Project overview
SFTP_PASSWORD=<secret>
SFTP_REMOTE_DIR=<remote-dir>
```

Le fallback `DATABRICKS_CONFIG_PROFILE` est reserve au developpement local
quand aucun token n'est fourni. En VM, preferer un secret `DATABRICKS_TOKEN`.

## Sync Masterdata

Deux méthodes : webhook n8n (Synchroniser / cron) ou import CSV/Parquet par un admin.

Verifier ensuite:

```bash
curl http://127.0.0.1:8080/api/masterdata/stats
curl http://127.0.0.1:8080/api/health/system
```

## Persistence

| Tier | Variable | Usage |
|---|---|---|
| PostgreSQL | `PG_DATABASE_URL` | Required for File2EDI runtime (dev/staging/prod) |

Sans `PG_DATABASE_URL`, `get_store()` échoue au démarrage (pas de fallback SQLite).
`FILE2EDI_POSTGRES_STRICT=true` reste recommandé dans les compose files pour cohérence CI/ops.
