---
# Phase 9: Production Deployment - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Production-ready deployment: Docker Compose prod profile (no --reload, multiple workers), Caddy TLS reverse proxy, Sentry error monitoring, daily PostgreSQL backups, deep health check endpoint, Alembic migrations separated from app startup, Celery Beat for follow-up automation (opt-in), and a Makefile for common ops.

</domain>

<decisions>
## Implementation Decisions

### Docker Compose (DEP-01)
- **D-01:** Create `docker-compose.prod.yml` alongside existing `docker-compose.yml`. Dev file unchanged — prod file has no mounted `src` volumes, no `--reload`, uses env_file `.env.prod`.
- **D-02:** Services in prod compose: `api`, `worker`, `beat`, `postgres`, `redis`, `caddy`. The `beat` service runs Celery Beat (`celery -A src.tasks.celery_app beat --loglevel=info`).
- **D-03:** `api` service in prod: `command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4`. No `--reload`. No src volume mount.
- **D-04:** Migration is NOT run in the api container command. It is a separate `migrate` service (or Makefile target). The `startup()` event migration code in `main.py` must be removed (DEP-06).
- **D-05:** Caddy service uses official `caddy:2-alpine` image, mounts `./Caddyfile:/etc/caddy/Caddyfile`, ports `80:80` and `443:443` and `443:443/udp`. No host port exposure for `api` (8000 not published externally — only Caddy reaches it).
- **D-06:** `beat` service only starts if `FOLLOWUPS_ENABLED=true` in the env. Since Docker Compose does not natively support conditional services, the beat service is always declared but `followups_enabled` is checked inside the task itself (already implemented in Phase 5). `.env.prod.example` sets `FOLLOWUPS_ENABLED=false` with a comment to enable once WhatsApp templates are Meta-approved.

### Caddy TLS (DEP-02)
- **D-07:** `Caddyfile` uses `yourdomain.com` as placeholder — operator replaces with real domain before first deploy.
- **D-08:** Caddy config: `yourdomain.com { reverse_proxy api:8000 }`. Caddy handles ACME/Let's Encrypt automatically. No manual cert management.
- **D-09:** HTTP→HTTPS redirect handled by Caddy automatically (Caddy default behavior).

### Sentry (DEP-03)
- **D-10:** Add `sentry-sdk[fastapi]` to `pyproject.toml` dependencies.
- **D-11:** Sentry init in `main.py` on startup: `sentry_sdk.init(dsn=settings.sentry_dsn, ...)` — only initializes if `settings.sentry_dsn` is non-empty (no-op when not configured).
- **D-12:** Add `sentry_dsn: str = ""` to `Settings` in `config.py`.
- **D-13:** `.env.prod.example` includes `SENTRY_DSN=` placeholder. Operator fills in DSN from their Sentry project.
- **D-14:** Include `environment`, `release` tags in Sentry init for context. `release` defaults to `"1.0.0"` (matches `main.py` version).

### PostgreSQL Backup (DEP-04)
- **D-15:** Backup stored in a local Docker volume `pg_backups` mounted at `/backups` inside a dedicated `backup` service (or cron-based approach). Chosen: local volume, zero cost, simple.
- **D-16:** Backup implementation: a `scripts/backup.sh` shell script that runs `pg_dump` and writes to `/backups/autodealer_YYYY-MM-DD.sql.gz`. Retention: delete files older than 7 days (`find /backups -mtime +7 -delete`).
- **D-17:** Backup triggered by a `backup` service in `docker-compose.prod.yml` that uses `postgres:16-alpine` image with `--entrypoint cron` and a crontab for daily 2:00 AM runs. Alternative: run backup from the host via `cron` + `docker exec`. **Chosen: host-side cron via `scripts/backup.sh` that calls `docker exec`** — simpler, no extra container, documented in Makefile.
- **D-18:** `make backup` runs the backup immediately. `make backup-list` shows existing files. Daily auto-backup via host cron (`crontab -e` entry documented in README section of CONTEXT).

### Health Check (DEP-05)
- **D-19:** Replace the trivial `/health` handler in `main.py` with a deep check: test DB (execute `SELECT 1`), test Redis (`redis_client.ping()`), test Celery (inspect active queues or use `celery.control.inspect().ping()` with a 1-second timeout).
- **D-20:** Response format:
  ```json
  {
    "status": "ok" | "degraded",
    "db": "ok" | "error",
    "redis": "ok" | "error",
    "celery": "ok" | "error"
  }
  ```
  Returns HTTP 200 if all ok, HTTP 503 if any component fails. `status` is `"degraded"` if any component is `"error"`.
- **D-21:** Celery check is best-effort with a 1-second timeout — if it times out, mark `"celery": "timeout"` and still return 200 (Celery workers may not always be reachable from the API process without blocking).

### Alembic Migration Separation (DEP-06)
- **D-22:** Remove the alembic migration block from `startup()` in `main.py`. The `startup()` function only creates the default dealership if absent — it no longer runs `alembic upgrade head`.
- **D-23:** `docker-compose.prod.yml` includes a one-shot `migrate` service: `command: alembic upgrade head`, `restart: "no"`, depends on postgres healthy. The `api` service depends on `migrate` completing successfully (`condition: service_completed_successfully`).
- **D-24:** `Makefile` targets:
  - `make migrate` — runs `docker compose -f docker-compose.prod.yml run --rm migrate`
  - `make deploy` — pulls latest, builds images, runs migrate, starts all services
  - `make logs` — tails `docker compose -f docker-compose.prod.yml logs -f`
  - `make backup` — runs `scripts/backup.sh`
  - `make stop` — `docker compose -f docker-compose.prod.yml down`

### .env.prod.example
- **D-25:** Create `.env.prod.example` documenting all required env vars for production. Keys: `DATABASE_URL`, `REDIS_URL`, `WHATSAPP_CLOUD_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_WEBHOOK_SECRET`, `ML_ACCESS_TOKEN`, `ML_USER_ID`, `LEMON_SQUEEZY_WEBHOOK_SECRET`, `ADMIN_PASSWORD_HASH`, `ALLOWED_ORIGINS`, `SENTRY_DSN`, `FOLLOWUPS_ENABLED=false`, `DEFAULT_DEALERSHIP_ID=1`.

### Claude's Discretion
- Exact Caddyfile syntax for TLS options (ACME email, etc.)
- Whether to use `asyncio` in the health check or keep it sync with a short timeout
- Exact pg_dump flags (--no-password, --format=custom vs plain SQL.gz)
- Makefile `.PHONY` declarations and error handling
- Whether to add a `HEALTHCHECK` instruction to the Dockerfile

</decisions>

<canonical_refs>
## Canonical References

### Existing Code
- `docker-compose.yml` — dev compose to keep unchanged; prod compose is additive
- `Dockerfile` — base image to reuse in prod; may add `HEALTHCHECK` directive
- `src/main.py` — startup() event (remove inline migration), /health route (replace with deep check), Sentry init
- `src/config.py` — add `sentry_dsn` setting
- `pyproject.toml` — add `sentry-sdk[fastapi]` dependency

### New Files
- `docker-compose.prod.yml` — prod services: api (4 workers), worker, beat, postgres, redis, caddy, migrate
- `Caddyfile` — Caddy reverse proxy config with yourdomain.com placeholder
- `Makefile` — migrate, deploy, logs, backup, stop targets
- `scripts/backup.sh` — pg_dump daily backup with 7-day retention
- `.env.prod.example` — all required env vars documented

</canonical_refs>

<code_context>
## Existing Code Insights

### main.py startup() — migration code to REMOVE:
```python
# REMOVE this block from startup():
try:
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied successfully")
except Exception as e:
    logger.warning("Could not run alembic migrations: %s", e)
# Keep: default dealership creation logic
```

### main.py /health — replace trivial handler:
```python
# Current (trivial):
@app.get("/health")
async def health():
    return {"status": "ok"}

# Replace with: deep check (DB + Redis + Celery)
```

### docker-compose.yml — current dev command (keep as-is):
```yaml
command: bash -c "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload"
```

### Existing Redis import pattern (for health check):
- `src/db/session.py` or `src/api/auth.py` — check how redis_client is instantiated; reuse same connection

</code_context>

<specifics>
## Specific Requirements

- DEP-01: docker-compose.prod.yml — no --reload, 4 workers
- DEP-02: Caddy — yourdomain.com placeholder, TLS automatic
- DEP-03: Sentry — SDK added, opt-in via SENTRY_DSN env var
- DEP-04: Backups — local volume, pg_dump daily, 7-day retention, host cron via scripts/backup.sh
- DEP-05: /health — deep check (DB + Redis + Celery), 503 on any failure
- DEP-06: Migrations — separate migrate service in docker-compose.prod.yml + Makefile target; remove from startup()
- Celery Beat — in prod compose, followups_enabled=false by default
- Makefile: migrate, deploy, logs, backup, stop targets

</specifics>

<deferred>
## Deferred Ideas

- S3/Backblaze backup upload — upgrade path when local backup is not enough
- CI/CD pipeline (GitHub Actions deploy) — v2
- Zero-downtime rolling deploys — v2
- Prometheus + Grafana metrics — v2
- Log aggregation (Loki, Datadog) — v2
- Docker Swarm / Kubernetes migration — v2
- Automatic SSL cert email notifications — v2

</deferred>

---

*Phase: 09-production-deployment*
*Context gathered: 2026-03-28*
