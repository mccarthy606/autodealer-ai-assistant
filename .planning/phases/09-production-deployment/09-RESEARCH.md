# Phase 9: Production Deployment - Research

**Researched:** 2026-03-27
**Domain:** Docker Compose production, Caddy TLS, Sentry, PostgreSQL backup, FastAPI health checks, Alembic migration separation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Docker Compose (DEP-01)**
- D-01: Create `docker-compose.prod.yml` alongside existing `docker-compose.yml`. Dev file unchanged — prod file has no mounted `src` volumes, no `--reload`, uses env_file `.env.prod`.
- D-02: Services in prod compose: `api`, `worker`, `beat`, `postgres`, `redis`, `caddy`. The `beat` service runs Celery Beat (`celery -A src.tasks.celery_app beat --loglevel=info`).
- D-03: `api` service in prod: `command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4`. No `--reload`. No src volume mount.
- D-04: Migration is NOT run in the api container command. It is a separate `migrate` service (or Makefile target). The `startup()` event migration code in `main.py` must be removed (DEP-06).
- D-05: Caddy service uses official `caddy:2-alpine` image, mounts `./Caddyfile:/etc/caddy/Caddyfile`, ports `80:80` and `443:443` and `443:443/udp`. No host port exposure for `api` (8000 not published externally — only Caddy reaches it).
- D-06: `beat` service always declared but `followups_enabled` is checked inside the task itself. `.env.prod.example` sets `FOLLOWUPS_ENABLED=false`.

**Caddy TLS (DEP-02)**
- D-07: `Caddyfile` uses `yourdomain.com` as placeholder.
- D-08: Caddy config: `yourdomain.com { reverse_proxy api:8000 }`. Caddy handles ACME/Let's Encrypt automatically.
- D-09: HTTP→HTTPS redirect handled by Caddy automatically.

**Sentry (DEP-03)**
- D-10: Add `sentry-sdk[fastapi]` to `pyproject.toml` dependencies.
- D-11: Sentry init in `main.py` on startup: only initializes if `settings.sentry_dsn` is non-empty.
- D-12: Add `sentry_dsn: str = ""` to `Settings` in `config.py`.
- D-13: `.env.prod.example` includes `SENTRY_DSN=` placeholder.
- D-14: Include `environment`, `release` tags in Sentry init. `release` defaults to `"1.0.0"`.

**PostgreSQL Backup (DEP-04)**
- D-15: Backup stored in a local Docker volume `pg_backups` mounted at `/backups`.
- D-16: Backup implementation: `scripts/backup.sh` that runs `pg_dump` and writes to `/backups/autodealer_YYYY-MM-DD.sql.gz`. Retention: delete files older than 7 days.
- D-17: Host-side cron via `scripts/backup.sh` that calls `docker exec` — no extra container.
- D-18: `make backup` runs the backup immediately. `make backup-list` shows existing files.

**Health Check (DEP-05)**
- D-19: Replace trivial `/health` with deep check: DB (`SELECT 1`), Redis (`ping()`), Celery (inspect ping with 1-second timeout).
- D-20: Response: `{"status": "ok"|"degraded", "db": "ok"|"error", "redis": "ok"|"error", "celery": "ok"|"error"}`. HTTP 200 if all ok, HTTP 503 if any component fails.
- D-21: Celery check is best-effort with 1-second timeout — if timeout, mark `"celery": "timeout"` and still return 200.

**Alembic Migration Separation (DEP-06)**
- D-22: Remove the alembic migration block from `startup()` in `main.py`. Keep only default dealership creation logic.
- D-23: `docker-compose.prod.yml` includes one-shot `migrate` service: `command: alembic upgrade head`, `restart: "no"`, depends on postgres healthy. The `api` service depends on `migrate` completing successfully (`condition: service_completed_successfully`).
- D-24: Makefile targets: `make migrate`, `make deploy`, `make logs`, `make backup`, `make stop`.

**env.prod.example**
- D-25: Keys: `DATABASE_URL`, `REDIS_URL`, `WHATSAPP_CLOUD_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_WEBHOOK_SECRET`, `ML_ACCESS_TOKEN`, `ML_USER_ID`, `LEMON_SQUEEZY_WEBHOOK_SECRET`, `ADMIN_PASSWORD_HASH`, `ALLOWED_ORIGINS`, `SENTRY_DSN`, `FOLLOWUPS_ENABLED=false`, `DEFAULT_DEALERSHIP_ID=1`.

### Claude's Discretion
- Exact Caddyfile syntax for TLS options (ACME email, etc.)
- Whether to use `asyncio` in the health check or keep it sync with a short timeout
- Exact pg_dump flags (--no-password, --format=custom vs plain SQL.gz)
- Makefile `.PHONY` declarations and error handling
- Whether to add a `HEALTHCHECK` instruction to the Dockerfile

### Deferred Ideas (OUT OF SCOPE)
- S3/Backblaze backup upload
- CI/CD pipeline (GitHub Actions deploy)
- Zero-downtime rolling deploys
- Prometheus + Grafana metrics
- Log aggregation (Loki, Datadog)
- Docker Swarm / Kubernetes migration
- Automatic SSL cert email notifications
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEP-01 | Docker Compose production profile (без --reload, с workers) | docker-compose.prod.yml structure, service_completed_successfully, migrate service pattern |
| DEP-02 | Caddy reverse proxy с автоматическим TLS | Caddyfile syntax verified, ACME auto, port 443/udp required |
| DEP-03 | Sentry для мониторинга ошибок | sentry-sdk 2.56.0, module-level init, FastAPI auto-integration |
| DEP-04 | PostgreSQL backup (pg_dump daily) | docker exec pg_dump pipe gzip pattern, 7-day retention via find -mtime |
| DEP-05 | Health check endpoint с проверкой зависимостей | redis.asyncio ping, SQLAlchemy text("SELECT 1"), Celery inspect with timeout |
| DEP-06 | Alembic миграции отдельно от app startup | Remove from startup(), one-shot migrate service, service_completed_successfully |
</phase_requirements>

---

## Summary

This phase wires together all production infrastructure concerns for the AutoDealer AI Assistant. The core work is creating `docker-compose.prod.yml` with a proper `migrate` → `api` dependency chain, replacing the trivial `/health` endpoint with a real dependency check, initializing Sentry at module level, and scripting daily PostgreSQL backups via host cron.

The most critical structural change is DEP-06: the current `main.py` runs Alembic inside `@app.on_event("startup")`. This is incompatible with a multi-worker Uvicorn deployment (4 workers would all race to run migrations). It must be removed and moved to a dedicated `migrate` service with `condition: service_completed_successfully`. Docker Compose has supported this condition natively since Compose v2.3+, which ships with Docker Desktop and modern Docker Engine installations.

The `@app.on_event("startup")` decorator is deprecated in recent FastAPI. The project currently uses it and it still works; the plan must preserve the existing decorator for the dealership seed logic (not forcibly migrate to `lifespan`), since that is a refactor outside this phase's scope. Sentry init should happen at module level, before `app = FastAPI(...)`, which is the canonical pattern per official docs.

**Primary recommendation:** Implement in dependency order — config/env changes first, then compose file, then code changes (Sentry init, startup() cleanup, /health replacement), then Caddyfile + scripts.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| caddy | 2-alpine (latest 2.x) | TLS-terminating reverse proxy | Automatic ACME/Let's Encrypt, zero-config HTTPS, Docker-friendly |
| sentry-sdk | 2.56.0 (latest) | Error monitoring + performance | Official Sentry Python SDK; auto-integrates with FastAPI |
| postgres | 16-alpine | Production database (same as dev) | Version parity with existing dev compose |
| redis | 7-alpine | Celery broker + cache (same as dev) | Version parity with existing dev compose |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sentry-sdk[fastapi] extra | Included in 2.56.0 | Installs FastApiIntegration + StarletteIntegration | Required for automatic request context in Sentry events |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Caddy 2-alpine | nginx + certbot | Caddy has zero-config ACME, nginx requires certbot cron or cert-manager |
| Host cron for backup | In-compose `backup` service with cron | Host cron is simpler, no extra container; backup service adds complexity for marginal gain |
| Plain SQL.gz via pipe | pg_dump --format=custom (.dump) | Custom format allows pg_restore parallelism; plain SQL.gz is simpler to inspect and restore manually; either works |

**Installation:**
```bash
# Python: add to pyproject.toml dependencies
sentry-sdk[fastapi]>=2.0.0

# Docker images pulled automatically via docker-compose.prod.yml
# caddy:2-alpine, postgres:16-alpine, redis:7-alpine
```

---

## Architecture Patterns

### Recommended Project Structure (new files this phase)

```
autodealer-ai-assistant/
├── docker-compose.prod.yml     # Production services
├── Caddyfile                   # Caddy reverse proxy config
├── Makefile                    # Updated with prod targets
├── .env.prod.example           # All prod env vars documented
├── scripts/
│   └── backup.sh               # pg_dump daily backup script
└── src/
    ├── config.py               # + sentry_dsn field
    └── main.py                 # - migration block, + Sentry init, + deep /health
```

**Note:** `scripts/` directory exists in the project root but is currently empty. `backup.sh` is the first file to be added there.

### Pattern 1: docker-compose.prod.yml Migrate → API dependency chain

**What:** A one-shot `migrate` service runs `alembic upgrade head` and exits 0. The `api` service waits for it via `condition: service_completed_successfully`. This prevents race conditions in multi-worker deployments.

**When to use:** Any time Alembic is separated from app startup in a Docker Compose setup.

**Example:**
```yaml
# Source: https://docs.docker.com/compose/how-tos/startup-order/
services:
  migrate:
    build: .
    command: alembic upgrade head
    restart: "no"
    env_file: .env.prod
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build: .
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_started
```

### Pattern 2: Caddy reverse proxy for Docker Compose

**What:** Caddy service proxies all external traffic to the `api` service on port 8000. Caddy uses the Docker service name `api` as the upstream hostname.

**When to use:** Any Docker Compose setup where you want automatic TLS without managing certificates.

```
# Source: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
# Caddyfile — replace yourdomain.com before first deploy

yourdomain.com {
    reverse_proxy api:8000
}
```

**Critical:** Port 443/udp must be exposed for HTTP/3 (QUIC). Caddy 2 advertises HTTP/3 by default. If your cloud provider blocks UDP 443, add `servers { protocols h1 h2 }` to disable HTTP/3.

### Pattern 3: Sentry init — module level, before app creation

**What:** `sentry_sdk.init()` must be called at module level in `main.py`, before `app = FastAPI(...)`. This ensures all request contexts are captured from the first request.

**When to use:** FastAPI + Sentry in any configuration.

```python
# Source: https://docs.sentry.io/platforms/python/integrations/fastapi/
import sentry_sdk
from src.config import settings

# Module-level init — BEFORE app = FastAPI(...)
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production",
        release="1.0.0",
        traces_sample_rate=0.1,  # 10% of transactions — adjust per load
        send_default_pii=False,   # GDPR: avoid sending user PII by default
    )

app = FastAPI(...)
```

**Key finding:** The `[fastapi]` extra installs `FastApiIntegration` and `StarletteIntegration` which are **auto-enabled** when `sentry_sdk.init()` is called and `fastapi` is installed. No explicit `integrations=[FastApiIntegration()]` parameter is needed unless customizing behavior.

**Timing:** Module-level init (not in `@app.on_event("startup")`) is the canonical approach. Initializing inside `startup()` is possible but can miss early import-time errors and causes issues with Sentry's ASGI middleware hub context.

### Pattern 4: Deep /health endpoint

**What:** Check all dependencies with timeouts. DB and Redis use async clients already present in the codebase. Celery uses `inspect().ping()` in a thread executor with a 1-second timeout.

```python
# Source: derived from project's existing redis.asyncio and sqlalchemy async patterns

import asyncio
from fastapi import Response
from sqlalchemy import text
from src.db.session import AsyncSessionLocal
from src.api.rate_limit import get_redis

@app.get("/health")
async def health(response: Response):
    result = {"status": "ok", "db": "ok", "redis": "ok", "celery": "ok"}

    # DB check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        result["db"] = "error"

    # Redis check
    try:
        r = await get_redis()
        if r:
            await r.ping()
        else:
            result["redis"] = "error"
    except Exception:
        result["redis"] = "error"

    # Celery check — run sync inspect in thread to avoid blocking
    try:
        from src.tasks.celery_app import app as celery_app
        def _celery_ping():
            insp = celery_app.control.inspect(timeout=1)
            return insp.ping()
        ping_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _celery_ping),
            timeout=1.5
        )
        if not ping_result:
            result["celery"] = "error"
    except asyncio.TimeoutError:
        result["celery"] = "timeout"
    except Exception:
        result["celery"] = "error"

    any_error = any(v in ("error",) for v in [result["db"], result["redis"], result["celery"]])
    if any_error:
        result["status"] = "degraded"
        response.status_code = 503

    return result
```

**Note on Celery timeout:** Per D-21, a Celery timeout returns `"celery": "timeout"` but the endpoint still returns HTTP 200. Only `"celery": "error"` triggers 503. The code above returns 503 only for `"error"` values, consistent with the decision.

### Pattern 5: pg_dump via docker exec

**What:** Host-side script calls `docker exec` to run `pg_dump` inside the running postgres container, pipes through gzip, writes to a local backup volume.

```bash
#!/bin/bash
# scripts/backup.sh
# Source: https://simplebackups.com/blog/docker-postgres-backup-restore-guide-with-examples

set -euo pipefail

BACKUP_DIR="/path/to/backups"   # Override from env or argument
DATE=$(date +%Y-%m-%d)
CONTAINER="autodealer-postgres-1"   # docker-compose.prod.yml service name

mkdir -p "$BACKUP_DIR"

docker exec -i "$CONTAINER" \
    pg_dump -U postgres autodealer \
    | gzip -9 > "$BACKUP_DIR/autodealer_${DATE}.sql.gz"

# 7-day retention
find "$BACKUP_DIR" -name "autodealer_*.sql.gz" -mtime +7 -delete

echo "Backup complete: autodealer_${DATE}.sql.gz"
```

**pg_dump flags:** Use plain text format piped to gzip (not `--format=custom`) per D-16. Add `PGPASSWORD` env var if the postgres container has a non-default password. In dev compose the password is `postgres` with no `.pgpass` needed.

### Anti-Patterns to Avoid

- **Running Alembic inside `@app.on_event("startup")` in production:** With `--workers 4`, all 4 Uvicorn workers call `startup()` concurrently on boot. Alembic uses a file-based lock (`alembic/versions/`) that is not concurrent-safe across processes. The `migrate` service exits before `api` starts, guaranteeing single-process migration.
- **Exposing port 8000 externally in prod compose:** Only Caddy should be externally reachable. Binding `0.0.0.0:8000:8000` in docker-compose.prod.yml would bypass Caddy TLS and expose unencrypted traffic.
- **Initializing Sentry inside `@app.on_event("startup")` with `on_event`:** Works for capturing request errors but misses import-time exceptions and has ASGI middleware context issues. Use module-level init.
- **Using `celery inspect` without a timeout in a health endpoint:** The `inspect()` call can hang indefinitely if workers are busy or unreachable. Always pass `timeout=1` to `inspect()` AND wrap in `asyncio.wait_for`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS certificate management | Custom certbot cron / openssl scripts | Caddy 2 automatic ACME | Caddy handles renewal, OCSP stapling, HTTP/3, and HTTP→HTTPS redirect automatically |
| Backup retention | Custom date-comparison logic | `find -mtime +7 -delete` | POSIX `find` handles it in one line; custom logic has off-by-one risks |
| Sentry request context | Manual `before_send` hooks | `sentry-sdk[fastapi]` auto-integration | FastApiIntegration + StarletteIntegration auto-capture request URL, method, user context |
| Celery async bridging in health check | Custom async Celery client | `asyncio.run_in_executor` + sync `inspect()` | Celery's `inspect` is synchronous by design; the executor pattern is the correct bridge |

**Key insight:** The entire TLS and certificate renewal problem is solved by using `caddy:2-alpine`. This eliminates a class of operational failure that plagues nginx+certbot setups (expired certs, renewal cron failures).

---

## Common Pitfalls

### Pitfall 1: `service_completed_successfully` requires Compose v2.3+
**What goes wrong:** On old Docker installations, `depends_on` with `condition: service_completed_successfully` silently falls back to no condition or raises a parse error.
**Why it happens:** This condition was added in Docker Compose v2.3 (released 2022).
**How to avoid:** Document minimum Docker Engine version in deployment notes. Modern Docker Desktop (2022+) includes Compose v2.3+. Test with `docker compose version`.
**Warning signs:** `api` starts before `migrate` exits, causing "relation does not exist" errors.

### Pitfall 2: Caddy container name vs service name for upstream
**What goes wrong:** Writing `reverse_proxy localhost:8000` in Caddyfile instead of `reverse_proxy api:8000`.
**Why it happens:** In Docker Compose, service-to-service communication uses the service name as hostname. `localhost` inside the Caddy container does not resolve to the `api` container.
**How to avoid:** Always use the Docker Compose service name: `reverse_proxy api:8000`.
**Warning signs:** Caddy logs show "connection refused" or "no such host" to localhost:8000.

### Pitfall 3: Caddy UDP port 443 not exposed
**What goes wrong:** HTTP/3 (QUIC) fails if `443/udp` is not mapped. Some cloud firewalls block UDP 443 even when TCP 443 is open.
**Why it happens:** Caddy 2 advertises HTTP/3 in response headers by default. Browsers attempt QUIC upgrade and fail silently, falling back to TCP — but this causes latency.
**How to avoid:** Map `443:443/udp` in docker-compose.prod.yml (already in D-05). If cloud provider blocks UDP 443, add `servers { protocols h1 h2 }` to Caddyfile to disable HTTP/3.
**Warning signs:** Browser console shows QUIC errors; Caddy logs show "failed to serve HTTP/3".

### Pitfall 4: Celery Beat duplicate tasks on restart
**What goes wrong:** If Celery Beat's `celerybeat-schedule` file (persistent schedule state) is not in a volume, it is recreated on every restart, potentially re-triggering overdue tasks.
**Why it happens:** By default, Beat stores schedule state in a local `celerybeat-schedule` file. When the container restarts without a persistent volume, Beat thinks all schedules are overdue.
**How to avoid:** Either (a) mount a volume for Beat's schedule file, or (b) use the database scheduler (`django-celery-beat` or equivalent). For this project, since `followups_enabled=false` by default, this is low-urgency for v1. Document in `.env.prod.example`.
**Warning signs:** After restart, a burst of follow-up messages sent that should not have been.

### Pitfall 5: `scripts/backup.sh` container name assumption
**What goes wrong:** The script hardcodes the Postgres container name (e.g., `autodealer-postgres-1`), which depends on the directory name where docker-compose runs. If the repo directory is renamed, the container name changes.
**Why it happens:** Docker Compose names containers as `{project_name}_{service_name}_{index}`, where `project_name` defaults to the directory name.
**How to avoid:** Use `docker compose -f docker-compose.prod.yml exec -T postgres` instead of `docker exec {hardcoded_name}`. Or parameterize the container name via `COMPOSE_PROJECT_NAME` env var. Alternatively, use `--project-name autodealer` flag for predictable naming.
**Warning signs:** `Error: No such container: autodealer-postgres-1`.

### Pitfall 6: sentry_dsn empty-string check
**What goes wrong:** `sentry_sdk.init(dsn="")` does not raise an error but initializes Sentry in a no-op "offline" mode that still consumes resources and logs warnings.
**Why it happens:** `sentry_sdk.init()` accepts an empty DSN for local dev compatibility, but it's not a clean no-op.
**How to avoid:** Guard with `if settings.sentry_dsn:` before calling `init()`. This is already in D-11.
**Warning signs:** Sentry SDK logs "DSN is empty, not sending events" in production logs.

---

## Code Examples

### docker-compose.prod.yml skeleton

```yaml
# Source: https://docs.docker.com/compose/how-tos/startup-order/
# Source: D-01 through D-06 from 09-CONTEXT.md

services:
  migrate:
    build: .
    command: alembic upgrade head
    restart: "no"
    env_file: .env.prod
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build: .
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_started

  worker:
    build: .
    command: celery -A src.tasks.celery_app worker --loglevel=info
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  beat:
    build: .
    command: celery -A src.tasks.celery_app beat --loglevel=info
    restart: unless-stopped
    env_file: .env.prod
    depends_on:
      redis:
        condition: service_started

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api

  postgres:
    image: postgres:16-alpine
    env_file: .env.prod
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - pg_backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
  caddy_data:      # Caddy stores TLS certs here — MUST be a named volume
  caddy_config:
  pg_backups:
```

**Critical:** `caddy_data` must be a named volume, not a bind mount. Caddy stores ACME certificates and account keys here. If this volume is lost, Caddy re-requests certificates and may hit Let's Encrypt rate limits (5 certs per domain per week).

### Caddyfile

```
# Source: https://caddyserver.com/docs/quick-starts/reverse-proxy
# Replace yourdomain.com before first deploy

yourdomain.com {
    reverse_proxy api:8000
}
```

Caddy automatically:
- Obtains and renews a Let's Encrypt certificate for `yourdomain.com`
- Redirects HTTP (port 80) to HTTPS
- Advertises HTTP/3 (QUIC) on port 443

Optional ACME email (for expiry notifications — not required for cert issuance):
```
{
    email admin@yourdomain.com
}

yourdomain.com {
    reverse_proxy api:8000
}
```

### config.py addition

```python
# Add to Settings class in src/config.py
sentry_dsn: str = ""
```

### main.py Sentry init + startup() cleanup

```python
# Source: https://docs.sentry.io/platforms/python/integrations/fastapi/
# Place BEFORE app = FastAPI(...)

import sentry_sdk
from src.config import settings

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production",
        release="1.0.0",
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

app = FastAPI(
    title="AutoDealer AI Assistant",
    ...
)
```

```python
# startup() — KEEP only dealership seed, REMOVE migration block
@app.on_event("startup")
async def startup():
    """Ensure default dealership exists."""
    from sqlalchemy import select
    from src.db.session import AsyncSessionLocal
    from src.db.models import Dealership

    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Dealership).where(Dealership.id == settings.default_dealership_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                d = Dealership(
                    name="Mi Concesionario",
                    address="Av. Libertador 1234, CABA",
                    business_hours="Lun-Vie 9-18, Sab 9-13",
                    timezone="America/Argentina/Buenos_Aires",
                    default_language="es-AR",
                )
                session.add(d)
                await session.commit()
                logger.info("Created default dealership id=%s", settings.default_dealership_id)
        except Exception as e:
            logger.warning("Startup: %s", e)
```

### scripts/backup.sh

```bash
#!/bin/bash
# Source: https://simplebackups.com/blog/docker-postgres-backup-restore-guide-with-examples
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y-%m-%d)
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-autodealer}"

# Use compose exec to avoid hardcoding container name
docker compose -f "$(dirname "$0")/../docker-compose.prod.yml" \
    exec -T postgres \
    pg_dump -U "$PGUSER" "$PGDATABASE" \
    | gzip -9 > "$BACKUP_DIR/autodealer_${DATE}.sql.gz"

# 7-day retention
find "$BACKUP_DIR" -name "autodealer_*.sql.gz" -mtime +7 -delete

echo "Backup complete: $BACKUP_DIR/autodealer_${DATE}.sql.gz"
```

### Makefile prod targets

```makefile
.PHONY: up down migrate deploy logs backup backup-list stop test shell

# --- Dev targets (existing) ---
up:
	docker compose up -d

down:
	docker compose down

test:
	docker compose run --rm api pytest tests/ -v

shell:
	docker compose run --rm api python -c "from src.db.session import sync_engine; from src.db.models import *; print('OK')"

# --- Prod targets (new) ---
migrate:
	docker compose -f docker-compose.prod.yml run --rm migrate

deploy:
	docker compose -f docker-compose.prod.yml pull || true
	docker compose -f docker-compose.prod.yml build
	docker compose -f docker-compose.prod.yml run --rm migrate
	docker compose -f docker-compose.prod.yml up -d --remove-orphans

logs:
	docker compose -f docker-compose.prod.yml logs -f

stop:
	docker compose -f docker-compose.prod.yml down

backup:
	bash scripts/backup.sh

backup-list:
	docker compose -f docker-compose.prod.yml exec postgres \
		find /backups -name "*.sql.gz" -ls
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `@asynccontextmanager lifespan` | FastAPI 0.95.0 (2023) | `on_event` still works but deprecated; no forced migration in this phase |
| nginx + certbot for TLS | Caddy 2 automatic ACME | Caddy 2.0 (2020), mainstream by 2022 | Zero-config TLS; no cron, no renewal scripts |
| Sentry explicit `StarletteIntegration` + `FastApiIntegration` in `integrations=[]` | Auto-detected from installed packages | sentry-sdk 1.x → 2.x | No explicit integration list needed unless customizing |
| `sentry-sdk[fastapi]` extra | Still recommended for explicit dep declaration | Current | Ensures FastAPI integration deps are present in the lockfile |

**Deprecated/outdated:**
- `@app.on_event("startup")`: Deprecated in FastAPI 0.95.0. Project uses it throughout; removing it is a separate refactor. Keep it for this phase.
- `aioredis` standalone package: The project uses `redis>=5.0.0` with `import redis.asyncio as redis` (confirmed in `src/api/rate_limit.py`). Do NOT use the old `aioredis` package — it was merged into `redis-py` in v4.2.0.

---

## Codebase Findings (answering research questions)

### Q4: What Redis client is currently in use?
`redis.asyncio` from the `redis>=5.0.0` package (redis-py with async support). Import pattern in `src/api/rate_limit.py`:
```python
import redis.asyncio as redis
_redis: Optional[redis.Redis] = None
```
The `get_redis()` function is the project's standard accessor for the Redis client. The `/health` endpoint should call `get_redis()` and then `await r.ping()` — consistent with existing patterns.

### Q8: Does a `scripts/` directory already exist?
Yes — `scripts/` exists at the project root but is currently empty. `backup.sh` is the first file to be added.

### Q1: migrate service depends_on structure
Confirmed: Docker Compose `service_completed_successfully` is the correct condition. The `migrate` service must exit with code 0 (which `alembic upgrade head` does on success). The `api` service sets `condition: service_completed_successfully` under `depends_on.migrate`.

### Q5: Safe Celery health check approach
The `celery.control.inspect(timeout=1).ping()` call is synchronous. It must run in a thread executor inside the async `/health` handler. Wrap with `asyncio.wait_for(..., timeout=1.5)` to enforce an outer deadline. Return `"celery": "timeout"` (not an error) per D-21.

---

## Environment Availability

> This phase creates infrastructure configuration files. No new external tools need to be installed on the development machine. The Docker images (caddy:2-alpine, postgres:16-alpine, redis:7-alpine) are pulled at deploy time on the production server.

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker + Compose v2.3+ | docker-compose.prod.yml | Assumed present (dev uses it) | Unknown on prod server | — |
| bash | scripts/backup.sh | Standard on Linux hosts | — | — |
| gzip | scripts/backup.sh | Standard on Linux hosts | — | — |
| sentry-sdk[fastapi] | Sentry init in main.py | Not yet installed | Will be 2.56.0 | No monitoring (acceptable; opt-in via DSN) |

**Missing dependencies with no fallback:**
- Production server must have Docker Engine with Compose v2.3+. Verify with `docker compose version` before first deploy.

**Missing dependencies with fallback:**
- `sentry-sdk[fastapi]` not yet in pyproject.toml — must be added. If DSN is empty, Sentry is a no-op; app functions without it.

---

## Open Questions

1. **Celery Beat schedule persistence**
   - What we know: Beat stores schedule in `celerybeat-schedule` file in the working directory
   - What's unclear: Whether the Beat service needs a volume mount to persist schedule state across restarts
   - Recommendation: For v1 with `FOLLOWUPS_ENABLED=false` by default, omit the volume. Document in `.env.prod.example` that enabling follow-ups may require a Beat schedule volume.

2. **Production Postgres password**
   - What we know: Dev compose uses plaintext `POSTGRES_PASSWORD: postgres` hardcoded
   - What's unclear: Whether the prod `.env.prod` will use a different password and how `backup.sh` should authenticate
   - Recommendation: `backup.sh` should pass `PGPASSWORD` from environment: `docker compose exec -T postgres env PGPASSWORD="$DB_PASS" pg_dump ...`. Or simpler: since we're running inside the container as the `postgres` user, peer auth applies and no password is needed. The `docker compose exec postgres pg_dump -U postgres` pattern works without a password when running as the postgres OS user inside the container.

3. **`@app.on_event("startup")` deprecation**
   - What we know: FastAPI 0.95.0 deprecated `on_event` in favor of `lifespan`
   - What's unclear: Whether this phase should migrate to `lifespan` while touching `main.py` anyway
   - Recommendation: Out of scope per decisions. Keep `@app.on_event("startup")` — it still works. Migrate to `lifespan` in a future refactor phase.

---

## Sources

### Primary (HIGH confidence)
- [Sentry FastAPI Docs](https://docs.sentry.io/platforms/python/integrations/fastapi/) — init pattern, auto-integration, package requirements
- [Caddy Reverse Proxy Docs](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) — Caddyfile syntax, automatic HTTPS behavior
- [Docker Compose Startup Order](https://docs.docker.com/compose/how-tos/startup-order/) — `service_completed_successfully` condition
- `src/api/rate_limit.py` (project codebase) — confirmed `redis.asyncio` client pattern
- `pip index versions sentry-sdk` — confirmed current version 2.56.0

### Secondary (MEDIUM confidence)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — on_event deprecation status
- [SimpleBackups pg_dump Docker Guide](https://simplebackups.com/blog/docker-postgres-backup-restore-guide-with-examples) — `docker exec pg_dump | gzip` pattern
- [Caddy Quick Start](https://caddyserver.com/docs/quick-starts/reverse-proxy) — minimal Caddyfile example

### Tertiary (LOW confidence — flagged for validation)
- WebSearch results on Celery inspect timeout behavior — multiple sources agree on `timeout` parameter; not verified against official Celery docs directly

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified via pip, Docker images are the same as dev compose
- Architecture: HIGH — patterns verified against official Docker Compose and Caddy docs
- Pitfalls: HIGH for Caddy/compose patterns (verified); MEDIUM for Celery timeout behavior (multiple sources, not direct official docs)

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (stable tooling; Caddy and sentry-sdk patch releases should not break these patterns)
