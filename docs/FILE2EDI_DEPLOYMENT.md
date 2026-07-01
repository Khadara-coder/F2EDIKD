# File2EDI — Build & Deploy

## Architecture (production)

```
React SPA (frontend/dist)
    ↓  served by server.py
FastAPI server.py :8000
    ├── /api/*           → src/file2edi/router.py (React contract)
    ├── /api/proxy/*     → moteur extraction local
    ├── /api/conversions → workflow revue / SFTP / email
    └── persistence      → Delta ▶ JSONL ▶ SQLite
```

## 1. Build frontend locally

```powershell
cd frontend
npm install
npm run build
```

Output: `frontend/dist/` — served automatically by `server.py` when present.

## 2. Run locally (Python unified stack)

```powershell
pip install -r requirements.txt
cd frontend && npm run build && cd ..
uvicorn server:app --host 0.0.0.0 --port 8000
```

- UI: http://localhost:8000
- API health: http://localhost:8000/api/health/system

### Dev mode (hot reload frontend)

```powershell
# Terminal 1
uvicorn server:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Frontend dev server proxies `/api` → port 8000.

## 3. Docker Compose

```powershell
docker compose -f docker-compose.file2edi.yml up --build -d
```

- UI: http://localhost:8080
- Builds React + Python in one image (`Dockerfile.file2edi`)

## 4. Databricks Apps deployment

1. Build frontend: `cd frontend && npm run build`
2. Sync project to workspace: `/Workspace/Users/rsr1dy@bosch.com/EDIFACT`
3. Deploy via `app.yaml` (command: `uvicorn server:app --port 8000`)

### Persistence tiers

| Tier | Config | Durability |
|------|--------|------------|
| 1 Delta | `DATABRICKS_WAREHOUSE_ID` + UC catalog | Production |
| 2 JSONL | `DATABRICKS_PERSIST_PATH` | Staging |
| 3 SQLite | default | Ephemeral (redeploy) |

Run `scripts/create_delta_tables.sql` once (replace `${CATALOG}` / `${SCHEMA}`).

### Required grants (Tier 1)

```sql
GRANT CREATE, USAGE ON SCHEMA bci_rbs_prod.file2edi TO `<app-service-principal>`;
```

### Required grants (Tier 2)

Workspace folder `/Users/.../EDIFACT/data/persist` → CAN_EDIT for app SP.

## 5. API endpoints (React frontend)

| Frontend call | Backend route |
|---------------|---------------|
| `getSystemHealth()` | `GET /api/health/system` |
| `getDashboardMetrics()` | `GET /api/dashboard/metrics` |
| `uploadPdf()` | `POST /api/upload` |
| `launchExtractionJob()` | `POST /api/upload/{id}/extract` |
| `getOrderReview()` | `GET /api/orders/{id}/review` |
| `generateEdifact()` | `POST /api/orders/{id}/generate-edifact` |
| `getHistory()` | `GET /api/conversions/history` |
| `getMasterData()` | `GET /api/master-data` |
| `getSettings()` | `GET /api/settings` |

Legacy endpoints (`/api/proxy/convert`, `/api/conversions/*`) remain available for backward compatibility.

## 6. Business rules

- Global confidence < 90 % → `review_required = true`
- Blocking anomaly open → generation blocked
- Generation calls `api_generate()` → `src/edifact_builder.py`
- UNB profile locked: ELM_STANDARD only
