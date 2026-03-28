#!/usr/bin/env bash
# PostgreSQL daily backup script. Runs on the host machine via cron or 'make backup'.
# Writes compressed backups to BACKUP_DIR on the host.
# Schedule via: crontab -e -> 0 2 * * * /full/path/to/project/scripts/backup.sh
#
# Environment variables (optional overrides):
#   BACKUP_DIR          — destination directory (default: <project-root>/backups)
#   POSTGRES_CONTAINER  — docker container name (default: autodealer-ai-assistant-postgres-1)
#   POSTGRES_PASSWORD   — postgres password for pg_dump auth (default: postgres)
#   POSTGRES_USER       — postgres user (default: postgres)
#   POSTGRES_DB         — database name (default: autodealer)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/../backups}"
DATE=$(date +%Y-%m-%d)
FILENAME="autodealer_${DATE}.sql.gz"
CONTAINER="${POSTGRES_CONTAINER:-autodealer-ai-assistant-postgres-1}"

mkdir -p "${BACKUP_DIR}"

echo "Starting backup: ${FILENAME}"

docker exec \
  -e PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" \
  "${CONTAINER}" \
  pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-autodealer}" \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "Backup written: ${BACKUP_DIR}/${FILENAME}"

# Remove backups older than 7 days
find "${BACKUP_DIR}" -name "autodealer_*.sql.gz" -mtime +7 -delete
echo "Retention: removed backups older than 7 days"
