# Stack Research — SaaS Features for WhatsApp Car Dealership Bot

## Current Stack (Keep)

- **Python 3.12** + **FastAPI** — async, production-ready
- **SQLAlchemy 2.0** (async) + **AsyncPG** — ORM + driver
- **PostgreSQL 16** — primary database
- **Redis 7** — cache + Celery broker
- **Celery** — background tasks
- **Docker Compose** — deployment
- **Alembic** — migrations

## Additions Needed

### Multi-Tenancy
- **Row-Level Security (RLS)** via PostgreSQL — `dealership_id` column already exists on all tables
- No new library needed — enforce via SQLAlchemy query filters and middleware
- **Confidence: High** — pattern well-established, already partially implemented

### Real-Time Manager Dashboard
- **WebSockets via FastAPI** (`fastapi.WebSocket`) — built-in, no extra dependency
- **SSE (Server-Sent Events)** as simpler alternative — `sse-starlette >= 2.0`
- **Recommendation: SSE** — simpler, works through proxies, sufficient for dashboard updates
- **Frontend: HTMX + Alpine.js** — lightweight, works with existing Jinja2 templates
- **Confidence: High** — SSE is well-suited for one-way real-time updates

### Billing (Lemon Squeezy)
- **lemonsqueezy Python SDK** or direct REST API via **httpx** (already in deps)
- Lemon Squeezy webhooks for subscription lifecycle events
- **Store subscription state** in PostgreSQL (new `Subscription` model)
- **Confidence: Medium** — Lemon Squeezy Python SDK less mature than Stripe, but REST API is solid

### Follow-Up Automation
- **Celery Beat** (`celery[beat]`) — periodic task scheduler
- Schedule checks every 15 min for conversations needing follow-up
- **APScheduler** as alternative, but Celery already in stack
- **Confidence: High** — Celery Beat is standard for this

### Analytics
- **SQL aggregations** via SQLAlchemy — no separate analytics DB needed at this scale
- **Materialized views** in PostgreSQL for expensive queries
- **Chart.js** or **ApexCharts** for frontend visualization
- **Confidence: High** — PostgreSQL handles analytics well for single-digit tenants

### Production Deployment
- **Caddy** — reverse proxy with automatic TLS (simpler than nginx)
- **Docker Compose** (production profile) — separate from dev compose
- **Uvicorn** with `--workers 2-4` (drop `--reload`)
- **Sentry** (`sentry-sdk[fastapi]`) — error tracking
- **Structured logging** via `structlog` or `python-json-logger`
- **Confidence: High**

### Security Hardening
- **python-jose** or **PyJWT** — JWT tokens for admin API auth
- **Webhook signature verification** — HMAC-SHA256 (Meta standard)
- **CORS restriction** — whitelist specific origins
- **Confidence: High**

## What NOT to Use

| Technology | Why Not |
|-----------|---------|
| GraphQL | Overkill for admin dashboard, REST is fine |
| React/Vue SPA | Existing Jinja2 + HTMX is simpler and sufficient |
| Kafka/RabbitMQ | Redis + Celery handles current scale |
| Elasticsearch | PostgreSQL full-text search sufficient |
| Kubernetes | VPS + Docker Compose is right for 1-10 tenants |
| Stripe | User chose Lemon Squeezy |
| MongoDB | Already on PostgreSQL, no reason to switch |
