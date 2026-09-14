# GenieCommande - File2EDI

Application **File2EDI** (React SPA + FastAPI Python) et moteur de génération **EDIFACT ORDERS D.96A** (`.tst`) pour Bosch Thermotechnologie France.

**Dépôt :** [github.boschdevcloud.com/DIK1DY/GenieCommande](https://github.boschdevcloud.com/DIK1DY/GenieCommande)  
**Version :** Phase 4 complète (PostgreSQL mandatory) + Phase 5+ (RBAC 2-role)  
**Status :** Production-ready (VM Azure + Docker Compose)

---

## 🏗️ Architecture Actuelle (2026-09)

```
┌─────────────────────────────────────────────────────────────┐
│ VM Azure (Docker Compose)                                   │
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │   React SPA      │         │   FastAPI        │         │
│  │  (port 8090)     │────────│   server.py      │         │
│  │   • Cockpit      │         │  (port 8000)     │         │
│  │   • Convertir    │         │  • REST API      │         │
│  │   • Revue        │         │  • LLM IA        │         │
│  │   • Historique   │         │  • RBAC          │         │
│  │   • Masterdata   │         │  • Workflows     │         │
│  │   • Paramètres   │         │  • PDF Extract   │         │
│  └──────────────────┘         └──────────────────┘         │
│                                       │                     │
│                           ┌───────────┴──────────┐          │
│                           │                      │          │
│                    ┌──────▼──────┐      ┌───────▼─────┐   │
│                    │ PostgreSQL   │      │  File2EDI   │   │
│                    │  (RLS + RBAC)│      │   Engine    │   │
│                    │  • auth_*    │      │ (OCR, LLM,  │   │
│                    │  • file2edi_*│      │  EDIFACT)   │   │
│                    └─────────────┘      └─────────────┘   │
└─────────────────────────────────────────────────────────────┘
               │                          │
     ┌─────────┴────────┐                │
     │                  │                │
  ┌──▼──┐          ┌────▼────┐        ┌──▼─────┐
  │SFTP │          │Databricks│       │GitHub  │
  │(SAP)│          │Model API │       │Repo    │
  │     │          │ (LLM)    │       │Masterdata
  └─────┘          └──────────┘       └────────┘
```

**Composants clés :**
- **PostgreSQL 15** : RBAC via RLS, persistance complète (no SQLite)
- **FastAPI** : REST API, LLM gateway (Databricks/OpenAI), auth, file routing
- **React SPA** : Interface responsive (desktop + mobile), Tailwind CSS
- **Databricks** : LLM Model Serving uniquement (endpoint distant)
- **GitHub** : Repo masterdata sync (via n8n webhook)
- **SFTP** : Livraison `.tst` vers SAP (stratégie temp + rename)

---

## 📊 Workflow de Développement

```
dev  ──PR──▶  staging  ──PR──▶  main
 │               │                │
local          VM Azure        VM Azure
               (pre-prod)      (prod)
```

| Branche | Rôle | Déploiement |
|---------|------|-------------|
| `dev` | Développement quotidien | Local (`docker compose`) |
| `staging` | Validation pré-prod | VM Azure (`docker compose.file2edi.yml`) |
| `main` | Production | VM Azure (`docker compose.file2edi.yml`) |

---

## 🔍 Documentation Complète

| Document | Audience | Contenu |
|----------|----------|---------|
| [**VALIDATION_RULES_ANALYSIS.md**](docs/VALIDATION_RULES_ANALYSIS.md) | Devs + Admins | **10 catégories de validation** : classification, extraction, matching, matière, EDIFACT, dédup, SFTP. Règles métier détaillées, decision tree, customisation. |
| [**VALIDATION_RULES_CLASSIFICATION.md**](docs/VALIDATION_RULES_CLASSIFICATION.md) | Devs + Product Owners | Classement par nature, étape, portée, impact et action de récupération. Points de cohérence à surveiller. |
| [**HEADER_FIELDS_PROPAGATION.md**](docs/HEADER_FIELDS_PROPAGATION.md) | Devs + Product Owners | Schéma de propagation des modifications d'en-tête, Sold-to, Ship-to, adresses et codes postaux. |
| [**validation_rules_inventory.xlsx**](docs/validation_rules_inventory.xlsx) | Managers + Ops + Devs | Classeur filtrable des règles, classes, blocages, sévérités, actions et incohérences. Générateur : `scripts/generate_validation_rules_excel.py`. |
| [**VALIDATION_RULES_QUICK_REFERENCE.md**](docs/VALIDATION_RULES_QUICK_REFERENCE.md) | Managers + Ops | **Quick ref** des sévérités, blocages, revue. Cas d'usage, SLA, monitoring. |
| [**REJECTION_CODES_CATALOG.md**](docs/REJECTION_CODES_CATALOG.md) | Devs + Support | **11 codes rejection** : descriptions, triggers, récupération. Issue taxonomy, aliases, FAQ. |
| [**FILE2EDI_DEPLOYMENT.md**](docs/FILE2EDI_DEPLOYMENT.md) | DevOps + Admins | Déploiement complet 3 phases (local, staging, prod), env vars, troubleshooting. |
| [**RUN_ME.md**](docs/RUN_ME.md) | Ops | Quick commands : start/deploy/monitor. |
| [**SUPPORT_GUIDE.md**](docs/SUPPORT_GUIDE.md) | Ops + Support | Daily checks, problem matrix, backup/restore, RBAC admin. |
| [**POSTGRES_IMPLEMENTATION_STATUS.md**](docs/POSTGRES_IMPLEMENTATION_STATUS.md) | Product Owners | Phase 4 complete (mandatory PG), Phase 5 decision pending (RBAC filtering strategy). |
| [**PROJECT_STATUS.md**](docs/PROJECT_STATUS.md) | Management | Global status matrix, all phases 1-6, next steps. |


## ⚡ Démarrage Rapide (Local)

### 1. Cloner et configurer

```bash
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
git checkout dev
cp .env.example .env
# Renseigner DATABRICKS_TOKEN, SFTP_* dans .env
# Copier masterdata CSV dans data/masterdata/
```

### 2. Lancer l'app

**Avec Docker** (recommandé) :
```bash
docker compose -f docker-compose.file2edi.yml up --build -d
# UI  : http://localhost:8090
# API : http://localhost:8090/api/health/system
```

**Natif Python** :
```bash
pip install -r requirements.txt -r requirements-postgres.txt
cd frontend && npm install && npm run build && cd ..
python server.py
# UI & API : http://localhost:8000
```

**Avec PostgreSQL local** (dev only) :
```bash
docker compose -f docker-compose-pg.yml up -d         # PG 15 + pgAdmin
docker compose -f docker-compose.file2edi.yml up -d   # App
# pgAdmin: http://localhost:5050 (admin@edifact.local / admin)
```

---

## 🚀 Déploiement (VM Azure)

### Staging

```bash
# 1. Push local vers Bosch remote (dev branche)
git push bosch dev

# 2. Créer PR : dev → staging sur GitHub
# 3. Merger la PR
# 4. Sur VM staging :
cd /root/GenieCommande
git fetch origin
git checkout staging
git pull origin staging
docker compose -f docker-compose.file2edi.yml up --build -d
```

### Production

```bash
# 1. Créer PR : staging → main
# 2. Merger
# 3. Sur VM prod :
cd /root/GenieCommande
git fetch origin
git checkout main
git pull origin main
docker compose -f docker-compose.file2edi.yml up --build -d
```

**Vérification post-déploiement :**
```bash
curl http://localhost:8090/api/health/system
# Doit voir : {"status":"ok","ocr":"connected","masterdata_sync":{...}}
docker compose -f docker-compose.file2edi.yml ps
docker compose -f docker-compose.file2edi.yml logs file2edi --tail 50
```

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
| `DB_Materials.csv` | Index matières (MATNR;MAKTX + colonnes Statut si présentes) |
| `DB_Salesorder.csv` | Référence historique (comparaison uniquement) |

Sync quotidienne en production : webhook n8n (bouton Synchroniser ou cron n8n).
Mise à jour manuelle : import CSV/Parquet par un administrateur dans Données maîtres.

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
      store.py            # Persistance File2EDI (PostgreSQL obligatoire en runtime)
      mapper.py           # Mapping engine → React API contract
    masterdata_runtime.py # Cache masterdata + sync metadata
    masterdata_n8n.py     # Déclenchement webhook n8n pour sync GitHub
  frontend/               # Interface React + TypeScript + Tailwind (responsive)
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
    browser_smoke.mjs     # Tests navigateur Playwright (responsive)
    smoke_file2edi_api.py # Smoke API rapide
  databricks/             # Role Databricks: Model Serving + masterdata
```

---

## Tests

```bash
python -m pytest tests/ -v
```

La suite couvre extraction, matching, EDIFACT builder, SFTP, RBAC, golden fixtures, Phase 1+2 engines, auth profil, logs métier.  
**371 tests** passent (août 2026).

Smoke API locale (serveur démarré) :

```bash
python scripts/smoke_file2edi_api.py
# Endpoints protégés (optionnel) :
python scripts/smoke_file2edi_api.py --actor <user> --password <password>
```

### Tests navigateur (Playwright)

```powershell
npm install playwright@1.49.1 --no-save
npx playwright install chromium
$env:F2EDI_USER='<user>'; $env:F2EDI_PASSWORD='<password>'
node scripts/browser_smoke.mjs
```

Vérifie : page login, routes desktop/mobile, sidebar responsive, hamburger menu.

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
| `PG_DATABASE_URL` | PostgreSQL obligatoire (pas de fallback SQLite runtime) | Staging/Prod |
| `FILE2EDI_POSTGRES_STRICT` | Conservé pour compose/CI ; `PG_DATABASE_URL` reste requis | Staging/Prod |
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

## Extraction - Champs extraits par ligne de commande

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

## Logs métier (Business Events)

L'application trace toutes les actions utilisateur dans `file2edi_business_events` :
- `auth.login`, `auth.logout`
- `order.patch_header`, `order.patch_partner`, `order.patch_line`
- `order.generate_edifact`, `order.send_sftp`
- `masterdata.sync`, `settings.update`

Chaque événement capture acteur, action, résultat, durée, et les valeurs `from`/`to` des champs modifiés.

Visible dans l'onglet **Paramètres → Logs → Métier**.

---

## Documentation

| Doc | Contenu |
|-----|---------|
| [docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md) | Schéma complet extraction PDF → revue → EDIFACT |
| [docs/RUN_ME.md](docs/RUN_ME.md) | Référence CLI moteur batch |
| [docs/N8N_API_INTEGRATION.md](docs/N8N_API_INTEGRATION.md) | Runbook VM Azure + n8n |
| [docs/SFTP_DELIVERY.md](docs/SFTP_DELIVERY.md) | Livraison SFTP détaillée |
| [docs/POSTGRES_QUICKSTART.md](docs/POSTGRES_QUICKSTART.md) | PostgreSQL local + RBAC |
| [docs/SUPPORT_GUIDE.md](docs/SUPPORT_GUIDE.md) | Opérations quotidiennes + codes erreur |
| [docs/UAT_CHECKLIST.md](docs/UAT_CHECKLIST.md) | Checklist recette fonctionnelle |
| [databricks/README.md](databricks/README.md) | Role Databricks: Model Serving + masterdata |

---

*Bosch Thermotechnologie France - EDIPUSHBOT / GenieCommande*
