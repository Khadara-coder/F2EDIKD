# File2EDI / EDIFACT Orders Generator

Application **File2EDI** (React + FastAPI) et moteur Python de génération EDIFACT ORDERS D.96A (`.tst`) pour Bosch Thermotechnologie France.

**Dépôt Bosch :** [github.boschdevcloud.com/DIK1DY/F2EDIDK](https://github.boschdevcloud.com/DIK1DY/F2EDIDK)  
**Miroir public :** [github.com/Khadara-coder/F2EDIKD](https://github.com/Khadara-coder/F2EDIKD)

---

## Démarrage rapide (après clone)

```powershell
git clone https://github.boschdevcloud.com/DIK1DY/F2EDIDK.git
cd F2EDIDK
copy .env.example .env
pip install -r requirements.txt
```

Copiez les CSV masterdata dans `data/masterdata/` (voir [data/masterdata/README.md](data/masterdata/README.md)).

```powershell
cd frontend
npm install
npm run build
cd ..
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

- **UI :** http://localhost:8000  
- **API :** http://localhost:8000/api/health/system  

Pages : Cockpit · Convertir · Revue · Historique · Données maîtres · Paramètres

Déploiement Docker / Databricks : [docs/FILE2EDI_DEPLOYMENT.md](docs/FILE2EDI_DEPLOYMENT.md)

---

## EDIFACT batch (moteur Python)

---

## UNB Profile: ELM_STANDARD ONLY

```
UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'
```

No alternate profile. No fallback. No runtime override. Startup fails if the profile is wrong.

---

## Architecture

```
PDF_INBOX
  |-> pdf_extractor     (extract order data)
  |-> matcher           (Sold-to + Ship-to resolution)
  |-> pompac_rules      (material resolution: EAN > fourre-tout > direct > fuzzy)
  |-> validations       (business rule checks)
  |-> edifact_builder   (ORDERS D.96A assembly)
  |-> sftp_delivery     (temp upload + rename + verify)
  |-> duplicate_ledger  (composite key duplicate prevention)
  |-> file_router       (PDF_PROCESSED or PDF_ERROR)
```

---

## n8n Project Analysis

Before generation, the engine analyses the existing n8n project at:
```
/Workspace/Users/rsr1dy@bosch.com/n8n
```
and generates `docs/N8N_ANALYSIS_REPORT.md` with all verified rules.

To run analysis only:
```
python src/edifact_orders_engine.py --analyse-n8n-only
```

---

## Master Data

Authoritative source (Databricks prod): `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/`

| File | Role |
|---|---|
| `10564_Customers.csv` | Sold-to lookup (SOLDTO;NAME;ORT01;PSTLZ;STRAS;LAND1;VAT_NR) |
| `10564_Partners.csv` | Ship-to lookup (SOLDTO;SHIPTO;LAND1;NAME;ORT01;PSTLZ;STRAS) |
| `10564_Materials.csv` | Material index (MATNR;MAKTX) |
| `DB_Salesorder.csv` | Historical reference (comparison only) |

---

## PDF Processing Flow

1. Drop PDF in `PDF_INBOX`
2. Engine extracts order number, date, lines
3. Sold-to matched (min confidence 75, postal/city required)
4. Ship-to matched filtered by Sold-to (min confidence 80)
5. Materials resolved: EAN > fourre-tout > direct > fuzzy > REJECT
6. Business validation
7. Duplicate check (composite key: order_number + soldto + pdf_hash)
8. EDIFACT ORDERS D.96A built
9. `.tst` submitted to SFTP (temp rename strategy)
10. SFTP verified
11. Duplicate ledger updated
12. PDF archived to `PDF_PROCESSED`

On any failure: PDF goes to `PDF_ERROR`, ledger NOT updated.

---

## SFTP Delivery

See `docs/SFTP_DELIVERY.md` for full documentation.

Upload strategy:
1. Upload as `<filename>.uploading`
2. Remote rename to `<filename>`
3. Verify via `stat()`
4. Mark `SFTP_SUBMITTED`

---

## Project Structure

```
edifact_generator/
  config.ini            # All configuration
  requirements.txt      # pip dependencies
  build_exe.bat         # PyInstaller build script
  install_task.ps1      # Windows Task Scheduler setup
  validate_project.py   # Pre-deployment validation
  src/                  # Python source modules
  lookups/              # CSV lookup tables
  data/                 # Ledgers (duplicate, sftp delivery)
  tests/                # pytest test suite (8 files)
  docs/                 # Operational documentation
  outbox/               # Local generated, submitted, failed archives
  logs/                 # Rotating log files
```

---

## Quick Start

See `docs/RUN_ME.md` and `docs/FILE2EDI_DEPLOYMENT.md` (React UI + Databricks).

### File2EDI Web UI (React)

```powershell
.\scripts\build_file2edi.ps1 -Docker    # Docker → http://localhost:8080
# or
cd frontend && npm run build && uvicorn server:app --port 8000   # → http://localhost:8000
```

## Build

```
build_exe.bat
```

Output: `dist/EDIFACT_Orders_Generator.exe`

## Test

```
python -m pytest tests\ -v
```

## Deploy

See `docs/TASK_SCHEDULER.md` for Windows Task Scheduler configuration.

---

## Forbidden Values

These values must NEVER appear in generated output, config, or active code:
- `3020810000707`
- `54209794400681`

The `test_forbidden_strings.py` test enforces this automatically.

---

*Bosch Thermotechnologie France - EDIPUSHBOT / F2EDI*
