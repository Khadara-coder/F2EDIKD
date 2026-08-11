# Guide de support opérationnel

## Contrôles quotidiens

1. Fichiers traités aujourd'hui → `logs/edifact.log` (ou `docker compose logs file2edi`)
2. Fraîcheur masterdata → `/api/health/system` : champ `masterdata_sync.status` doit être `fresh`
3. Fichiers en `PDF_ERROR` à traiter manuellement
4. Confirmations SFTP → `data/sftp_delivery_ledger.csv`
5. Doublons détectés → `data/duplicate_ledger.csv`
6. Aucune ligne `CRITICAL` dans `logs/edifact.log`
7. Qualité d'extraction → `python scripts/analyze_columns_quality.py`

---

## Qualité d'extraction - Cibles

| Colonne DB | Cible prod | Commande de vérification |
|---|---|---|
| `bosch_article` | 99%+ | `analyze_columns_quality.py` |
| `quantity` | 80%+ | `analyze_columns_quality.py` |
| `unit_price` | 90%+ | `analyze_columns_quality.py` |
| `amount` | 85%+ | `analyze_columns_quality.py` |
| `customer_reference` | 5%+ | Phase 1 |
| `payment_terms` | 10%+ | Phase 1 |
| `delivery_date` | 84%+ | Phase 2 |
| `special_instructions` | 5%+ | Phase 2 |

```bash
# Test qualité sur 50 PDFs aléatoires
docker compose exec api python scripts/test_random_pdfs.py \
  --source "RAG Purchase Orders" --n 50 --seed 42
```

---

## Migration de schéma (Phase 3)

Si les colonnes Phase 1+2 sont absentes après une mise à jour :

```bash
docker compose exec api python scripts/migrate_add_fields.py
docker compose exec api python scripts/backfill_new_fields.py
```

---

## Codes d'erreur courants

| Code | Cause | Résolution |
|---|---|---|
| `PDF_EMPTY_TEXT` | PDF image sans texte extractible | Traitement manuel requis |
| `PDF_ENCRYPTED` | PDF protégé par mot de passe non vide | Demander version non protégée |
| `ORDER_NUMBER_MISSING` | Numéro de commande absent du PDF | Vérifier le format PDF |
| `QUANTITY_MISSING` | Quantité non extraite | Vérifier les variantes : QTÉ/QTE/QTY/PCE |
| `UNKNOWN_MATERIAL` | Article absent des masterdata et lookups | Ajouter au lookup fourre-tout ou escalader |
| `DISCONTINUED_MATERIAL` | MATNR dans la liste discontinued | Informer le client d'utiliser le nouvel article |
| `ROH_NONCOMMERCIAL` | MATNR de type ROH | Non commandable |
| `SOLDTO_LOW_CONFIDENCE` | Client non matchée | Vérifier dans `10564_Customers.csv` |
| `SHIPTO_WEAK_EVIDENCE` | Adresse de livraison sans CP/ville | Vérifier la section livraison du PDF |
| `SFTP_UPLOAD_FAILED` | Problème connexion ou auth SFTP | Vérifier credentials et accessibilité hôte SFTP |
| `DUPLICATE_ORDER` | Commande déjà soumise | Vérifier si reçue par ELM |

---

## Refresh des données maîtres

Chaîne automatique recommandée :

```text
Job Databricks → repo Git RSR1DY/masterdata → sync quotidien File2EDI → cache mémoire
```

### Windows (local / poste de travail)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_masterdata_autosync_windows.ps1
Start-ScheduledTask -TaskName "File2EDI-Masterdata-AutoSync"
```

### Linux / VM Azure

```bash
bash scripts/install_masterdata_autosync_cron.sh
```

### Dans le process uvicorn (optionnel)

Dans `.env` :

```bash
MASTERDATA_AUTO_SYNC=true
MASTERDATA_AUTO_SYNC_INTERVAL_HOURS=24
MASTERDATA_REPO_URL=https://github.boschdevcloud.com/RSR1DY/masterdata.git
```

Prérequis : `git` authentifié vers Bosch DevCloud, et droits d'écriture sur `data/masterdata`.

Après sync, vérifier :
1. `/api/masterdata/stats` → `sync_commit` et `sync_age_hours` récents
2. `/api/health/system` → `masterdata_sync.status = fresh`

---

## Rotation des credentials SFTP

1. Mettre à jour `SFTP_PASSWORD` (ou `SFTP_PRIVATE_KEY_PATH`) dans `.env`
2. Redémarrer le service : `docker compose -f docker-compose.file2edi.yml restart file2edi`
3. Vérifier : `python src/edifact_orders_engine.py --validate-only`
4. Test dry-run : `python src/edifact_orders_engine.py --dry-run`

---

## Mise à jour du code (VM Azure / staging)

```bash
# Récupérer la dernière version de staging
git -C /root/GenieCommande pull origin staging

# Redémarrer sans perte de données (volumes persistants)
docker compose -f docker-compose.file2edi.yml up --build -d
```

---

## Procédure de rollback

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
