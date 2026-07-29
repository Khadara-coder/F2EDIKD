# GenieCommande

Application **File2EDI** (React + FastAPI) et moteur Python de génération EDIFACT ORDERS D.96A (`.tst`) pour Bosch Thermotechnologie France.

**Dépôt :** [github.boschdevcloud.com/DIK1DY/GenieCommande](https://github.boschdevcloud.com/DIK1DY/GenieCommande)

---

## Workflow de développement

```
dev  ──PR──▶  staging  ──PR──▶  main
 │               │                │
local          VM Azure        Databricks Apps
               (ce serveur)    (production)
```

| Branche | Rôle | Déploiement |
|---------|------|-------------|
| `dev` | Développement quotidien | Local (`docker compose`) |
| `staging` | Validation pré-prod | VM Azure (`docker compose`) |
| `main` | Production | Databricks Apps |

### Cloner et démarrer en local

```bash
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
git checkout dev
cp .env.example .env
# Renseigner les valeurs dans .env (voir section Variables d'environnement)
```

Copier les CSV masterdata dans `data/masterdata/` (voir [data/masterdata/README.md](data/masterdata/README.md)).

```bash
docker compose -f docker-compose.file2edi.yml up --build -d
# UI  : http://localhost:8080
# API : http://localhost:8080/api/health/system
```

### Pousser en staging (VM Azure)

```bash
# Depuis ta branche locale dev
git push origin dev
# Ouvrir une PR dev → staging sur GitHub, merger

# Sur la VM Azure
git -C /root/GenieCommande pull origin staging
git -C /root/GenieCommande checkout staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

### Passer en production (Databricks Apps)

```bash
# PR staging → main sur GitHub, merger
# Databricks : git pull origin main, puis redéployer l'app
```

---

## Lancer sans Docker (Python natif)

```bash
pip install -r requirements.txt -r requirements-postgres.txt
cd frontend && npm install && npm run build && cd ..
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

- **UI :** http://localhost:8000
- **API :** http://localhost:8000/api/health/system

Pages : Cockpit · Convertir · Revue · Historique · Données maîtres · Paramètres

---

## UNB Profile : ELM_STANDARD uniquement

```
UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'
```

Aucun profil alternatif. Aucun fallback. Aucun override runtime. Le démarrage échoue si le profil est incorrect.

---

## Architecture

```
PDF_INBOX
  |-> pdf_extractor     (extraction données commande)
  |-> matcher           (résolution Sold-to + Ship-to)
  |-> pompac_rules      (résolution matière : EAN > fourre-tout > direct > fuzzy)
  |-> validations       (contrôles métier)
  |-> edifact_builder   (assemblage ORDERS D.96A)
  |-> sftp_delivery     (upload temp + rename + vérification)
  |-> duplicate_ledger  (déduplication par clé composite)
  |-> file_router       (PDF_PROCESSED ou PDF_ERROR)
```

---

## Flux de traitement PDF

1. Déposer le PDF dans `PDF_INBOX`
2. Le moteur extrait numéro de commande, date, lignes
3. Sold-to matchée (confiance min 75, code postal/ville requis)
4. Ship-to matchée filtrée par Sold-to (confiance min 80)
5. Matières résolues : EAN > fourre-tout > direct > fuzzy > REJET
6. Validation métier
7. Contrôle doublon (clé composite : order_number + soldto + pdf_hash)
8. Construction EDIFACT ORDERS D.96A
9. Envoi `.tst` en SFTP (stratégie temp + rename)
10. Vérification SFTP
11. Mise à jour du ledger doublon
12. PDF archivé dans `PDF_PROCESSED`

Sur tout échec : PDF vers `PDF_ERROR`, ledger NON mis à jour.

---

## Données maîtres

Source autoritaire (Databricks prod) : `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/`

Repo source quotidien (job sync prod) : `https://github.boschdevcloud.com/RSR1DY/masterdata.git`

| Fichier | Rôle |
|---|---|
| `10564_Customers.csv` | Lookup Sold-to (SOLDTO;NAME;ORT01;PSTLZ;STRAS;LAND1;VAT_NR) |
| `10564_Partners.csv` | Lookup Ship-to (SOLDTO;SHIPTO;LAND1;NAME;ORT01;PSTLZ;STRAS) |
| `10564_Materials.csv` | Index matières (MATNR;MAKTX) |
| `DB_Salesorder.csv` | Référence historique (comparaison uniquement) |

Sync quotidienne en production :

```bash
python scripts/sync_masterdata_repo.py \
  --repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
  --branch main \
  --target-dir /Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/ \
  --notify-api-url https://file2edi-5555213114570927.7.azure.databricksapps.com/api/masterdata/sync
```

---

## Livraison SFTP

Voir `docs/SFTP_DELIVERY.md` pour la documentation complète.

Stratégie d'upload :
1. Upload sous `<filename>.uploading`
2. Rename atomique vers `<filename>`
3. Vérification via `stat()`
4. Marquage `SFTP_SUBMITTED`

---

## Structure du projet

```
GenieCommande/
  server.py               # Serveur FastAPI principal (UI + API)
  config.ini              # Configuration moteur (chemins, EDI, SFTP)
  requirements.txt        # Dépendances Python
  requirements-postgres.txt
  docker-compose.file2edi.yml  # Stack Docker principale (dev + staging)
  Dockerfile.file2edi     # Image multi-stage (React + Python)
  app/                    # Moteur d'extraction full-code
  src/                    # Modules Python (config, SFTP, EDIFACT, matcher…)
  frontend/               # Interface React + TypeScript + Tailwind
    dist/                 # Build React versionné (prêt à servir)
  data/
    masterdata/           # CSV non versionnés (voir data/masterdata/README.md)
  lookups/                # Tables de correspondance CSV (EAN, fourre-tout…)
  tests/                  # Suite pytest (203 tests, 27 fichiers)
  docs/                   # Documentation opérationnelle
  scripts/                # Scripts utilitaires (sync masterdata, build…)
  databricks/             # Configuration déploiement Databricks Apps
```

---

## Tests

```bash
python -m pytest tests/ -v
```

203 tests couvrant extraction, matching, EDIFACT builder, SFTP, RBAC, golden fixtures.

---

## Variables d'environnement clés

Copier `.env.example` → `.env` et renseigner :

| Variable | Rôle | Requis |
|---|---|---|
| `PG_DATABASE_URL` | PostgreSQL (si vide : fallback SQLite) | Staging/Prod |
| `SFTP_HOST` / `SFTP_USERNAME` / `SFTP_PASSWORD` | Livraison SFTP | Prod |
| `DATABRICKS_TOKEN` | Auth Databricks Apps | Prod |
| `DATABRICKS_SERVER_HOSTNAME` | Workspace Databricks | Prod |
| `APP_ADMIN_USERS` | Emails admins séparés par virgule | Tous |
| `MOCK_MODE` | `true` = pas d'envoi SFTP réel | Dev/Staging |

---

## Valeurs interdites

Ces valeurs ne doivent **jamais** apparaître dans les fichiers générés, la config ou le code actif :
- `3020810000707`
- `54209794400681`

Le test `test_forbidden_strings.py` l'enforçe automatiquement.

---

## Documentation

| Doc | Contenu |
|-----|---------|
| [docs/FILE2EDI_DEPLOYMENT.md](docs/FILE2EDI_DEPLOYMENT.md) | Build, Docker, Databricks Apps |
| [docs/RUN_ME.md](docs/RUN_ME.md) | Référence CLI moteur batch |
| [docs/N8N_API_INTEGRATION.md](docs/N8N_API_INTEGRATION.md) | Runbook VM Azure + n8n |
| [docs/SFTP_DELIVERY.md](docs/SFTP_DELIVERY.md) | Livraison SFTP détaillée |
| [docs/POSTGRES_QUICKSTART.md](docs/POSTGRES_QUICKSTART.md) | PostgreSQL local + RBAC |
| [docs/SUPPORT_GUIDE.md](docs/SUPPORT_GUIDE.md) | Opérations quotidiennes + codes erreur |
| [docs/UAT_CHECKLIST.md](docs/UAT_CHECKLIST.md) | Checklist recette fonctionnelle |
| [databricks/README.md](databricks/README.md) | Déploiement Databricks Apps |

---

*Bosch Thermotechnologie France — EDIPUSHBOT / GenieCommande*
