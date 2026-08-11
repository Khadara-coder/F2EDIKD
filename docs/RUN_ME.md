# RUN_ME - Référence CLI moteur batch

Ce document couvre l'exécution du **moteur Python batch** (`src/edifact_orders_engine.py`).
Pour lancer l'application web complète, voir [FILE2EDI_DEPLOYMENT.md](FILE2EDI_DEPLOYMENT.md).

---

## Démarrage rapide (Docker Compose)

```bash
docker compose -f docker-compose.file2edi.yml up --build -d
# UI  : http://localhost:8080
# API : http://localhost:8080/api/health/system
```

---

## Moteur batch - étapes manuelles

### 1. Installer les dépendances

```bash
pip install -r requirements.txt -r requirements-postgres.txt
```

### 2. Configurer les variables SFTP

```bash
export SFTP_HOST=your_sftp_host
export SFTP_USERNAME=your_username
export SFTP_PASSWORD=your_password
export SFTP_REMOTE_DIR=/remote/edi/in
```

Ou via `.env` (copier `.env.example` → `.env`).

### 3. Valider le projet

```bash
python validate_project.py
```

### 4. Analyser le projet n8n (optionnel)

```bash
python src/edifact_orders_engine.py --analyse-n8n-only
```

Génère `docs/N8N_ANALYSIS_REPORT.md`.

### 5. Dry run (pas de SFTP, pas de déplacement PDF)

```bash
python src/edifact_orders_engine.py --dry-run
```

### 6. Traiter un seul PDF

```bash
python src/edifact_orders_engine.py --single-pdf "chemin/vers/commande.pdf"
```

### 7. Run complet production

```bash
python src/edifact_orders_engine.py
```

### 8. Tests

```bash
python -m pytest tests/ -v
```

---

## Référence des flags CLI

| Flag | Description |
|---|---|
| `--config path` | Utiliser un config.ini alternatif |
| `--analyse-n8n-only` | Générer le rapport d'analyse n8n et quitter |
| `--validate-only` | Valider config, masterdata, SFTP puis quitter |
| `--dry-run` | Construire l'EDIFACT sans uploader en SFTP |
| `--single-pdf path` | Traiter un seul PDF spécifique |
| `--skip-sftp` | Ignorer le SFTP (dev local uniquement, jamais en prod) |
| `--log-level DEBUG` | Logs verbeux |

---

## Profil UNB verrouillé

Le profil UNB est définitivement verrouillé sur `ELM_STANDARD`.
Tout autre profil déclenche `ForbiddenProfileError` au démarrage.

```
UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'
```
