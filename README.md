# GenieCommande

Application **File2EDI** (React + FastAPI) et moteur Python de génération EDIFACT ORDERS D.96A (`.tst`) pour Bosch Thermotechnologie France.

**Dépôt :** [github.boschdevcloud.com/DIK1DY/GenieCommande](https://github.boschdevcloud.com/DIK1DY/GenieCommande)

---

## Workflow de développement

```
dev  ──PR──▶  staging  ──PR──▶  main
 │               │                │
local          VM Azure        VM Azure
               (pre-prod)      (prod)
```

| Branche | Rôle | Déploiement |
|---------|------|-------------|
| `dev` | Développement quotidien | Local (`docker compose`) |
| `staging` | Validation pré-prod | VM Azure (`docker compose`) |
| `main` | Production | VM Azure (`docker compose`) |

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

### Passer en production (VM Azure)

```bash
# PR staging → main sur GitHub, merger
# Sur la VM prod : git pull origin main, puis relancer docker compose
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
    engines/
      delivery_date.py        # Extraction date livraison + urgence  [Phase 2]
      special_instructions.py # Extraction notes / instructions  [Phase 2]
      llm_orderlines.py       # LLM (Claude Sonnet 4) extraction lignes
      delivery_address.py     # Résolution adresse livraison
  src/                    # Modules Python (config, SFTP, EDIFACT, matcher…)
    file2edi/
      store.py            # Persistance File2EDI (PostgreSQL prioritaire + fallback SQLite)
      mapper.py           # Mapping engine → React API contract
  frontend/               # Interface React + TypeScript + Tailwind
    dist/                 # Build React versionné (prêt à servir)
  config/
    extraction.yaml       # Anchors OCR, scoring, keywords
  data/
    masterdata/           # CSV non versionnés (voir data/masterdata/README.md)
    file2edi_schema.sql   # Schéma SQLite file2edi_order_lines
  lookups/                # Tables de correspondance CSV (EAN, fourre-tout…)
  tests/                  # Suite pytest (extraction, matching, EDIFACT, SFTP, RBAC)
  docs/                   # Documentation opérationnelle
  scripts/                # Scripts utilitaires
    migrate_add_fields.py # Migration DB Phase 3
    backfill_new_fields.py # Backfill historique Phase 3
    test_random_pdfs.py   # Test extraction sur N PDFs aléatoires
  databricks/             # Role Databricks: Model Serving + masterdata
```

---

## Tests

```bash
python -m pytest tests/ -v
```

La suite couvre extraction, matching, EDIFACT builder, SFTP, RBAC, golden fixtures, Phase 1+2 engines.

Smoke API locale (serveur démarré) :

```bash
python scripts/smoke_file2edi_api.py
# Endpoints protégés (optionnel) :
python scripts/smoke_file2edi_api.py --actor <user> --password <password>
```

```bash
# Test extraction sur 50 PDFs aléatoires (RAG Purchase Orders)
python scripts/test_random_pdfs.py --source "RAG Purchase Orders" --n 50 --seed 42
```

| Résultats seed=42 (50 PDFs) | Score |
|---|---|
| Documents traités | 39/50 (78%) |
| Numéro commande | 100% |
| Date commande | 100% |
| Total HT | 95% |
| Code article | 100% |
| Quantité | 100% |
| Prix unitaire | 100% |
| Date livraison | 84% |

---

## Variables d'environnement clés

Copier `.env.example` → `.env` et renseigner :

| Variable | Rôle | Requis |
|---|---|---|
| `PG_DATABASE_URL` | PostgreSQL principal (fallback SQLite seulement si `FILE2EDI_POSTGRES_STRICT=false`) | Staging/Prod |
| `FILE2EDI_POSTGRES_STRICT` | `true` = échec au démarrage si PostgreSQL indisponible (recommandé en staging/prod) | Staging/Prod |
| `SFTP_HOST` / `SFTP_USERNAME` / `SFTP_PASSWORD` | Livraison SFTP | Prod |
| `DATABRICKS_TOKEN` | Auth HTTP vers Databricks Model Serving | Prod |
| `DATABRICKS_HOST` | Workspace Databricks qui heberge le LLM | Prod |
| `DATABRICKS_MODEL_ENDPOINT` | Endpoint Model Serving utilise pour l'extraction | Prod |
| `APP_ADMIN_USERS` | Emails admins séparés par virgule | Tous |
| `MOCK_MODE` | `true` = pas d'envoi SFTP réel | Dev/Staging |

---

## Valeurs interdites

Ces valeurs ne doivent **jamais** apparaître dans les fichiers générés, la config ou le code actif :
- `3020810000707`
- `54209794400681`

Le test `test_forbidden_strings.py` l'enforçe automatiquement.

---

## Extraction — Champs extraits par ligne de commande

| Champ | Source | Phase |
|-------|--------|-------|
| `bosch_article` | Article number (ELM/direct) | Core |
| `designation` | Description OCR | Core |
| `quantity` | QTÉ / PCE / ratio montant/prix | Core + Phase 1 |
| `unit_price` | Prix HT | Core |
| `amount` | Montant ligne HT | Core |
| `customer_reference` | Réf client / PO / commande client | Phase 1 |
| `payment_terms` | Conditions paiement (NET 30J, COMPTANT…) | Phase 1 |
| `delivery_date` | Date livraison souhaitée par ligne | Phase 2 |
| `special_instructions` | Remarques, instructions, FRAGILE… | Phase 2 |
| `warnings` | ⚠️ URGENT, IMPORTANT, ATTENTION | Phase 2 |

### Schéma DB `file2edi_order_lines`

```sql
CREATE TABLE file2edi_order_lines (
  line_id, order_id, line_number,
  customer_reference,        -- Phase 1
  bosch_article, designation, quantity, unit, unit_price, amount,
  confidence, status, comment, manually_edited,
  payment_terms,             -- Phase 1
  delivery_date,             -- Phase 2
  special_instructions,      -- Phase 2
  warnings                   -- Phase 2
);
```

### Migration

```bash
# Ajouter les colonnes Phase 1+2 (idempotent)
docker compose exec api python scripts/migrate_add_fields.py
# Backfill lignes existantes
docker compose exec api python scripts/backfill_new_fields.py
```

---

## Documentation

| Doc | Contenu |
|-----|---------|
| [docs/FILE2EDI_DEPLOYMENT.md](docs/FILE2EDI_DEPLOYMENT.md) | Build, Docker, VM Azure |
| [docs/RUN_ME.md](docs/RUN_ME.md) | Référence CLI moteur batch |
| [docs/N8N_API_INTEGRATION.md](docs/N8N_API_INTEGRATION.md) | Runbook VM Azure + n8n |
| [docs/SFTP_DELIVERY.md](docs/SFTP_DELIVERY.md) | Livraison SFTP détaillée |
| [docs/POSTGRES_QUICKSTART.md](docs/POSTGRES_QUICKSTART.md) | PostgreSQL local + RBAC |
| [docs/SUPPORT_GUIDE.md](docs/SUPPORT_GUIDE.md) | Opérations quotidiennes + codes erreur |
| [docs/UAT_CHECKLIST.md](docs/UAT_CHECKLIST.md) | Checklist recette fonctionnelle |
| [databricks/README.md](databricks/README.md) | Role Databricks: Model Serving + masterdata |

---

*Bosch Thermotechnologie France — EDIPUSHBOT / GenieCommande*
