---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
stopped_at: Completed 13-01-PLAN.md
last_updated: "2026-03-28T22:44:37.058Z"
progress:
  total_phases: 15
  completed_phases: 12
  total_plans: 36
  completed_plans: 34
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Bot catches ML leads, writes customer on WhatsApp first, closes on dealership visit.
**Current focus:** Phase 13 — analytics-dashboard

## Current Position

Phase: 13 (analytics-dashboard) — EXECUTING
Plan: 2 of 3

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 4min | 1 tasks | 7 files |
| Phase 02 P01 | 4min | 2 tasks | 7 files |
| Phase 03 P01 | 8min | 1 tasks | 3 files |
| Phase 04 P01 | 2min | 2 tasks | 4 files |
| Phase 05 P01 | 15min | 4 tasks | 4 files |
| Phase 05 P02 | 12min | 3 tasks | 4 files |
| Phase 06 P02 | 15min | 4 tasks | 6 files |
| Phase 06 P04 | 10min | 4 tasks | 3 files |
| Phase 08 P01 | 5min | 3 tasks | 3 files |
| Phase 08 P04 | 15min | 2 tasks | 3 files |
| Phase 09 P01 | 15min | 2 tasks | 5 files |
| Phase 09 P02 | 8min | 2 tasks | 3 files |
| Phase 09 P03 | 8min | 1 tasks | 1 files |
| Phase 10 P01 | 8min | 2 tasks | 2 files |
| Phase 10 P03 | 5min | 1 tasks | 1 files |
| Phase 10 P02 | 8min | 2 tasks | 2 files |
| Phase 11 P01 | 5min | 3 tasks | 3 files |
| Phase 11 P02 | 5min | 2 tasks | 2 files |
| Phase 13 P01 | 5min | 1 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Brownfield project: build on top of existing MVP code, not rewrite
- Core business is OUTBOUND (ML lead -> WhatsApp first contact -> visit)
- Fine granularity: 9 phases targeting comprehensive coverage
- [Phase 01]: LLM rephrasing is opt-in via llm_enabled, deterministic responses always the fallback
- [Phase 01]: Lazy import pattern for optional LLM dependency in conversation_engine
- [Phase 02]: Empty ALLOWED_ORIGINS = deny all cross-origin (admin UI same-origin Jinja2 unaffected)
- [Phase 02]: Rate limiter returns tuple (allowed, retry_after) for better client UX
- [Phase 02]: Webhook reads raw body before JSON parse to prevent stream exhaustion
- [Phase 03]: Symmetric language switch via lang.split('-')[0] comparison handles es-AR variant
- [Phase 03]: Manager mode must explicitly set result.language from saved state
- [Phase 04]: Lazy import of phone_utils inside get_buyer_contact to avoid circular imports
- [Phase 04]: Phone normalizer builds 549+area+number format (WhatsApp E.164 for Argentina)
- [Phase 05]: OPT_OUT uses bare-no regex + keyword list; "no quiero" excluded (ambiguous shopping phrase)
- [Phase 05]: asyncio.run() used to call async send_template() from sync Celery worker
- [Phase 05]: 48h minimum gap enforced between followup #1 and followup #2 via last_followup_at
- [Phase 06-02]: WhatsAppCloudAdapter is fully backward-compatible; no-arg construction still works
- [Phase 06-02]: Silent 200 on unknown phone_number_id (Meta must never receive 4xx from webhook)
- [Phase 06-02]: Rate limiter key namespaced to rate:wa:{dealership_id}:{phone}
- [Phase 06-02]: ML webhook falls back to settings.default_dealership_id when no dealership found
- [Phase 06-04]: bcrypt hashes computed at module level in conftest.py to avoid per-test CPU cost
- [Phase 06-04]: is_authenticated test patches settings.admin_password to force real session check path
- [Phase 08-01]: migration chain 004→006→007 (no 005); down_revision="006"
- [Phase 08-01]: LS status paused/unpaid both map to past_due; unknown LS status defaults to expired
- [Phase 08-01]: status=None + future trial_ends_at = active (D-19 pre-subscription trial exception)
- [Phase 08-01]: Naive datetime normalization via .replace(tzinfo=UTC) before any datetime comparison
- [Phase 09-01]: api service has no ports key; Caddy is sole public entrypoint (80/443/443-udp)
- [Phase 09-01]: migrate is one-shot service (restart: no) with service_completed_successfully dependency
- [Phase 09-01]: backup.sh runs on host via docker exec, PGPASSWORD env var, 7-day retention
- [Phase 09-01]: FOLLOWUPS_ENABLED=false in .env.prod.example; beat always declared, checked inside task code
- [Phase 09-02]: Sentry init at module level before app = FastAPI(); conditional on non-empty sentry_dsn
- [Phase 09-02]: Celery timeout in /health maps to "timeout" (not "error") — HTTP 200 to keep load balancers happy
- [Phase 09-02]: Alembic removed from startup(); default dealership creation logic preserved
- [Phase 09-03]: Patch at source module (src.db.session, src.api.rate_limit, src.tasks.celery_app) — local imports in health() body mean src.main.* patches would be no-ops
- [Phase 09-03]: MagicMock (not AsyncMock) wraps async context manager to avoid coroutine-of-coroutine issue with __aenter__
- [Phase 10-01]: Migration 008 adds exactly 5 columns (not whatsapp_access_token — already in 006): whatsapp_webhook_secret, ml_access_token, ml_refresh_token, ml_app_id, ml_client_secret
- [Phase 10-01]: All 5 new credential columns are nullable=True — dealers configure post-onboarding, system works in unconfigured state
- [Phase 10]: [Phase 10-03]: settings.default_dealership_id fallback in WA webhook; logger.warning on double-miss; Dealership added to model import
- [Phase 11-01]: Lazy import of get_valid_token inside sync_all_listings() matches existing _ensure_token() pattern; pagination exits on empty results OR offset >= total
- [Phase 11-02]: asyncio.run() used to call async sync_all_listings() from sync Celery worker (same pattern as Phase 05)
- [Phase 11-02]: Sold-item marking filtered to source=="mercadolibre" only — prevents touching sheet/manual inventory rows
- [Phase 13]: _pct() helper defined at module level; funnel uses all-time counts per D-03; top_searches uses range_start; zero-fill generates full date list from today backwards

### Pending Todos

None yet.

### Blockers/Concerns

- Two conversation engines must be merged before outbound flow can work correctly
- WhatsApp 24h window rule: follow-ups MUST use template messages
- Multi-tenancy data isolation must be enforced at SQLAlchemy level (RLS), not just routes

## Session Continuity

Last session: 2026-03-28T22:44:37.055Z
Stopped at: Completed 13-01-PLAN.md
Resume file: None
