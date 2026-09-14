# RUN_ME - Quick Reference

Cette page est la **référence rapide** pour lancer et gérer l'application File2EDI.  
Pour un guide détaillé, voir [FILE2EDI_DEPLOYMENT.md](FILE2EDI_DEPLOYMENT.md).

---

## 🚀 Lancer en Local (Docker)

### 1. Prérequis

```bash
git clone https://github.boschdevcloud.com/DIK1DY/GenieCommande.git
cd GenieCommande
cp .env.example .env
# Renseigner DATABRICKS_TOKEN et SFTP_* dans .env
```

### 2. PostgreSQL (optionnel - dev local)

```bash
docker compose -f docker-compose-pg.yml up -d
# pgAdmin: http://localhost:5050 (admin@edifact.local / admin)
```

### 3. Démarrer l'app

```bash
docker compose -f docker-compose.file2edi.yml up --build -d

# Vérifier
curl http://localhost:8090/api/health/system

# Logs
docker compose -f docker-compose.file2edi.yml logs -f file2edi
```

**UI:** http://localhost:8090

---

## 🐍 Lancer Natif (Python + Node)

```bash
# Installer dépendances
pip install -r requirements.txt -r requirements-postgres.txt

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Lancer serveur (nécessite PG_DATABASE_URL dans .env)
python server.py

# UI & API: http://localhost:8000
```

---

## 📤 Déployer sur Staging

```bash
# 1. Push code
git push bosch dev

# 2. Créer PR dev → staging (merger)

# 3. Sur VM staging
cd /root/GenieCommande
git fetch bosch staging
git pull bosch staging
docker compose -f docker-compose.file2edi.yml up --build -d

# 4. Vérifier
curl http://127.0.0.1:8090/api/health/system
```

---

## 🏭 Déployer en Prod

```bash
# 1. PR staging → main (merger)

# 2. Sur VM prod
cd /root/GenieCommande
git fetch bosch main
git pull bosch main
docker compose -f docker-compose.file2edi.yml down
docker compose -f docker-compose.file2edi.yml up --build -d

# 3. Vérifier
curl http://127.0.0.1:8090/api/health/system
docker compose -f docker-compose.file2edi.yml logs file2edi | head -20
```

---

## 🧪 Tests

```bash
# Unit tests
python -m pytest tests/ -v

# Test API (serveur en cours)
python scripts/smoke_file2edi_api.py

# Test extraction (50 PDFs aléatoires)
python scripts/test_random_pdfs.py --source "RAG Purchase Orders" --n 50 --seed 42
```

---

## 📊 Monitoring

```bash
# Status
docker compose -f docker-compose.file2edi.yml ps

# Logs temps réel
docker compose -f docker-compose.file2edi.yml logs -f file2edi

# Health endpoint
curl http://localhost:8090/api/health/system | jq .

# Masterdata freshness
curl http://localhost:8090/api/masterdata/stats
```

---

## 🆘 Arrêter & Nettoyer

```bash
# Arrêter sans supprimer données
docker compose -f docker-compose.file2edi.yml down

# Arrêter + nettoyer volumes (⚠️ perte données)
docker compose -f docker-compose.file2edi.yml down -v

# Redémarrer complètement
docker compose -f docker-compose.file2edi.yml down
docker system prune -f
docker compose -f docker-compose.file2edi.yml up --build -d
```

---

## 🔧 Migration PostgreSQL

Si passant de SQLite → PostgreSQL :

```bash
# 1. Démarrer PG
docker compose -f docker-compose-pg.yml up -d

# 2. Migrer données
python migrate_to_postgres.py \
  --src data/file2edi.db \
  --dst "postgresql+psycopg://edifact:edifact_dev_password@localhost:5432/edifact"

# 3. Vérifier
curl http://localhost:8000/api/orders | jq '.total'
```

---

## 📚 Docs Complètes

- [FILE2EDI_DEPLOYMENT.md](FILE2EDI_DEPLOYMENT.md) - Build & deploy détaillé
- [POSTGRES_MIGRATION.md](POSTGRES_MIGRATION.md) - Guides PostgreSQL
- [POSTGRES_IMPLEMENTATION_STATUS.md](POSTGRES_IMPLEMENTATION_STATUS.md) - Architecture DB
- [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md) - Support opérationnel
- [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md) - Flux PDF → EDIFACT
- [README.md](../README.md) - Vue d'ensemble projet
