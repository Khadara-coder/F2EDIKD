# SUPPORT_GUIDE.md

## Daily Operational Checks

1. New files processed today (check `logs/edifact.log`)
2. Any files in `PDF_ERROR` that need review
3. SFTP delivery confirmations in `data/sftp_delivery_ledger.csv`
4. Duplicate detection count
5. `logs/edifact.log` does not show CRITICAL entries

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

When master data is updated in the `RSR1DY/masterdata` repository:
1. Sync files to `/Volumes/hcdap_prod/silver_hcfrdashlog/f2edi/masterdata/`
2. The engine picks them up on next run automatically
3. No restart required

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
