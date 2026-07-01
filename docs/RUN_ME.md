# RUN_ME.md

## Quick Start

### 1. Install Dependencies
```
pip install -r requirements.txt
```

### 2. Set SFTP Credentials (environment variables)
```
set SFTP_HOST=your_sftp_host
set SFTP_USERNAME=your_username
set SFTP_PASSWORD=your_password
set SFTP_REMOTE_DIR=/remote/edi/in
```

### 3. Validate Project
```
python validate_project.py
```

### 4. Analyse n8n Project
```
python src/edifact_orders_engine.py --analyse-n8n-only
```

### 5. Dry Run (no SFTP, no PDF moves)
```
python src/edifact_orders_engine.py --dry-run
```

### 6. Process a Single PDF
```
python src/edifact_orders_engine.py --single-pdf "path\to\order.pdf"
```

### 7. Full Production Run
```
python src/edifact_orders_engine.py
```

### 8. Run Tests
```
python -m pytest tests\ -v
```

### 9. Build Executable
```
build_exe.bat
```

### 10. Install Windows Task Scheduler Task
```
powershell -ExecutionPolicy Bypass -File install_task.ps1
```

---

## CLI Reference

| Flag | Description |
|---|---|
| `--config path` | Use custom config.ini |
| `--analyse-n8n-only` | Generate n8n analysis report and exit |
| `--validate-only` | Validate config, master data, SFTP. Exit. |
| `--dry-run` | Build EDIFACT but do NOT upload to SFTP |
| `--single-pdf path` | Process one specific PDF |
| `--skip-sftp` | Skip SFTP (local dev only, never production) |
| `--log-level DEBUG` | Verbose logging |

---

## UNB Profile Lock

The UNB profile is permanently locked to ELM_STANDARD.
Any other profile causes `ForbiddenProfileError` at startup.

```
UNB+UNOC:3+4399901876613+3015981600108+<YYMMDD>:<HHMM>+<ControlRef>'
```
