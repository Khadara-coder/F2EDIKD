# File2EDI React frontend

Interface SaaS pour convertir des commandes PDF en fichiers EDIFACT `.tst`.

## Stack unifiée (production)

Le frontend React est servi par **`server.py`** (FastAPI Python) — même déploiement sur Databricks Apps et Docker.

```
frontend/dist  →  server.py  →  src/file2edi/  →  moteur EDIFACT + Databricks
```

Voir [docs/FILE2EDI_DEPLOYMENT.md](../docs/FILE2EDI_DEPLOYMENT.md) pour le guide complet.

## Démarrage rapide

### Docker Compose (recommandé)

```powershell
.\scripts\build_file2edi.ps1 -Docker
```

→ http://localhost:8080

### Local (Python + build React)

```powershell
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --host 0.0.0.0 --port 8000
```

→ http://localhost:8000

### Dev hot-reload

```powershell
# Terminal 1
uvicorn server:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

→ http://localhost:5173 (proxy API → :8000)

## Pages

| Route | Description |
|-------|-------------|
| `/` | Cockpit |
| `/convertir` | Upload PDF |
| `/revue/:orderId` | Revue éditable |
| `/historique` | Historique |
| `/donnees-maitres` | Master data |
| `/parametres` | Configuration |

## Note sur `backend/` (Node)

Le dossier `backend/` Node/Express reste disponible pour tests isolés en mode mock.
**La stack de production utilise uniquement `server.py` (Python).**
