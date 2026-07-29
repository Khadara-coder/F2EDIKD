# Databricks Apps — Déploiement GenieCommande

## Architecture

```
Bosch user (Entra ID / AAD)
    ↓
Databricks App  file2edi  (port 8000)
    ├── server.py          FastAPI + React SPA
    ├── src/               Moteur EDIFACT, SFTP, RBAC
    ├── app/               Moteur extraction full-code
    └── data/masterdata/   ← /Volumes/hcdap_prod/... (monté)
```

L'app est accessible sans licence Databricks via le partage AAD group sur l'app.

---

## Variables d'environnement requises

Configurer dans les paramètres de l'app Databricks (ou via `app.yaml`) :

| Variable | Valeur |
|---|---|
| `DATABRICKS_SERVER_HOSTNAME` | `<workspace>.azuredatabricks.net` |
| `DATABRICKS_TOKEN` | PAT ou OAuth service principal |
| `DATABRICKS_WAREHOUSE_ID` | ID du SQL Warehouse |
| `EDIFACT_CATALOG` | `hive_metastore` |
| `EDIFACT_SCHEMA` | `file2edi` |
| `PG_DATABASE_URL` | URL PostgreSQL prod (ou vide pour SQLite) |
| `SFTP_HOST` / `SFTP_USERNAME` / `SFTP_PASSWORD` | Credentials SFTP ELM |
| `SFTP_REMOTE_DIR` | Répertoire remote SFTP |
| `APP_ADMIN_USERS` | `dik1dy@bosch.com,dik1dy` |
| `MOCK_MODE` | `false` en production |
| `APP_REQUIRE_AUTH` | `true` |

---

## Déploiement initial

```bash
# Dans un terminal Databricks (ou depuis la VM)
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
# Le frontend/dist est déjà versionné — pas besoin de npm build
```

Configurer `app.yaml` (déjà présent dans le repo) :

```yaml
command: ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Mise à jour production

Après merge d'une PR `staging → main` :

```bash
# Dans le terminal Databricks ou depuis la VM via SSH
cd /path/to/GenieCommande
git pull origin main
databricks apps restart file2edi
```

Vérifier le healthcheck :
```bash
curl https://file2edi-5555213114570927.7.azure.databricksapps.com/api/health/system
```

---

## Sync masterdata (job quotidien)

Créer un job Databricks qui exécute chaque nuit :

```bash
python scripts/sync_masterdata_repo.py \
    --repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
    --branch main \
    --target-dir /Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/ \
    --notify-api-url https://file2edi-5555213114570927.7.azure.databricksapps.com/api/masterdata/sync \
    --notify-api-key "$APP_API_KEY"
```

Vérification après sync :
- `/api/masterdata/stats` → `sync_age_hours` < 25
- `/api/health/system` → `masterdata_sync.status = fresh`

---

## Grants Unity Catalog requis

```sql
-- Accès schema
GRANT CREATE, USAGE ON SCHEMA hive_metastore.file2edi
  TO `<service-principal-app>`;

-- Accès Volume masterdata
GRANT READ, WRITE ON VOLUME hcdap_prod.silver_hcfrdashlog.f2edi
  TO `<service-principal-app>`;
```

---

## Dépannage

**App ne démarre pas**
```bash
databricks apps logs file2edi --follow
```

**Masterdata non chargée**
- Vérifier `/api/health/system` → champ `masterdata`
- Relancer le job de sync masterdata
- Vérifier que le Volume est accessible depuis l'app SP

**Rollback rapide**
```bash
git -C /path/to/GenieCommande checkout <commit-précédent>
databricks apps restart file2edi
```
