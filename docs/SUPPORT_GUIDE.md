# SUPPORT_GUIDE.md

## Daily Operational Checks

1. New files processed today (check `logs/edifact.log`)
2. Masterdata sync freshness on `/api/health/system` (`masterdata_sync.status` should be `fresh`)
3. Any files in `PDF_ERROR` that need review
4. SFTP delivery confirmations in `data/sftp_delivery_ledger.csv`
5. Duplicate detection count in `data/duplicate_ledger.csv`
6. `logs/edifact.log` does not show CRITICAL entries

## Common Error Codes and Resolution

| Error Code | Cause | Resolution |
|---|---|---|
| `PDF_EMPTY_TEXT` | PDF is image-only, no extractable text | Manual processing required |
| `ORDER_NUMBER_MISSING` | No order number found in PDF | Check PDF format |
| `UNKNOWN_MATERIAL` | Article not in master data or lookups | Add to fourre-tout lookup or escalate |
| `DISCONTINUED_MATERIAL` | MATNR in discontinued list | Inform customer to use new article |
| `ROH_NONCOMMERCIAL` | MATNR is ROH type | Cannot be ordered |
| `SOLDTO_LOW_CONFIDENCE` | Customer not matched | Verify customer in 10564_Customers.csv |
| `SHIPTO_WEAK_EVIDENCE` | Delivery address has no postal/city | Check PDF delivery section |
| `SFTP_UPLOAD_FAILED` | SFTP connection or authentication issue | Check SFTP credentials and host reachability |
| `DUPLICATE_ORDER` | Same order already submitted | Verify if order was received by ELM |

## Master Data Refresh

Production must sync from `https://github.boschdevcloud.com/RSR1DY/masterdata.git` daily.

Use the daily Databricks job command:

```
python scripts/sync_masterdata_repo.py \
	--repo-url https://github.boschdevcloud.com/RSR1DY/masterdata.git \
	--branch main \
	--target-dir /Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/ \
	--notify-api-url https://file2edi-5555213114570927.7.azure.databricksapps.com/api/masterdata/sync \
	--notify-api-key "$APP_API_KEY"
```

After sync, verify:

1. `/api/masterdata/stats` shows updated `sync_commit` and recent `sync_age_hours`
2. `/api/health/system` reports `masterdata_sync.status = fresh`
3. `.masterdata_sync_metadata.json` exists in runtime masterdata path

## SFTP Credential Rotation

1. Update `SFTP_PASSWORD` (or `SFTP_PRIVATE_KEY_PATH`) on host `DY1-C-0014E`
2. Run `python src/edifact_orders_engine.py --validate-only` to confirm SFTP config
3. Process a test PDF with `--dry-run` first

## Rollback Procedure

If the generator produces incorrect output:
1. Set `dry_run = true` in `config.ini` immediately
2. Notify ELM contact to hold processing of recent `.tst` files
3. Review `logs/edifact.log` for the affected batch
4. Fix the issue, run `python validate_project.py`
5. Re-enable `dry_run = false` after fix is confirmed

## n8n Analysis Report Refresh

Run at any time:
```
python src/edifact_orders_engine.py --analyse-n8n-only
```
Output: `docs/N8N_ANALYSIS_REPORT.md`

## UNB Profile Lock

The UNB profile is PERMANENTLY locked to `ELM_STANDARD`.

- Sender: `4399901876613`
- Receiver: `3015981600108`

Any attempt to change this will cause `ForbiddenProfileError` at startup.
Do not modify `lookups/unb_profiles.csv` or the `[edi]` section of `config.ini`.
