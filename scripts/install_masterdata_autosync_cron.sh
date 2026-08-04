#!/usr/bin/env bash
# Install a daily cron job that syncs RSR1DY/masterdata into File2EDI runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_URL="${MASTERDATA_REPO_URL:-https://github.boschdevcloud.com/RSR1DY/masterdata.git}"
BRANCH="${MASTERDATA_REPO_BRANCH:-main}"
TARGET_DIR="${MASTERDATA_RUNTIME_DIR:-$ROOT/data/masterdata}"
NOTIFY_URL="${MASTERDATA_NOTIFY_API_URL:-http://127.0.0.1:8080/api/masterdata/reload-cache}"
NOTIFY_KEY="${MASTERDATA_NOTIFY_API_KEY:-${APP_API_KEY:-}}"
CRON_HOUR="${MASTERDATA_AUTO_SYNC_HOUR:-2}"
CRON_MIN="${MASTERDATA_AUTO_SYNC_MINUTE:-15}"
LOG_FILE="${MASTERDATA_AUTO_SYNC_LOG:-/var/log/file2edi-masterdata-sync.log}"

MARKER="# File2EDI masterdata autosync"
CMD="cd \"$ROOT\" && python scripts/sync_masterdata_repo.py --repo-url \"$REPO_URL\" --branch \"$BRANCH\" --target-dir \"$TARGET_DIR\""
if [[ -n "$NOTIFY_URL" ]]; then
  CMD="$CMD --notify-api-url \"$NOTIFY_URL\""
fi
if [[ -n "$NOTIFY_KEY" ]]; then
  CMD="$CMD --notify-api-key \"$NOTIFY_KEY\""
fi
CMD="$CMD >> \"$LOG_FILE\" 2>&1"

LINE="$CRON_MIN $CRON_HOUR * * * $CMD $MARKER"

TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARKER" >"$TMP" || true
echo "$LINE" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "OK: cron installé ($CRON_MIN $CRON_HOUR * * *)"
echo "  target: $TARGET_DIR"
echo "  notify: $NOTIFY_URL"
echo "  log:    $LOG_FILE"
