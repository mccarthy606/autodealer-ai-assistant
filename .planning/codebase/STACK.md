# Technology Stack

**Analysis Date:** 2026-03-27

## Languages

**Primary:**
- Python >=3.12 - All application code, backend services, tasks

**Secondary:**
- HTML/Jinja2 - Admin UI templates (`src/templates/`)
- CSS - Admin UI styles (`src/static/admin.css`)

## Runtime

**Environment:**
- Python 3.12 (Docker base: `python:3.12-slim`)
- PYTHONPATH=/app (set in Dockerfile)
- PYTHONUNBUFFERED=1

**Package Manager:**
- pip with setuptools>=68 + wheel
- Build backend: `setuptools.build_meta`
- Lockfile: Not present (no requirements.txt or pip-lock)
- Config: `pyproject.toml`

## Frameworks

**Core:**
- FastAPI >=0.109.0 - HTTP API framework, async
- Uvicorn[standard] >=0.27.0 - ASGI server (host 0.0.0.0, port 8000, reload in dev)
- Pydantic >=2.5.0 - Data validation
- Pydantic-Settings >=2.1.0 - Environment-based configuration (`src/config.py`)

**ORM/Database:**
- SQLAlchemy >=2.0.25 - ORM with both async and sync engines
- Alembic >=1.13.0 - Database migrations (`alembic/`, `alembic.ini`)
- asyncpg >=0.29.0 - Async PostgreSQL driver
- psycopg2-binary >=2.9.9 - Sync PostgreSQL driver (for Alembic and Celery tasks)

**Task Queue:**
- Celery[redis] >=5.3.0 - Background task processing
- Redis >=5.0.0 - Celery broker/backend + rate limiting

**Testing:**
- pytest >=7.4.0 - Test runner
- pytest-asyncio >=0.23.0 - Async test support (mode: `auto`)
- pytest-cov >=4.1.0 - Coverage (dev dependency)
- aiosqlite >=0.19.0 - SQLite async driver for test database

**Build/Dev:**
- Docker + Docker Compose - Container orchestration
- Make - Task runner (`Makefile`)

## Key Dependencies

**Critical:**
- `openai` >=1.10.0 - LLM integration via `AsyncOpenAI` client; uses function calling/tools (`src/services/llm_service.py`)
- `httpx` >=0.26.0 - Async HTTP client for all external API calls (WhatsApp, MercadoLibre, webhooks, Google Sheets)
- `sqlalchemy` >=2.0.25 - All data access, async sessions for FastAPI, sync sessions for Celery

**Infrastructure:**
- `redis` >=5.0.0 - Rate limiting (`src/api/rate_limit.py`) and Celery broker
- `celery[redis]` >=5.3.0 - Background inventory import from Google Sheets
- `alembic` >=1.13.0 - Schema migrations, auto-run on startup

**Communication:**
- `aiosmtplib` >=3.0.0 - Async email sending for manager handoff notifications (`src/services/notifications.py`)
- `python-multipart` >=0.0.6 - Form data parsing (WhatsApp webhook payloads)

**Templating:**
- `jinja2` >=3.1.0 - Server-side rendered admin UI (`src/templates/`)

**Config:**
- `python-dotenv` >=1.0.0 - .env file loading (via pydantic-settings)

## Database

**Primary: PostgreSQL 16**
- Image: `postgres:16-alpine`
- Database name: `autodealer`
- Connection: `postgresql://postgres:postgres@postgres:5432/autodealer`
- Async driver: asyncpg (SQLAlchemy async engine)
- Sync driver: psycopg2-binary (Alembic, Celery)
- JSONB columns used for: `photos`, `tags`, `state`, `raw`, `attachments`, `payload`
- Session management: `src/db/session.py`
- Models: `src/db/models.py`

**Migrations:**
- Tool: Alembic
- Config: `alembic.ini`
- Versions directory: `alembic/versions/`
- Current migrations:
  - `001_initial_schema.py`
  - `002_mvp_schema_extensions.py`
- Auto-run on app startup in `src/main.py`

**Cache/Broker: Redis 7**
- Image: `redis:7-alpine`
- Connection: `redis://redis:6379/0`
- Used for: Celery task broker/backend, rate limiting (sliding window per phone number)

## Configuration

**Environment:**
- Managed via Pydantic-Settings `BaseSettings` in `src/config.py`
- Loads from `.env` file (UTF-8 encoding)
- `.env.example` provided with all variables
- All integrations are optional with empty-string defaults (graceful degradation to mock mode)
- Key env vars: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `WHATSAPP_CLOUD_TOKEN`, `ML_ACCESS_TOKEN`, `ADMIN_PASSWORD`

**Build:**
- `pyproject.toml` - Package definition, dependencies, pytest config
- `Dockerfile` - Single-stage Python 3.12-slim build
- `docker-compose.yml` - 4 services (api, worker, postgres, redis)
- `Makefile` - Convenience commands (up, down, migrate, test, logs, shell)
- `alembic.ini` - Migration config

## Docker Architecture

**Services (docker-compose.yml):**

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| `api` | Custom (Dockerfile) | FastAPI app + Alembic migrations | 8000 |
| `worker` | Custom (Dockerfile) | Celery worker for background tasks | - |
| `postgres` | postgres:16-alpine | Primary database | 5432 |
| `redis` | redis:7-alpine | Task broker + cache | 6379 |

**Volumes:**
- `postgres_data` - Persistent PostgreSQL data
- `redis_data` - Persistent Redis data
- Dev mounts: `./src`, `./alembic`, `./tests` mounted into api container

**Startup order:**
1. postgres (with healthcheck: `pg_isready`)
2. redis
3. api (runs `alembic upgrade head` then `uvicorn`)
4. worker (runs `celery worker`)

## Platform Requirements

**Development:**
- Docker and Docker Compose
- Python 3.12+ (for local development without Docker)
- `make up` to start all services

**Production:**
- Docker-compatible hosting (any VPS, cloud VM, or container platform)
- PostgreSQL 16 database
- Redis 7 instance
- Port 8000 exposed for API/webhooks
- Publicly accessible URL for WhatsApp/MercadoLibre webhook registration

---

*Stack analysis: 2026-03-27*
