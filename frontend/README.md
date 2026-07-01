# File2EDI React frontend

Interface **React + TypeScript + Tailwind** (sidebar, Cockpit, Convertir, Revue, etc.).

> L’ancienne UI monolithique (`static/index.html`, Alpine.js) reste dans le dépôt pour référence mais **n’est plus servie par défaut**. Utilisez `FILE2EDI_UI=legacy` uniquement si besoin.

## Stack de production

```
frontend/dist  →  server.py (FILE2EDI_UI=react)  →  src/file2edi/  →  moteur EDIFACT
```

## Démarrage

```powershell
cd frontend && npm install && npm run build && cd ..
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

→ http://localhost:8000

## Routes React

| URL | Page |
|-----|------|
| `/` | Cockpit |
| `/convertir` | Upload + aperçu extraction |
| `/revue` | Liste de toutes les commandes converties |
| `/revue/:orderId` | Revue éditable (PDF, lignes, EDIFACT) |
| `/historique` | Historique |
| `/donnees-maitres` | Données maîtres |
| `/parametres` | Paramètres |

Les URLs directes (`/revue`, `/revue/ord-…`) fonctionnent après rechargement (fallback SPA dans `server.py`).

## Dev hot-reload

```powershell
# Terminal 1
python -m uvicorn server:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

→ http://localhost:5173 (proxy `/api` → :8000)

## Ancienne UI (désactivée par défaut)

```powershell
$env:FILE2EDI_UI="legacy"
python -m uvicorn server:app --port 8000
```

Voir [docs/FILE2EDI_DEPLOYMENT.md](../docs/FILE2EDI_DEPLOYMENT.md).
