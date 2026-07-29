# GenieCommande — Build & Deploy

## Workflow de branches

```
dev  ──PR──▶  staging  ──PR──▶  main
 │               │                │
local          VM Azure        Databricks Apps
               (ce serveur)    (production)
```

---

## 1. Développement local

### Avec Docker Compose (recommandé)

```bash
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
git checkout dev
cp .env.example .env    # renseigner les valeurs
docker compose -f docker-compose.file2edi.yml up --build -d
```

- UI : http://localhost:8080
- API health : http://localhost:8080/api/health/system
- PostgreSQL tourne dans le même compose (`edifact-postgres:5432`)
- `MOCK_MODE=true` → aucun envoi SFTP réel

Arrêter :
```bash
docker compose -f docker-compose.file2edi.yml down
```

### Sans Docker (Python natif)

```bash
pip install -r requirements.txt -r requirements-postgres.txt
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Dev hot-reload frontend

```bash
# Terminal 1
uvicorn server:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Frontend dev server proxy `/api` → :8000 — accès sur http://localhost:5173

---

## 2. Staging (VM Azure)

La VM Azure est le serveur de validation pré-prod. On y déploie la branche `staging`.

### Premier déploiement

```bash
# Sur la VM
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git /root/F2EDIDK
cd /root/F2EDIDK
git checkout staging
cp .env.example .env
# Renseigner .env avec les vraies valeurs staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

### Mise à jour staging (après merge PR dev → staging)

```bash
git -C /root/F2EDIDK fetch origin
git -C /root/F2EDIDK checkout staging
git -C /root/F2EDIDK pull origin staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

### Vérifier l'état

```bash
docker compose -f docker-compose.file2edi.yml ps
docker compose -f docker-compose.file2edi.yml logs file2edi --tail 50
```

---

## 3. Production — Databricks Apps

### Architecture

```
React SPA (frontend/dist)
    ↓  servi par server.py
FastAPI server.py :8000
    ├── /api/*           → src/file2edi/router.py
    ├── /api/proxy/*     → moteur extraction local
    ├── /api/conversions → workflow revue / SFTP / email
    └── persistence      → PostgreSQL (RLS) ▶ SQLite (fallback)
```

### Déploiement

Après merge PR `staging → main` sur GitHub :

1. Dans le workspace Databricks, ouvrir un terminal sur l'app `file2edi` :

```bash
git pull origin main
```

2. Redémarrer l'app depuis l'interface Databricks Apps (ou via CLI) :

```bash
databricks apps restart file2edi
```

3. Vérifier le healthcheck :

```bash
curl https://file2edi-5555213114570927.7.azure.databricksapps.com/api/health/system
```

### Chemins Unity Catalog requis en production

| Variable | Chemin |
|---|---|
| Masterdata source | `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/` |
| PDF storage | `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/pdf/` |
| SQLite fallback | `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/database/edifact_standalone.db` |
| Outbox | `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/outbox/` |
| Logs | `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/logs/` |

### Grants UC requis

```sql
GRANT CREATE, USAGE ON SCHEMA hive_metastore.file2edi TO `<service-principal-app>`;
```

### Sync masterdata quotidienne (job Databricks)

```bash
python scripts/sync_masterdata_repo.py \
    --repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
    --branch main \
    --target-dir /Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/ \
    --notify-api-url https://file2edi-5555213114570927.7.azure.databricksapps.com/api/masterdata/sync \
    --notify-api-key "$APP_API_KEY"
```

---

## 4. Tiers de persistance

| Tier | Variable | Durabilité |
|------|----------|------------|
| 1 — PostgreSQL + RLS | `PG_DATABASE_URL` | Production / Staging |
| 2 — SQLite | `DB_PATH` sur UC Volume | Fallback automatique si PG absent |

Si `PG_DATABASE_URL` est vide ou inaccessible, l'app bascule silencieusement sur SQLite.

---

## 5. Build frontend seul

Nécessaire uniquement si tu modifies le frontend avant de builder l'image Docker :

```bash
cd frontend
npm install
npm run build
# frontend/dist/ est versionné → commiter le résultat
```

---

## 6. Endpoints API

| Appel frontend | Route backend |
|---|---|
| `getSystemHealth()` | `GET /api/health/system` |
| `getDashboardMetrics()` | `GET /api/dashboard/metrics` |
| `uploadPdf()` | `POST /api/upload` |
| `launchExtractionJob()` | `POST /api/upload/{id}/extract` |
| `getOrderReview()` | `GET /api/orders/{id}/review` |
| `generateEdifact()` | `POST /api/orders/{id}/generate-edifact` |
| `getHistory()` | `GET /api/conversions/history` |
| `getMasterData()` | `GET /api/master-data` |
| `getSettings()` | `GET /api/settings` |

---

## 7. Règles métier

- Confiance globale < 90 % → `review_required = true`
- Anomalie bloquante ouverte → génération bloquée
- Génération appelle `api_generate()` → `src/edifact_builder.py`
- Profil UNB verrouillé : ELM_STANDARD uniquement
