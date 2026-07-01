# File2EDI React frontend

Interface **React + TypeScript + Tailwind** (sidebar, Cockpit, Convertir, Revue, etc.).

## Stack de production

```
frontend/dist  →  server.py  →  src/file2edi/  →  moteur EDIFACT
```

## Démarrage

```powershell
cd frontend && npm install && npm run build && cd ..
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

→ http://localhost:8000

## Routes

| URL | Page |
|-----|------|
| `/` | Cockpit |
| `/convertir` | Upload + aperçu extraction |
| `/revue` | Liste des commandes converties |
| `/revue/:orderId` | Revue éditable (PDF, lignes, EDIFACT) |
| `/historique` | Historique |
| `/donnees-maitres` | Données maîtres |
| `/parametres` | Paramètres |

## Dev hot-reload

```powershell
# Terminal 1
python -m uvicorn server:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

→ http://localhost:5173 (proxy `/api` → :8000)

Voir [docs/FILE2EDI_DEPLOYMENT.md](../docs/FILE2EDI_DEPLOYMENT.md).
