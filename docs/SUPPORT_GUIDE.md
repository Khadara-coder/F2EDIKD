# Guide de Support Opérationnel - File2EDI

**Version:** Phase 4+ (PostgreSQL + RBAC)  
**Pour:** Administrateurs, DevOps, support technique  
**Mise à jour:** 2026-09-14

---

## 📋 Contrôles Quotidiens

### Matin (08:00)

```bash
# 1. Status application
curl http://<prod-vm>:8090/api/health/system | jq .

# 2. Masterdata sync freshness
curl http://<prod-vm>:8090/api/masterdata/stats | jq '.sync_age_hours, .sync_commit'

# 3. Logs pour erreurs critiques
docker compose -f docker-compose.file2edi.yml logs file2edi --since 24h | grep -E "ERROR|CRITICAL" | wc -l

# 4. Espace disque
docker system df | head -5
```

**Alertes:**
- ❌ Health check != "ok" → Redémarrer app
- ❌ masterdata_sync.status != "fresh" → Trigger sync manuelle
- ❌ > 5 CRITICAL logs → Vérifier logs complets

### Après Traitement des Fichiers (14:00)

```bash
# 1. Fichiers traités aujourd'hui
docker compose -f docker-compose.file2edi.yml logs file2edi --since 24h | \
  grep -E "PDF_INBOX|EDIFACT|SFTP_SUBMITTED" | tail -20

# 2. Fichiers en PDF_ERROR (à traiter manuellement)
ls -la data/pdf/PDF_ERROR/ | head -10

# 3. Confirmations SFTP (ledger)
tail -20 data/sftp_delivery_ledger.csv

# 4. Doublons détectés
tail -10 data/duplicate_ledger.csv
```

---

## 🔧 Problèmes Courants et Solutions

### "Health check failed"

```bash
# 1. Vérifier PostgreSQL
docker compose -f docker-compose.file2edi.yml ps postgres

# 2. Si postgres down:
docker compose -f docker-compose-pg.yml up -d
sleep 10
docker compose -f docker-compose.file2edi.yml up -d

# 3. Vérifier logs
docker compose -f docker-compose.file2edi.yml logs file2edi | tail -50
```

### "OCR not connected"

```bash
# 1. Vérifier Tesseract
docker compose -f docker-compose.file2edi.yml exec file2edi tesseract --version

# 2. Si absent, rebuild:
docker compose -f docker-compose.file2edi.yml build --no-cache file2edi
docker compose -f docker-compose.file2edi.yml restart file2edi

# 3. Vérifier logs OCR
docker compose -f docker-compose.file2edi.yml logs file2edi | grep -i ocr
```

### "SFTP upload failed"

```bash
# 1. Vérifier credentials
cat .env | grep SFTP_

# 2. Test connexion manuelle
sftp -o Port=22 $SFTP_USERNAME@$SFTP_HOST

# 3. Vérifier droits répertoire SFTP
sftp> ls -la $SFTP_REMOTE_DIR

# 4. Si credentials changés:
# a. Mettre à jour .env
# b. Redémarrer: docker compose -f docker-compose.file2edi.yml restart file2edi
# c. Valider: python scripts/smoke_file2edi_api.py
```

### "Masterdata out of date"

```bash
# 1. Vérifier sync status
curl http://<prod-vm>:8090/api/masterdata/stats

# 2. Trigger sync manuelle
# Option A: Interface (Paramètres → Données maîtres → Synchroniser)
# Option B: API
curl -X POST http://<prod-vm>:8090/api/masterdata/reload-cache \
  -H "Authorization: Bearer $API_KEY"

# 3. Vérifier après 30s
curl http://<prod-vm>:8090/api/masterdata/stats | jq '.sync_age_hours'
```

### "Database connection refused"

```bash
# 1. Vérifier connexion PG
echo $PG_DATABASE_URL

# 2. Tester connexion
python -c "import psycopg; conn = psycopg.connect('$PG_DATABASE_URL'); print('OK')"

# 3. Si cloud PG (Azure):
# a. Vérifier IP VM whitelist dans Azure Portal
# b. Vérifier firewall rules
# c. Tester: psql postgresql://...

# 4. Redémarrer postgres local
docker compose -f docker-compose-pg.yml restart postgres
```

---

## 🗄️ Backup & Restauration

### Backup PostgreSQL (Quotidien)

```bash
# 1. Dump PostgreSQL
docker compose -f docker-compose-pg.yml exec postgres pg_dump -U edifact \
  -d edifact_prod > backup_pg_$(date +%Y%m%d_%H%M%S).sql

# 2. Archiver (ex: S3, blob storage)
az storage blob upload-batch \
  -d backups \
  -s . \
  -p "backup_pg_*.sql"
```

### Restaurer depuis Backup

```bash
# 1. Arrêter app
docker compose -f docker-compose.file2edi.yml down

# 2. Supprimer volume (⚠️ perte données courantes!)
docker volume rm geniecommande_prod_postgres_data

# 3. Redémarrer PG (vierge)
docker compose -f docker-compose-pg.yml up -d

# 4. Restaurer données
docker compose -f docker-compose-pg.yml exec -T postgres psql -U edifact -d edifact_prod \
  < backup_pg_20260914_083000.sql

# 5. Redémarrer app
docker compose -f docker-compose.file2edi.yml up -d
```

### Backup Application (Volumes)

```bash
# 1. Archiver data/ (PDFs, masterdata, logs)
docker run --rm -v geniecommande_prod_file2edi_data:/data \
  -v /backup:/backup alpine \
  tar czf /backup/app_data_$(date +%Y%m%d).tar.gz /data

# 2. Vérifier
tar tzf /backup/app_data_*.tar.gz | head -20
```

---

## 📊 Performance & Optimisation

### Requêtes Lentes (Query Analysis)

```bash
# 1. Activer query logging dans PostgreSQL
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c \
  "ALTER SYSTEM SET log_min_duration_statement = 1000;"

# 2. Recharger config
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c "SELECT pg_reload_conf();"

# 3. Vérifier logs lents
docker compose -f docker-compose-pg.yml logs postgres | grep "duration: "

# 4. Créer index si manquant
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c \
  "CREATE INDEX CONCURRENTLY idx_orders_soldto ON file2edi_orders(soldto);"
```

### Espace Disque

```bash
# 1. Vérifier usage
docker system df

# 2. Nettoyer old images (>7 jours)
docker image prune -a -f --filter "until=168h"

# 3. Nettoyer containers arrêtés
docker container prune -f

# 4. Archiver old PDFs (avant de supprimer)
tar czf archive_pdf_old_$(date +%Y%m).tar.gz data/pdf/PDF_PROCESSED/
rm -rf data/pdf/PDF_PROCESSED/*
```

---

## 👥 RBAC & Auth

### Activer/Désactiver Utilisateur

```bash
# 1. Afficher utilisateurs
docker compose -f docker-compose.file2edi.yml exec file2edi python -c \
  "from src.database_pg import PostgresDB; db = PostgresDB(); \
   import asyncio; print(asyncio.run(db.list_users()))"

# 2. Désactiver utilisateur
docker compose -f docker-compose.file2edi.yml exec file2edi python -c \
  "from src.database_pg import PostgresDB; db = PostgresDB(); \
   import asyncio; print(asyncio.run(db.deactivate_user('user@bosch.com')))"

# 3. Alternative: Mettre à jour .env
APP_ADMIN_USERS='admin1@bosch.com,admin2@bosch.com'
docker compose -f docker-compose.file2edi.yml restart file2edi
```

### Attribuer Rôle ADV & Scopes

```bash
# 1. Assigner ADV à clients Sold-to
# Exemple SQL :
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c "
  INSERT INTO auth_user_adv_scope (user_id, soldto)
  SELECT u.user_id, '3015981600108'
  FROM auth_users u
  WHERE u.email = 'adv@bosch.com' AND u.role = 'adv'
  ON CONFLICT DO NOTHING;
"

# 2. Vérifier
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c \
  "SELECT * FROM auth_user_adv_scope WHERE user_email = 'adv@bosch.com';"
```

---

## 📈 Qualité d'Extraction

### Cibles de Qualité (Prod)

| Champ | Cible | Commande de vérif |
|-------|-------|-------------------|
| bosch_article | 99%+ | `analyze_columns_quality.py` |
| quantity | 80%+ | `analyze_columns_quality.py` |
| unit_price | 90%+ | `analyze_columns_quality.py` |
| amount | 85%+ | `analyze_columns_quality.py` |
| delivery_date | 84%+ | `analyze_columns_quality.py` |

### Test Extraction

```bash
# 1. Test sur N PDFs aléatoires
python scripts/test_random_pdfs.py \
  --source "RAG Purchase Orders" \
  --n 50 \
  --seed 42

# 2. Vérifier qualité colonnes
python scripts/analyze_columns_quality.py

# 3. Analyser anomalies
docker compose -f docker-compose-pg.yml exec postgres \
  psql -U edifact -d edifact_prod -c \
  "SELECT anomaly_type, COUNT(*) as count FROM file2edi_order_anomalies \
   GROUP BY anomaly_type ORDER BY count DESC;"
```

---

## 🔄 Mise à Jour du Code

### Staging (Pré-prod)

```bash
# 1. Récupérer last staging
cd /root/GenieCommande
git fetch bosch staging
git pull bosch staging

# 2. Build & restart (volumes persistants conservés)
docker compose -f docker-compose.file2edi.yml up --build -d

# 3. Vérifier
sleep 30
curl http://127.0.0.1:8090/api/health/system
docker compose -f docker-compose.file2edi.yml logs file2edi --tail 20
```

### Production (Cutover)

```bash
# 1. Synchroniser main
cd /root/GenieCommande
git fetch bosch main
git pull bosch main

# 2. Graceful shutdown (volumes conservés)
docker compose -f docker-compose.file2edi.yml down

# 3. Build & start nouvelle version
docker compose -f docker-compose.file2edi.yml up --build -d

# 4. Monitoring (1h)
docker compose -f docker-compose.file2edi.yml logs -f file2edi

# 5. Si problème: rollback
git checkout main~1
docker compose -f docker-compose.file2edi.yml down
docker compose -f docker-compose.file2edi.yml up --build -d
```

---

## 🆘 Escalade (Support Urgent)

**Personne à contacter :** DIK1DY (dik1dy@bosch.com)

**Checklist avant escalade :**
1. ✅ Vérifier `docker compose ps`
2. ✅ Vérifier logs app: `docker compose logs file2edi --tail 100`
3. ✅ Vérifier PostgreSQL: `docker compose -f docker-compose-pg.yml ps`
4. ✅ Vérifier conectivité SFTP: `sftp user@host`
5. ✅ Vérifier espace disque: `docker system df`

**Informations à inclure :**
- Last successful processing: ___
- Error message (complet): ___
- Steps to reproduce: ___
- Output de `docker compose ps` et `docker system df`: ___

---

## 📚 Docs Complémentaires

- [FILE2EDI_DEPLOYMENT.md](FILE2EDI_DEPLOYMENT.md) - Build & deployment
- [POSTGRES_IMPLEMENTATION_STATUS.md](POSTGRES_IMPLEMENTATION_STATUS.md) - DB architecture
- [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md) - PDF processing
- [SFTP_DELIVERY.md](SFTP_DELIVERY.md) - SFTP upload strategy
- [README.md](../README.md) - Project overview

Si le générateur produit des fichiers incorrects :

1. Passer `MOCK_MODE=true` dans `.env` immédiatement → `docker compose restart file2edi`
2. Prévenir le contact ELM de suspendre le traitement des `.tst` récents
3. Analyser `logs/edifact.log` pour le batch concerné
4. Corriger le problème, exécuter `python validate_project.py`
5. Repasser `MOCK_MODE=false` et redémarrer après confirmation du fix

En production VM, rollback via :
```bash
git -C /root/GenieCommande checkout <commit-précédent>
docker compose -f /root/GenieCommande/docker-compose.file2edi.yml up --build -d
```

---

## Refresh du rapport n8n

```bash
python src/edifact_orders_engine.py --analyse-n8n-only
```

Sortie : `docs/N8N_ANALYSIS_REPORT.md`

---

## Profil UNB - verrouillage permanent

Le profil UNB est **définitivement verrouillé** sur `ELM_STANDARD`.

- Émetteur : `4399901876613`
- Récepteur : `3015981600108`

Toute tentative de modification provoque `ForbiddenProfileError` au démarrage.
Ne pas modifier `lookups/unb_profiles.csv` ni la section `[edi]` de `config.ini`.
