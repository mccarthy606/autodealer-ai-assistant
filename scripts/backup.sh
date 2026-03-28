#!/usr/bin/env bash
# PostgreSQL daily backup script. Runs on the host machine via cron or 'make backup'.
# Writes compressed backups to BACKUP_DIR on the host.
# Schedule via: crontab -e -> 0 2 * * * POSTGRES_PASSWORD=secret /full/path/to/project/scripts/backup.sh
#
# Required environment variables:
#   POSTGRES_PASSWORD   — postgres password for pg_dump auth (no default — must be set explicitly)
#
# Optional environment variables:
#   BACKUP_DIR          — destination directory (default: <project-root>/backups)
#   POSTGRES_CONTAINER  — docker container name (default: autodealer-ai-assistant-postgres-1)
#   POSTGRES_USER       — postgres user (default: postgres)
#   POSTGRES_DB         — database name (default: autodealer)

set -euo pipefail

# Fail loudly if POSTGRES_PASSWORD is unset or empty — no silent default
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set (no default to avoid silent misconfiguration)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/../backups}"
DATE=$(date +%Y-%m-%d)
FILENAME="autodealer_${DATE}.sql.gz"
CONTAINER="${POSTGRES_CONTAINER:-autodealer-ai-assistant-postgres-1}"

mkdir -p "${BACKUP_DIR}"

echo "Starting backup: ${FILENAME}"

# Write to a temp file first; only move into place on success to avoid zero-byte
# backup files if pg_dump or gzip fails mid-stream.
TMPFILE=$(mktemp "${BACKUP_DIR}/.tmp_backup_XXXXXX")
trap 'rm -f "${TMPFILE}"' EXIT

docker exec \
  -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  "${CONTAINER}" \
  pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-autodealer}" \
  | gzip > "${TMPFILE}"

# Verify the gzip is valid before committing the file
gzip -t "${TMPFILE}" || { echo "ERROR: Backup integrity check failed — aborting"; exit 1; }

mv "${TMPFILE}" "${BACKUP_DIR}/${FILENAME}"
echo "Backup written: ${BACKUP_DIR}/${FILENAME}"

# Remove backups older than 7 days
find "${BACKUP_DIR}" -name "autodealer_*.sql.gz" -mtime +7 -delete
echo "Retention: removed backups older than 7 days"
