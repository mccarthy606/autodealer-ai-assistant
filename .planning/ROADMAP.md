# Roadmap: AutoDealer AI Assistant

## Overview

Transform existing WhatsApp bot MVP into a production SaaS for Argentine auto dealerships. The core business flow is outbound: ML lead arrives, system detects car of interest, writes customer on WhatsApp first, scripts to close on visit. Nine phases take us from tech debt cleanup through production deployment, building on top of existing code (conversation engine, intent detection, WhatsApp integration, admin UI, Docker Compose).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Refactoring & Tech Debt** - Merge dual engines, split admin monolith, fix deprecated APIs
- [ ] **Phase 2: Security Hardening** - CORS lockdown, proper auth, webhook verification, rate limiting
- [ ] **Phase 3: Engine Consolidation** - Unified conversation engine with correct state machine, multilingual, dedup
- [ ] **Phase 4: Outbound Flow** - ML lead detection, auto-first-contact via WhatsApp, visit-closing script
- [ ] **Phase 5: Follow-Up Automation** - Template-based reminders at 24h/3d, opt-out respect, message limits
- [ ] **Phase 6: Multi-Tenancy** - Data isolation, tenant middleware, webhook routing, cache separation
- [ ] **Phase 7: Admin Dashboard & Analytics** - Per-tenant dashboard with stats, conversations, leads
- [ ] **Phase 8: Billing** - Lemon Squeezy subscription, webhook lifecycle, access gating, grace period
- [ ] **Phase 9: Production Deployment** - Docker prod profile, Caddy TLS, Sentry, backups, health checks, migrations
- [x] **Phase 10: Client Integration Setup** - Self-service UI for dealerships to connect WhatsApp Business and MercadoLibre without .env editing (completed 2026-03-28)

## Phase Details

### Phase 1: Refactoring & Tech Debt
**Goal**: Codebase is clean and maintainable — single engine, modular admin, no deprecated APIs
**Depends on**: Nothing (first phase)
**Requirements**: REF-01, REF-02, REF-03
**Success Criteria** (what must be TRUE):
  1. Only one conversation engine file exists and all conversation routes use it
  2. admin_ui.py is split into separate modules (inventory, leads, conversations, dashboard) each under 300 lines
  3. No remaining datetime.utcnow() calls in the codebase — all use datetime.now(UTC)
  4. All existing tests still pass after refactoring
**Plans**: 3 plans
Plans:
- [x] 01-01-PLAN.md — Engine merge: absorb LLM layer from orchestrator, delete dead code
- [x] 01-02-PLAN.md — Admin UI split: break admin_ui.py into 5 domain modules
- [x] 01-03-PLAN.md — datetime fix: replace all datetime.utcnow() with datetime.now(UTC)

### Phase 2: Security Hardening
**Goal**: Application endpoints are protected against common attack vectors
**Depends on**: Phase 1
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04
**Success Criteria** (what must be TRUE):
  1. CORS rejects requests from non-whitelisted origins
  2. Admin login uses bcrypt-hashed passwords stored in DB with Redis-backed sessions
  3. WhatsApp webhook rejects requests with invalid Meta signature
  4. Webhook endpoints return 429 after exceeding rate limit threshold
**Plans**: 2 plans
Plans:
- [x] 02-01-PLAN.md — Config + CORS lockdown + rate_limit refactor + Lemon Squeezy webhook
- [x] 02-02-PLAN.md — Auth Redis+bcrypt migration + async conversion + rate limit wiring

### Phase 3: Engine Consolidation
**Goal**: Unified conversation engine handles all inbound channels with correct behavior
**Depends on**: Phase 1
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04
**Success Criteria** (what must be TRUE):
  1. Single engine processes all conversation states (NEW, BROWSING, PRESENTING, DETAILS, CLOSING, HANDOFF) correctly
  2. Bot responds in Spanish to Spanish messages and English to English messages automatically
  3. Duplicate WhatsApp messages (same wamid) are silently dropped without double-processing
  4. All seven intents (search, photos, details, visit, financing, trade-in, human) trigger correct state transitions
**Plans**: 2 plans
Plans:
- [x] 03-01-PLAN.md — State machine verification + language stickiness fix + comprehensive tests
- [x] 03-02-PLAN.md — WhatsApp message deduplication via wamid column + webhook dedup check

### Phase 4: Outbound Flow
**Goal**: System proactively contacts ML leads via WhatsApp and scripts them toward a dealership visit
**Depends on**: Phase 2, Phase 3
**Requirements**: OUT-01, OUT-02, OUT-03, OUT-04, OUT-05
**Success Criteria** (what must be TRUE):
  1. When a MercadoLibre inquiry arrives, system processes it within 60 seconds
  2. System identifies the specific vehicle the lead inquired about from the ML webhook payload
  3. Bot sends first WhatsApp message to the lead with vehicle info (photo, price, key specs)
  4. Bot follows outbound conversation script aimed at scheduling a visit
  5. When lead confirms a visit, a lead record is created and the assigned manager receives a notification
**Plans**: 2 plans
Plans:
- [x] 04-01-PLAN.md — Adapter extensions: send_template(), get_buyer_contact(), phone normalizer, ml_item_id index
- [x] 04-02-PLAN.md — Outbound service pipeline + OUTBOUND_INIT engine state + webhook wiring + tests

### Phase 5: Follow-Up Automation
**Goal**: Unresponsive leads receive automated, compliant follow-up messages that respect boundaries
**Depends on**: Phase 4
**Requirements**: FUP-01, FUP-02, FUP-03, FUP-04, FUP-05
**Success Criteria** (what must be TRUE):
  1. Lead who does not reply within 24 hours receives a follow-up via WhatsApp template message
  2. Lead still silent after 3 days receives a second follow-up template message
  3. All follow-ups use approved WhatsApp template messages (not free-form text)
  4. No lead receives more than 2-3 follow-up messages total per conversation
  5. Lead who explicitly declines (says "no", "not interested", etc.) receives zero further follow-ups
**Plans**: TBD

### Phase 6: Multi-Tenancy
**Goal**: Multiple dealerships operate on one instance with complete data isolation
**Depends on**: Phase 2
**Requirements**: MT-01, MT-02, MT-03, MT-04
**Success Criteria** (what must be TRUE):
  1. Dealership A cannot see or access Dealership B's inventory, leads, or conversations
  2. Incoming requests are automatically scoped to the correct dealership without manual configuration
  3. WhatsApp webhooks are routed to the correct dealership based on phone_number_id
  4. Redis cache keys are prefixed per tenant — no cross-tenant cache pollution
**Plans**: TBD

### Phase 7: Admin Dashboard & Analytics
**Goal**: Dealership owner can monitor bot performance, review conversations, and manage leads
**Depends on**: Phase 6
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. Dashboard home shows key metrics: active conversations, new leads today, pending visits
  2. Analytics page displays lead count, visit conversion rate, and average response time
  3. Analytics page shows top requested brands/models as a ranked list
  4. Owner can browse all conversations with full message history
  5. Owner can view and filter leads by status (new, contacted, visit scheduled, closed)
**Plans**: TBD
**UI hint**: yes

### Phase 8: Billing
**Goal**: Only paying dealerships can use the service, managed via Lemon Squeezy subscriptions
**Depends on**: Phase 6
**Requirements**: BILL-01, BILL-02, BILL-03, BILL-04
**Success Criteria** (what must be TRUE):
  1. Each tenant has a subscription plan linked to their account
  2. Lemon Squeezy webhook events (created, renewed, cancelled, past_due) update tenant subscription status
  3. Bot stops processing messages for tenants without active subscription
  4. Tenant with failed payment gets a grace period before service interruption
**Plans**: TBD

### Phase 9: Production Deployment
**Goal**: System is running in production with TLS, monitoring, backups, and proper ops
**Depends on**: Phase 7, Phase 8
**Requirements**: DEP-01, DEP-02, DEP-03, DEP-04, DEP-05, DEP-06
**Success Criteria** (what must be TRUE):
  1. Docker Compose production profile runs without --reload, with multiple workers
  2. HTTPS works via Caddy with automatic certificate renewal
  3. Application errors are captured in Sentry with proper context
  4. PostgreSQL is backed up daily via pg_dump with retention policy
  5. Health check endpoint at /health returns status of DB, Redis, and Celery connections
  6. Database migrations run via Alembic as a separate step before app startup
**Plans**: 3 plans
Plans:
- [x] 09-01-PLAN.md — Infra files: docker-compose.prod.yml, Caddyfile, Makefile, scripts/backup.sh, .env.prod.example
- [x] 09-02-PLAN.md — Code changes: Sentry init (config.py + pyproject.toml + main.py), deep /health, remove alembic from startup()
- [ ] 09-03-PLAN.md — Tests: 4 automated tests for /health endpoint (all-ok, db-error, redis-error, celery-timeout)

### Phase 10: Client Integration Setup
**Goal**: Dealership owner can connect WhatsApp Business and MercadoLibre through the Admin UI — no .env editing, no docker commands required
**Depends on**: Phase 6, Phase 9
**Requirements**: INT-01, INT-02, INT-03, INT-04, INT-05
**Success Criteria** (what must be TRUE):
  1. Dealership credentials (WhatsApp token, phone ID, ML tokens) are stored in the dealerships table, not only in .env
  2. Admin integrations page has a form where owner enters and saves WhatsApp and ML credentials
  3. "Verificar conexión" button makes a live API call and shows result inline
  4. WhatsApp webhooks route by phone_number_id looked up from DB (not just settings)
  5. ML token manager uses per-dealership Redis keys (ml:{did}:access_token etc.)
**Plans**: 4 plans
Plans:
- [x] 10-01-PLAN.md — Migration 008 + Dealership model: add 5 credential columns (whatsapp_webhook_secret, ml_access_token, ml_refresh_token, ml_app_id, ml_client_secret)
- [x] 10-02-PLAN.md — ml_token_manager.py per-dealer key refactor + MercadoLibreAdapter._ensure_token() update
- [x] 10-03-PLAN.md — webhook_cloud.py: default dealership fallback when phone_number_id not in DB
- [x] 10-04-PLAN.md — Admin integrations page redesign: Spanish credential forms + save route + test-connection endpoint

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Refactoring & Tech Debt | 3/3 | Planning complete | - |
| 2. Security Hardening | 2/2 | Executing | - |
| 3. Engine Consolidation | 1/2 | Executing | - |
| 4. Outbound Flow | 1/2 | Executing | - |
| 5. Follow-Up Automation | 0/? | Not started | - |
| 6. Multi-Tenancy | 0/? | Not started | - |
| 7. Admin Dashboard & Analytics | 0/? | Not started | - |
| 8. Billing | 0/? | Not started | - |
| 9. Production Deployment | 0/3 | Planning complete | - |
| 10. Client Integration Setup | 4/4 | Complete    | 2026-03-28 |
