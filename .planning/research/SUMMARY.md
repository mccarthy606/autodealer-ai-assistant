# Research Summary — AutoDealer AI Assistant SaaS

## Key Findings

### Stack
- Current stack (Python 3.12 + FastAPI + PostgreSQL + Redis + Celery) is solid — keep it
- Add: SSE for real-time, HTMX+Alpine.js for dashboard, Celery Beat for follow-ups, Caddy for TLS
- Lemon Squeezy via REST API (httpx already in deps)
- Multi-tenancy via PostgreSQL RLS + SQLAlchemy middleware (dealership_id already on all tables)
- No need for SPA framework — extend existing Jinja2 approach

### Table Stakes Missing
1. **Webhook signature verification** — security critical
2. **Manager reply UI** — can see conversations but can't reply through platform
3. **Proper admin auth** — in-memory sessions, plaintext password
4. **Data isolation** — no tenant middleware
5. **Production deployment** — no TLS, no monitoring, no backups

### Critical Pitfalls
1. **WhatsApp 24h window** — follow-ups MUST use template messages, not free-form
2. **Multi-tenancy data leaks** — enforce at SQLAlchemy level, not just route level
3. **Two engine divergence** — merge before adding features
4. **Webhook replay attacks** — verify signatures + deduplicate messages

### Recommended Build Order
1. Security hardening + refactoring (foundation)
2. Multi-tenancy (data isolation)
3. Manager dashboard (core value for client)
4. Follow-up automation
5. Analytics
6. Billing (Lemon Squeezy)
7. Production deployment

**Alternative:** Deploy first (Phase 1), then iterate. Depends on client urgency.

### Anti-Patterns to Avoid
- Don't build a React SPA — HTMX + Jinja2 is faster to ship
- Don't use Kubernetes — Docker Compose on VPS is right for 1-10 tenants
- Don't build a CRM — integrate with existing tools
- Don't automate price negotiation — dealerships want human control
