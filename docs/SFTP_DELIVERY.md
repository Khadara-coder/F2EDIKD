# SFTP_DELIVERY.md

## Overview

The EDIFACT Orders Generator submits all generated `.tst` files to a remote SFTP server. This is the **official final delivery** path. Local files are retained as archive copies only.

---

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SFTP_HOST` | Yes | SFTP server hostname or IP |
| `SFTP_USERNAME` | Yes | SFTP login username |
| `SFTP_PASSWORD` | If no key | SFTP password (never commit to code) |
| `SFTP_PRIVATE_KEY_PATH` | If no password | Path to RSA or Ed25519 private key file |
| `SFTP_PRIVATE_KEY_PASSPHRASE` | If key is encrypted | Passphrase for the private key |
| `SFTP_REMOTE_DIR` | Yes | Remote directory where `.tst` files are deposited |

Set these variables in your Windows environment or in a `.env` file (never commit to Git).

---

## Authentication Mode

Authentication priority:
1. If `SFTP_PRIVATE_KEY_PATH` is set: use private-key authentication (RSA or Ed25519)
2. If no private key: use password authentication (`SFTP_PASSWORD`)
3. Both must never appear in logs - they are masked

---

## Remote Directory Configuration

Set `SFTP_REMOTE_DIR` to the full remote path where Esker/ELM ingests EDIFACT files.

Example:
```
SFTP_REMOTE_DIR=/edi/orders/in
```

---

## Upload Temp/Rename Strategy

To avoid partial file reads by downstream systems:

1. File is uploaded as: `<filename>.uploading`
2. Once upload is complete, server-side rename to: `<filename>`
3. Remote file existence is verified via `stat()`
4. Only after verification: delivery status is marked `SFTP_SUBMITTED`
5. Only after `SFTP_SUBMITTED`: duplicate ledger is updated and PDF is archived

This guarantees atomicity: the final `.tst` file only appears when it is fully written.

---

## Retry Behavior

- `max_retries = 3` (configurable in `config.ini`)
- Exponential backoff: 2s, 4s between retries
- All retry attempts are logged
- If all retries fail: status = `SFTP_UPLOAD_FAILED`

---

## Verification Behavior

After rename, the generator calls `sftp.stat(remote_final_path)` to confirm the file exists.

If `stat()` fails:
- Status = `SFTP_UPLOAD_FAILED`
- PDF is routed to `PDF_ERROR`
- `.tst` is archived to `sftp_failed_archive`

---

## Failure Behavior

If SFTP fails after all retries:

| Action | Details |
|---|---|
| PDF routing | PDF moved to `PDF_ERROR` |
| TST archival | Local `.tst` copied to `sftp_failed_archive` |
| Ledger | Duplicate ledger NOT updated (order can be reprocessed) |
| Log | `SFTP_UPLOAD_FAILED` with full reason |
| Batch | Generator continues processing remaining PDFs |

---

## SFTP Delivery Ledger

Every upload attempt is recorded in `data/sftp_delivery_ledger.csv`:

```
submitted_at,tst_filename,local_path,remote_dir,remote_path,file_size,sha256,status,error_reason
```

Status values: `PENDING`, `UPLOADING`, `SFTP_SUBMITTED`, `SFTP_FAILED`

---

## Security Notes

- Never hardcode passwords or key contents in code or config
- `.env` must be in `.gitignore`
- Rotate SFTP credentials if they may have been exposed
- The generator never prints password or key content in any log
