# Concerns & Risks

## Technical Debt

1. **Two parallel conversation processors** — `conversation_engine.py` and `orchestrator.py` both handle conversations with different logic. Easy to diverge. Should consolidate into one path.

2. **admin_ui.py is 32KB** — Massive single file with HTML templates, route handlers, and business logic mixed together. Should split into smaller modules.

3. **Hardcoded dealership ID** — `settings.default_dealership_id` used everywhere in webhooks. No multi-tenant routing from the webhook payload itself.

4. **TODO in admin_ui.py:520** — `# TODO: Send via channel adapter (WhatsApp/ML) if configured` — admin chat doesn't actually send to WhatsApp.

5. **`datetime.utcnow()` usage** — Deprecated in Python 3.12+. Should use `datetime.now(UTC)`.

6. **Wildcard import** — `src/db/__init__.py` uses `from src.db.models import *  # noqa`.

7. **No pagination** — Admin API endpoints likely return all records. Will break with large datasets.

8. **Response text hardcoded in engine** — `conversation_engine.py` has inline Spanish/English strings (lines 246-250, 259-260, 273-281) instead of using `responder.py` consistently.

## Security Concerns

1. **CORS allows all origins** — `allow_origins=["*"]` in `main.py:25`. In production, should restrict to known domains.

2. **No webhook signature verification** — `webhook_cloud.py` POST handler doesn't verify Meta's X-Hub-Signature-256 header. Anyone can send fake webhook payloads.

3. **Admin auth is in-memory** — `auth.py` stores sessions in `_admin_sessions: set[str]` — lost on restart. No persistence.

4. **Admin password in plaintext** — `_check_password()` compares raw password via `secrets.compare_digest`. No hashing.

5. **No admin password by default** — When `admin_password=""`, `_check_password()` returns `True` — admin is open to anyone.

6. **Cookie lacks Secure flag** — `set_cookie()` in `auth.py:35` doesn't set `secure=True`. Cookie sent over HTTP.

7. **No rate limiting on webhooks** — `check_rate_limit()` exists but is not called from webhook routes.

8. **PostgreSQL default credentials** — `postgres:postgres` in docker-compose. Fine for dev, dangerous if exposed.

9. **No input sanitization** — User messages from WhatsApp passed directly to regex-based intent/entity extraction. Could craft messages to manipulate state.

10. **OpenAI API key in env** — Standard practice, but no rotation mechanism.

11. **No HTTPS enforcement** — No TLS configuration in Docker setup. Needs reverse proxy.

## Scalability Risks

1. **Single-process uvicorn** — `--reload` flag and no `--workers` in docker-compose. Single worker handles all requests.

2. **No connection pooling config** — AsyncPG pool uses defaults. Under load, may exhaust connections.

3. **Conversation state in JSONB** — State grows with `last_results_ids`, `preferences`, etc. No cleanup/archival.

4. **No caching layer** — Redis is configured but only used for rate limiting and Celery. Inventory queries hit DB every time.

5. **Sync Alembic on startup** — `main.py:58-65` runs Alembic migrations on every app start. Blocks startup, races with multiple workers.

6. **WhatsApp adapter creates new httpx client per call** — `WhatsAppCloudAdapter` likely creates a new client each time instead of reusing connections.

7. **No background processing for webhooks** — Webhook processes message synchronously. Long LLM calls would block the response to Meta (timeout risk).

8. **No message queue for outbound** — WhatsApp messages sent inline. If Meta API is slow, webhook response is delayed.

9. **SQLite in tests vs PostgreSQL in prod** — Different SQL dialects may mask bugs (JSONB, indexes, etc.).

## Missing Features (for production SaaS)

1. **No multi-tenancy** — Single dealership focus. No tenant isolation, no per-tenant billing, no signup flow.

2. **No billing/subscription** — No payment integration (Stripe, MercadoPago).

3. **No monitoring/observability** — No Sentry, no structured logging, no metrics (Prometheus/Datadog), no health check beyond `/health`.

4. **No CI/CD pipeline** — No GitHub Actions, no automated tests on push, no deployment automation.

5. **No backup strategy** — PostgreSQL volume data not backed up. No point-in-time recovery config.

6. **No bot→human handoff UI** — Leads are created and logged, but no real-time dashboard for managers to pick up conversations.

7. **No conversation history export** — No way to export chats for compliance/audit.

8. **No follow-up automation** — `followups_enabled` setting exists but no implementation found.

## Code Smells

1. **conversation_engine.py (500 lines)** — Giant function `process_message()` handles all intents in one if/elif chain. Should use strategy/handler pattern.

2. **Duplicate conversation creation** — Both `conversation_engine._get_or_create_conversation()` and `orchestrator.get_or_create_conversation()` implement the same logic independently.

3. **Mixed return types** — `orchestrator.process_message_debug()` returns a 5-tuple. Should use a dataclass/NamedTuple.

4. **No type hints on some functions** — `responder.py` functions likely lack full type annotations.

## Deployment Gaps

1. **No reverse proxy** — No nginx/Caddy for TLS termination, static file serving, rate limiting.

2. **No Docker health checks for API** — Only postgres has a healthcheck. API and worker containers don't.

3. **No log aggregation** — Logs go to stdout only. No log forwarding configured.

4. **No secrets management** — Env vars via `.env` file. No Vault, no AWS Secrets Manager.

5. **No auto-scaling** — Single container per service. No Kubernetes, no ECS.

6. **`--reload` in production command** — docker-compose uses `--reload` which is dev-only. Should be separate dev/prod configs.

7. **Source code mounted as volume** — `./src:/app/src` in docker-compose. Dev convenience, not for production.

## Data Integrity

1. **No database constraints on state** — `Conversation.state` is free-form JSONB. Invalid state shapes won't be caught.

2. **Race condition in conversation creation** — Handled with try/except/rollback in engine, but orchestrator doesn't handle it.

3. **No soft deletes** — No `deleted_at` columns. Hard deletes lose audit trail.

4. **No foreign key on Event.conversation_id** — `Event.conversation_id` is `Integer, nullable=True` with no ForeignKey. Can reference non-existent conversations.

5. **`onupdate=datetime.utcnow`** — SQLAlchemy `onupdate` only fires on ORM updates, not raw SQL. Can get stale `updated_at`.

6. **No migration for schema changes** — Only 2 migrations exist. Any manual DB changes would be untracked.
