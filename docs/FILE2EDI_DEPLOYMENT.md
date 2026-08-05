# GenieCommande - Build & Deploy

## Workflow

```text
dev  ->  staging  ->  main
 |         |          |
local     VM Azure   VM Azure
          pre-prod   prod
```

Databricks n'heberge plus l'application. La VM Azure execute l'application avec
Docker Compose et PostgreSQL. Databricks reste un fournisseur externe pour:

- Model Serving LLM, appele en HTTP par l'API;
- la source amont des masterdata, si la synchronisation CSV utilise le repo
  masterdata gere cote Databricks/GitHub.

## Local

```bash
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
git checkout dev
cp .env.example .env
docker compose -f docker-compose.file2edi.yml up --build -d
```

- UI: http://localhost:8080
- API health: http://localhost:8080/api/health/system
- PostgreSQL tourne dans le compose.

Sans Docker:

```bash
pip install -r requirements.txt -r requirements-postgres.txt
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Staging VM

```bash
cd /root/GenieCommande
git fetch origin
git checkout staging
git pull origin staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

Verification:

```bash
docker compose -f docker-compose.file2edi.yml ps
docker compose -f docker-compose.file2edi.yml logs file2edi --tail 50
curl http://127.0.0.1:8080/api/health/system
```

## Production VM

Apres merge `staging -> main`:

```bash
cd /root/GenieCommande
git fetch origin
git checkout main
git pull origin main
docker compose -f docker-compose.file2edi.yml up --build -d
```

Verification:

```bash
curl http://127.0.0.1:8080/api/health/system
curl http://127.0.0.1:8080/api/proxy/health
```

## Variables Requises

```env
PG_DATABASE_URL=postgresql+psycopg://edifact:<password>@postgres:5432/edifact
FILE2EDI_POSTGRES_STRICT=true

F2EDI_LLM_PROVIDER=databricks
F2EDI_LLM_ENABLED=1
DATABRICKS_HOST=https://<workspace>.azuredatabricks.net
DATABRICKS_MODEL_ENDPOINT=<serving-endpoint>
DATABRICKS_TOKEN=<token-service>

APP_REQUIRE_AUTH=true
APP_API_KEYS=<secret-n8n>
APP_API_ACTOR=n8n
APP_API_ROLE=adv

SFTP_ENABLED=true
SFTP_HOST=<host>
SFTP_USERNAME=<user>
SFTP_PASSWORD=<secret>
SFTP_REMOTE_DIR=<remote-dir>
```

Le fallback `DATABRICKS_CONFIG_PROFILE` est reserve au developpement local
quand aucun token n'est fourni. En VM, preferer un secret `DATABRICKS_TOKEN`.

## Sync Masterdata

Exemple de job quotidien sur la VM:

```bash
python scripts/sync_masterdata_repo.py \
  --repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
  --branch main \
  --target-dir /root/GenieCommande/data/masterdata/ \
  --notify-api-url http://127.0.0.1:8080/api/masterdata/sync \
  --notify-api-key "$APP_API_KEY"
```

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
