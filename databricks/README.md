# Databricks — Rôle dans l'architecture GenieCommande

## Architecture actuelle

```
VM Azure (Docker Compose)
    ├── server.py + React SPA     ← application complète (prod + staging)
    ├── PostgreSQL                ← persistance RLS
    └── moteur EDIFACT            ← génération des fichiers .tst

        ↕ REST (Bearer token)
Databricks Model Serving          ← LLM (extraction PDF → JSON)

        ↕ git clone (cron quotidien)
Databricks / GitHub               ← repo masterdata RSR1DY/masterdata.git
```

**Databricks n'héberge plus l'application.** Il fournit deux services :
1. **Model Serving** — endpoint LLM pour l'extraction intelligente des PDFs
2. **Source masterdata** — repo git utilisé pour mettre à jour les CSV de référence

---

## 1. Configuration IA (Model Serving)

### Variables d'environnement (`.env`)

```bash
DATABRICKS_HOST=https://<workspace>.azuredatabricks.net
DATABRICKS_TOKEN=dapi...
DATABRICKS_MODEL_ENDPOINT=databricks-gpt-oss-120b
```

### Interface admin

Aller dans **Paramètres → Intelligence artificielle** pour :
- Définir le host, l'endpoint du modèle, catalog/schema
- Appliquer un token PAT en mémoire
- Tester la connexion en un clic

Le client LLM (`src/llm_client.py`) appelle directement :
```
POST {DATABRICKS_HOST}/serving-endpoints/{MODEL_ENDPOINT}/invocations
Authorization: Bearer {DATABRICKS_TOKEN}
```

Aucune dépendance `mlflow` n'est requise.

---

## 2. Sync masterdata (cron quotidien)

Le script `scripts/sync_masterdata_repo.py` clone le repo `RSR1DY/masterdata.git`
et publie les CSV dans `data/masterdata/` de l'application.

### Crontab recommandé (sur la VM)

```cron
0 3 * * * /usr/bin/python3 /root/GenieCommande/scripts/sync_masterdata_repo.py \
    --repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
    --branch main \
    --target-dir /root/GenieCommande/data/masterdata/ \
    --notify-api-url http://localhost:8080/api/masterdata/sync \
    >> /root/GenieCommande/data/logs/masterdata_sync.log 2>&1
```

### Vérification après sync

```bash
curl http://localhost:8080/api/masterdata/stats
curl http://localhost:8080/api/health/system | python3 -m json.tool | grep masterdata
```

Champs attendus :
- `masterdata_sync.status = fresh`
- `masterdata_sync.sync_age_hours < 25`

---

## 3. Accès GitHub (pour la sync masterdata)

Le script requiert un accès git vers `github.boschdevcloud.com`.

Option 1 — SSH key dans l'agent :
```bash
export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_masterdata -o StrictHostKeyChecking=no"
```

Option 2 — Token HTTPS dans l'URL :
```bash
--repo-url https://<token>@github.boschdevcloud.com/RSR1DY/masterdata.git
```

---

## 4. Grants Unity Catalog (si accès SQL Warehouse utilisé)

Si `DATABRICKS_WAREHOUSE_ID` est configuré pour des requêtes SQL :

```sql
GRANT USAGE ON SCHEMA hive_metastore.file2edi TO `<service-principal>`;
GRANT SELECT ON ALL TABLES IN SCHEMA hive_metastore.file2edi TO `<service-principal>`;
```
