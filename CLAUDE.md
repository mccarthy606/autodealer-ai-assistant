<!-- GSD:project-start source:PROJECT.md -->
## Project

**AutoDealer AI Assistant**

SaaS WhatsApp-бот для автосалонов Аргентины. Автоматически общается с клиентами через WhatsApp: отвечает на вопросы об автомобилях, показывает фото и цены, создаёт лиды, записывает на визит и передаёт менеджеру когда нужно. Интегрирован с MercadoLibre для синхронизации инвентаря.

**Core Value:** Бот должен корректно обрабатывать входящие WhatsApp-сообщения клиентов автосалона и вовремя передавать горячие лиды менеджерам — это то, за что платят.

### Constraints

- **Stack**: Python 3.12 + FastAPI + SQLAlchemy 2.0 — не менять, всё уже написано
- **Market**: Аргентина only — es-AR, ARS, MercadoLibre
- **Timeline**: Клиент ждёт — нужен working product ASAP
- **Budget**: Один разработчик, минимальные затраты на инфраструктуру
- **Payments**: Lemon Squeezy для биллинга (monthly subscription)
- **WhatsApp**: Meta Business Cloud API (не Twilio)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python >=3.12 - All application code, backend services, tasks
- HTML/Jinja2 - Admin UI templates (`src/templates/`)
- CSS - Admin UI styles (`src/static/admin.css`)
## Runtime
- Python 3.12 (Docker base: `python:3.12-slim`)
- PYTHONPATH=/app (set in Dockerfile)
- PYTHONUNBUFFERED=1
- pip with setuptools>=68 + wheel
- Build backend: `setuptools.build_meta`
- Lockfile: Not present (no requirements.txt or pip-lock)
- Config: `pyproject.toml`
## Frameworks
- FastAPI >=0.109.0 - HTTP API framework, async
- Uvicorn[standard] >=0.27.0 - ASGI server (host 0.0.0.0, port 8000, reload in dev)
- Pydantic >=2.5.0 - Data validation
- Pydantic-Settings >=2.1.0 - Environment-based configuration (`src/config.py`)
- SQLAlchemy >=2.0.25 - ORM with both async and sync engines
- Alembic >=1.13.0 - Database migrations (`alembic/`, `alembic.ini`)
- asyncpg >=0.29.0 - Async PostgreSQL driver
- psycopg2-binary >=2.9.9 - Sync PostgreSQL driver (for Alembic and Celery tasks)
- Celery[redis] >=5.3.0 - Background task processing
- Redis >=5.0.0 - Celery broker/backend + rate limiting
- pytest >=7.4.0 - Test runner
- pytest-asyncio >=0.23.0 - Async test support (mode: `auto`)
- pytest-cov >=4.1.0 - Coverage (dev dependency)
- aiosqlite >=0.19.0 - SQLite async driver for test database
- Docker + Docker Compose - Container orchestration
- Make - Task runner (`Makefile`)
## Key Dependencies
- `openai` >=1.10.0 - LLM integration via `AsyncOpenAI` client; uses function calling/tools (`src/services/llm_service.py`)
- `httpx` >=0.26.0 - Async HTTP client for all external API calls (WhatsApp, MercadoLibre, webhooks, Google Sheets)
- `sqlalchemy` >=2.0.25 - All data access, async sessions for FastAPI, sync sessions for Celery
- `redis` >=5.0.0 - Rate limiting (`src/api/rate_limit.py`) and Celery broker
- `celery[redis]` >=5.3.0 - Background inventory import from Google Sheets
- `alembic` >=1.13.0 - Schema migrations, auto-run on startup
- `aiosmtplib` >=3.0.0 - Async email sending for manager handoff notifications (`src/services/notifications.py`)
- `python-multipart` >=0.0.6 - Form data parsing (WhatsApp webhook payloads)
- `jinja2` >=3.1.0 - Server-side rendered admin UI (`src/templates/`)
- `python-dotenv` >=1.0.0 - .env file loading (via pydantic-settings)
## Database
- Image: `postgres:16-alpine`
- Database name: `autodealer`
- Connection: `postgresql://postgres:postgres@postgres:5432/autodealer`
- Async driver: asyncpg (SQLAlchemy async engine)
- Sync driver: psycopg2-binary (Alembic, Celery)
- JSONB columns used for: `photos`, `tags`, `state`, `raw`, `attachments`, `payload`
- Session management: `src/db/session.py`
- Models: `src/db/models.py`
- Tool: Alembic
- Config: `alembic.ini`
- Versions directory: `alembic/versions/`
- Current migrations:
- Auto-run on app startup in `src/main.py`
- Image: `redis:7-alpine`
- Connection: `redis://redis:6379/0`
- Used for: Celery task broker/backend, rate limiting (sliding window per phone number)
## Configuration
- Managed via Pydantic-Settings `BaseSettings` in `src/config.py`
- Loads from `.env` file (UTF-8 encoding)
- `.env.example` provided with all variables
- All integrations are optional with empty-string defaults (graceful degradation to mock mode)
- Key env vars: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `WHATSAPP_CLOUD_TOKEN`, `ML_ACCESS_TOKEN`, `ADMIN_PASSWORD`
- `pyproject.toml` - Package definition, dependencies, pytest config
- `Dockerfile` - Single-stage Python 3.12-slim build
- `docker-compose.yml` - 4 services (api, worker, postgres, redis)
- `Makefile` - Convenience commands (up, down, migrate, test, logs, shell)
- `alembic.ini` - Migration config
## Docker Architecture
| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| `api` | Custom (Dockerfile) | FastAPI app + Alembic migrations | 8000 |
| `worker` | Custom (Dockerfile) | Celery worker for background tasks | - |
| `postgres` | postgres:16-alpine | Primary database | 5432 |
| `redis` | redis:7-alpine | Task broker + cache | 6379 |
- `postgres_data` - Persistent PostgreSQL data
- `redis_data` - Persistent Redis data
- Dev mounts: `./src`, `./alembic`, `./tests` mounted into api container
## Platform Requirements
- Docker and Docker Compose
- Python 3.12+ (for local development without Docker)
- `make up` to start all services
- Docker-compatible hosting (any VPS, cloud VM, or container platform)
- PostgreSQL 16 database
- Redis 7 instance
- Port 8000 exposed for API/webhooks
- Publicly accessible URL for WhatsApp/MercadoLibre webhook registration
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` for all Python modules: `conversation_engine.py`, `lead_service.py`, `rate_limit.py`
- Test files: `test_<module>.py` pattern: `test_engine.py`, `test_webhook.py`, `test_inventory.py`
- `__init__.py` in every package (most are empty or minimal)
- Use `snake_case` for all functions: `detect_intent()`, `extract_brand()`, `process_message()`
- Private/helper functions prefixed with underscore: `_get_or_create_conversation()`, `_car_to_dict()`, `_format_car_line()`
- Async functions use `async def` with no special naming prefix
- Use `snake_case`: `dealership_id`, `budget_max`, `car_summary`
- Constants use `UPPER_SNAKE_CASE`: `SEARCH_CAR`, `REASON_VISIT_SCHEDULING`, `GRAPH_API_URL`
- Private module-level variables prefixed with underscore: `_RESPONSES`, `_EN_STOPS`, `_redis`
- Use `PascalCase`: `InventoryService`, `WhatsAppCloudAdapter`, `EngineResult`
- Enums use `PascalCase` with `Enum` suffix: `ConditionEnum`, `StatusEnum`, `LeadIntentEnum`
- Enum members use `snake_case` string values: `zero_km`, `in_transit`, `handed_off`
- No Pydantic models for request/response schemas (uses raw dicts)
- Pydantic only for `Settings` config via `pydantic-settings`
- SQLAlchemy models use `PascalCase` class names with plural `snake_case` table names: `class Lead` -> `__tablename__ = "leads"`
## Code Style
- No `.prettierrc`, `.editorconfig`, `black.toml`, or `ruff.toml` detected
- No autoformatter is configured; follow the existing style manually
- Use 4-space indentation (Python standard)
- Strings: prefer double quotes `"` for all strings
- No `.flake8`, `pylintrc`, `ruff.toml`, or `mypy.ini` detected
- No linter is enforced; follow PEP 8 conventions by inspection
## Import Organization
- Use explicit named imports, not wildcard (except `conftest.py` which uses `from src.db.models import *`)
- Group related imports on one line when reasonable:
- Trailing commas in multi-line import tuples
- No path aliases configured
- All imports use relative package paths from `src`: `from src.services.intent import detect_intent`
- No `__init__.py` re-exports; import directly from the source module
## Error Handling
- Broad `except Exception` with logging, never bare `except:`
- Pattern: try/except -> log warning -> return graceful fallback
- Database race conditions handled with rollback + retry in `src/services/conversation_engine.py`:
- API dependency `get_db()` in `src/api/deps.py` uses try/except/finally for commit/rollback/close
- Enum parsing uses try/except ValueError with `pass` to silently skip invalid values (`src/services/inventory.py`)
- No custom exception classes exist; all errors use built-in exceptions
## Logging
- `logger.info()` for business events: handoffs, lead creation, startup, mock API calls
- `logger.warning()` for recoverable failures: failed emails, Redis connection, migration issues
- `logger.error()` for API/integration failures: WhatsApp API errors
- Use `%s` string formatting, not f-strings: `logger.info("Lead created: id=%s intent=%s", lead.id, intent)`
- `src/main.py`
- `src/services/conversation_engine.py`
- `src/services/lead_service.py`
- `src/services/notifications.py`
- `src/adapters/whatsapp_cloud.py`
- `src/api/routes/webhooks.py`
- `src/api/rate_limit.py`
## Comments
- Module-level docstrings on every `.py` file (triple-quoted, one-line):
- Section separator comments with `# --- Section Name ---` in longer files:
- Inline comments for business logic rules: `# H1: Explicit human`, `# Idempotency check`
- `# noqa` used sparingly: `from src.db.models import *  # noqa - import all models`
- Use triple-quoted strings for all public functions
- Brief one-line docstrings preferred:
- Multi-line docstrings for complex functions use imperative mood:
- No docstrings on private helper functions (underscore-prefixed)
## Type Annotations
- All function parameters and return types are annotated:
- Use `Optional[X]` from `typing` (not `X | None`), except for `dict | None` in newer code
- Use `list[dict]`, `dict[str, Any]`, `tuple[Optional[float], Optional[float]]` (Python 3.12 syntax)
- `AsyncGenerator` used for dependency injection: `async def get_db() -> AsyncGenerator[AsyncSession, None]`
- No `TypedDict` or `Protocol` usage; plain dicts used for data transfer
## Pydantic Model Patterns
- All settings have defaults (app works with zero env vars)
- Singleton instance: `settings = Settings()` at module level
- No Pydantic models for API request/response validation; raw dicts and SQLAlchemy models used instead
## Data Transfer Patterns
- `InventoryService.search()` returns `list[dict[str, Any]]`
- `EngineResult` is a plain class with `to_dict()` method (not a Pydantic model)
- `_car_to_dict()` converts SQLAlchemy model to dict manually
- Conversation state stored as `dict` in JSONB column
## Module Design
## Multilingual Patterns
- Language detected per-message via `detect_language()` in `src/services/entities.py`
- Response templates keyed by `(intent, language)` tuples in `src/services/responder.py`
- Use `lang.startswith("es")` to check Spanish (handles `es-AR`, `es`, etc.)
- Default language is Spanish (`es-AR`)
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## High-Level Pattern
```
```
## Request Flow
### WhatsApp Webhook Flow
```
```
### Admin Test Chat Flow
```
```
## Two Processing Paths
## Conversation State Machine
```
```
- `stage`: current FSM stage
- `language`: detected language (es/en)
- `name`: extracted customer name
- `preferred_time`: visit time preference
- `preferences`: {brand, model, year, budget_min, budget_max, condition}
- `last_results_ids`: IDs of last search results
- `selected_car_id`: currently focused car
- `unhelpful_count`: counter for auto-handoff (threshold: 2)
- Customer requests human agent
- Financing inquiry
- Trade-in inquiry
- Visit scheduling (after lead creation)
- Photos missing from inventory
- Bot unhelpful 2+ times
## Service Layer
| Service | Responsibility |
|---------|---------------|
| `conversation_engine.py` | State machine, main processing (17.9KB) |
| `orchestrator.py` | LLM-aware processing, debug mode |
| `intent.py` | Rule-based intent detection (regex patterns) |
| `entities.py` | Entity extraction (brand, model, year, budget, name, time) + language detection |
| `inventory.py` | `InventoryService.search()` — filtered DB queries |
| `responder.py` | Multilingual response templates (es/en) |
| `deterministic_responder.py` | Standalone rule-based responses (no state machine) |
| `lead_service.py` | Lead creation from conversation state |
| `handoff_rules.py` | Handoff condition checking |
| `llm_service.py` | OpenAI integration with tool calling |
| `notifications.py` | Manager notifications (webhook, SMTP) |
| `visit_confirmation.py` | Visit intent detection + response formatting |
## Database Schema
### Entity Relationships
```
```
### Key Models
- **Dealership** — tenant root; stores WhatsApp config, ML config, timezone, language
- **InventoryItem** — car listing; brand, model, year, price, km, condition, status, photos (JSONB), tags (JSONB)
- **Conversation** — per dealer+phone unique; state (JSONB), mode (bot/manager), handoff tracking
- **Message** — in/out messages with raw payload and attachments
- **Lead** — customer intent; links to conversation and last car viewed
- **Event** — audit log; type + payload (JSONB) for analytics
### Indexes
- `ix_inv_dealer_status` — inventory by dealership + status
- `ix_inv_dealer_brand_model` — inventory search
- `ix_inv_external_id` — unique external ID per dealership
- `ix_conv_dealer_phone` — unique conversation per dealer+phone
- `ix_events_dealer_type_created` — event queries
## Async Patterns
- **AsyncPG** driver via SQLAlchemy 2.0 async engine
- `async_sessionmaker` with `expire_on_commit=False`
- Dual engines: async (FastAPI) + sync (Alembic/Celery)
- `get_db()` dependency with auto commit/rollback
- Race condition handling in `_get_or_create_conversation()` (rollback + retry)
- Celery for background tasks (CSV import) — uses sync engine
## Entry Points
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
