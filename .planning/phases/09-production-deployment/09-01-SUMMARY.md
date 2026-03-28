---
phase: 09-production-deployment
plan: "01"
subsystem: infrastructure
tags: [docker, caddy, tls, backup, ops, makefile]
dependency_graph:
  requires: []
  provides: [docker-compose.prod.yml, Caddyfile, Makefile-prod-targets, scripts/backup.sh, .env.prod.example]
  affects: [deployment, ops-runbook]
tech_stack:
  added: [caddy:2-alpine]
  patterns: [service_completed_successfully, named-volumes, one-shot-migrate-service]
key_files:
  created:
    - docker-compose.prod.yml
    - Caddyfile
    - scripts/backup.sh
    - .env.prod.example
  modified:
    - Makefile
decisions:
  - "api service has no ports key — Caddy is the sole public entrypoint"
  - "migrate is a one-shot service (restart: no) with service_completed_successfully dependency"
  - "backup.sh runs on host via docker exec, writes to host BACKUP_DIR, 7-day retention"
  - "Makefile retains dev targets (up/down/test/shell/dev-migrate/dev-logs) and adds prod targets (migrate/deploy/logs/backup/stop)"
metrics:
  duration: "15 minutes"
  completed: "2026-03-27"
  tasks_completed: 2
  files_created: 5
---

# Phase 9 Plan 01: Production Infrastructure Files Summary

Production deployment infrastructure: docker-compose.prod.yml with 7 services (4-worker api behind Caddy TLS, one-shot migrate service, celery worker/beat, postgres, redis), Caddyfile with yourdomain.com placeholder, Makefile prod targets, pg_dump backup script with 7-day retention, and .env.prod.example documenting all 18 required env vars.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create docker-compose.prod.yml | 753423d | docker-compose.prod.yml |
| 2 | Create Caddyfile, Makefile, backup.sh, .env.prod.example | 1c16db4 | Caddyfile, Makefile, scripts/backup.sh, .env.prod.example |

## What Was Built

### docker-compose.prod.yml
Seven services with correct dependency chain:
- `migrate` service: `alembic upgrade head`, `restart: "no"`, depends on `postgres: service_healthy`
- `api` service: 4 uvicorn workers, no `--reload`, no src volume mount, depends on `migrate: service_completed_successfully`
- `worker` / `beat` services: celery, depend on postgres+redis
- `postgres`: named volumes `postgres_data` + `pg_backups:/backups`, healthcheck
- `redis`: named volume `redis_data`, no host port
- `caddy`: sole public entrypoint with ports 80/443/443-udp, mounts `./Caddyfile`
- Named volumes: `postgres_data`, `redis_data`, `pg_backups`, `caddy_data`, `caddy_config`

### Caddyfile
Minimal two-line config — `yourdomain.com { reverse_proxy api:8000 }`. Caddy handles ACME/Let's Encrypt and HTTP→HTTPS redirect automatically.

### Makefile
Retains existing dev targets (`up`, `down`, `test`, `shell`, `dev-migrate`, `dev-logs`). Adds prod targets using `COMPOSE=docker compose -f docker-compose.prod.yml`:
- `migrate` — runs one-shot migrate service
- `deploy` — pull/build/migrate/up all prod services
- `logs` — tail prod logs
- `backup` — runs `scripts/backup.sh`
- `backup-list` — lists existing backup files
- `stop` — `docker compose down` on prod stack

### scripts/backup.sh
Runs on host via `docker exec`. Uses `PGPASSWORD` env var for pg_dump auth. Pipes `pg_dump` output through `gzip` to `BACKUP_DIR` (defaults to `<project-root>/backups`). Removes backups older than 7 days via `find -mtime +7 -delete`. Fully configurable via env vars.

### .env.prod.example
18 env vars documented including `DATABASE_URL`, `REDIS_URL`, `POSTGRES_*`, WhatsApp API vars, `ML_ACCESS_TOKEN`, `ML_USER_ID`, `LEMON_SQUEEZY_WEBHOOK_SECRET`, `ADMIN_PASSWORD_HASH`, `OPENAI_API_KEY`, `ALLOWED_ORIGINS`, `SENTRY_DSN`, `FOLLOWUPS_ENABLED=false` (with comment about Meta template approval), `DEFAULT_DEALERSHIP_ID`.

## Deviations from Plan

### Makefile Extension Instead of Replacement
**Found during:** Task 2
**Issue:** Existing Makefile had dev targets (`migrate`, `logs`, `up`, `down`, `test`, `shell`) that would be lost if overwritten.
**Fix:** Preserved dev targets by renaming conflicting ones to `dev-migrate` and `dev-logs`; added prod targets with the exact names required by the plan (`migrate`, `deploy`, `logs`, `backup`, `stop`). All plan acceptance criteria pass.
**Files modified:** Makefile
**Rule:** Rule 2 (preserved existing functionality)

## Verification Results

All plan acceptance criteria passed:
- `service_completed_successfully` — 1 match in docker-compose.prod.yml (api depends on migrate)
- `workers 4` — confirmed in api command
- `caddy_data` — 2 matches (volume definition + caddy service mount)
- `pg_backups` — 2 matches (volume definition + postgres service mount)
- api service has NO `ports:` key — confirmed via YAML parse
- caddy service has ports `80:80`, `443:443`, `443:443/udp`
- `restart: "no"` — present on migrate service
- No `src:/app/src` volume mounts — confirmed
- YAML valid — python yaml.safe_load exits 0
- `docker-compose.yml` (dev) unchanged — `git diff` returns 0 lines

## Known Stubs

None — all files are complete production-ready configurations with no placeholder data except the intentional `yourdomain.com` placeholder in Caddyfile (documented in plan as required) and `CHANGE_ME` values in `.env.prod.example` (documentation file by design).

## Self-Check: PASSED

Files created:
- docker-compose.prod.yml — FOUND
- Caddyfile — FOUND
- Makefile — FOUND (modified)
- scripts/backup.sh — FOUND (executable)
- .env.prod.example — FOUND

Commits:
- 753423d — FOUND (feat(09-01): add production Docker Compose)
- 1c16db4 — FOUND (feat(09-01): add Caddyfile, Makefile prod targets)
