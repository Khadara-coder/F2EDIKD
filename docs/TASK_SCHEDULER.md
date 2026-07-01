# TASK_SCHEDULER.md

## Windows Task Scheduler - EDIFACT Orders Generator

### Task Name
`EDIFACT_Orders_Generator`

### Program/Script
```
\\dy00fs04.emea.bosch.com\Dy2_Sales$\Pole Data\EDIPUSHBOT\edifact_generator\EDIFACT_Orders_Generator.exe
```

### Start In
```
\\dy00fs04.emea.bosch.com\Dy2_Sales$\Pole Data\EDIPUSHBOT\edifact_generator
```

### Schedule
- Trigger: Every 5 minutes
- Start: 07:00 daily
- Stop after: 10 minutes (execution timeout)
- Run whether user is logged on or not: YES
- Run with highest privileges: YES
- Run only if network is available: YES
- If the task is already running: Do not start a new instance (Ignore)

### Setting the Task via install_task.ps1
Run `install_task.ps1` as Administrator to register the task automatically.

### Important Notes

1. The local `.tst` file in `outbox/local_generated` is NOT the final delivery.
2. The SFTP remote folder is the official submission point.
3. PDF_INBOX must be accessible from the Task Scheduler service account.
4. SFTP credentials must be set as system environment variables on the host.

### Environment Variables (set on host DY1-C-0014E)

```
SFTP_HOST=<your_sftp_host>
SFTP_USERNAME=<your_sftp_username>
SFTP_PASSWORD=<your_sftp_password>  (or use SFTP_PRIVATE_KEY_PATH)
SFTP_REMOTE_DIR=<remote_directory>
```

### Monitoring

- Check `logs/edifact.log` for processing results
- Check `data/sftp_delivery_ledger.csv` for SFTP status
- Check `data/duplicate_ledger.csv` for duplicate records
- Alert on files remaining in PDF_INBOX > 30 minutes after expected run time
