# Roadmap: AutoDealer AI Assistant

## Overview

Transform existing WhatsApp bot MVP into a production SaaS for Argentine auto dealerships. The core business flow is outbound: ML lead arrives, system detects car of interest, writes customer on WhatsApp first, scripts to close on visit. Phases 1–10 complete the foundation. Phases 11–15 build the full product: live ML inventory sync, AI agent, analytics, client onboarding, and test deployment.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Refactoring & Tech Debt** - Merge dual engines, split admin monolith, fix deprecated APIs (completed 2026-03-28)
- [x] **Phase 2: Security Hardening** - CORS lockdown, proper auth, webhook verification, rate limiting (completed 2026-03-28)
- [x] **Phase 3: Engine Consolidation** - Unified conversation engine with correct state machine, multilingual, dedup (completed 2026-03-28)
- [x] **Phase 4: Outbound Flow** - ML lead detection, auto-first-contact via WhatsApp, visit-closing script (completed 2026-03-28)
- [x] **Phase 5: Follow-Up Automation** - Template-based reminders at 24h/3d, opt-out respect, message limits (completed 2026-03-28)
- [x] **Phase 6: Multi-Tenancy** - Data isolation, tenant middleware, webhook routing, cache separation (completed 2026-03-28)
- [x] **Phase 7: Admin Dashboard & Analytics** - Per-tenant dashboard with stats, conversations, leads (completed 2026-03-28)
- [x] **Phase 8: Billing** - Lemon Squeezy subscription, webhook lifecycle, access gating, grace period (completed 2026-03-28)
- [x] **Phase 9: Production Deployment** - Docker prod profile, Caddy TLS, Sentry, backups, health checks, migrations (completed 2026-03-28)
- [x] **Phase 10: Client Integration Setup** - Self-service UI for dealerships to connect WhatsApp Business and MercadoLibre without .env editing (completed 2026-03-28)
- [x] **Phase 11: MercadoLibre Inventory Sync** - Pull ML listings into InventoryItems DB via API; Celery periodic sync; AI agent operates on live ML data (completed 2026-03-28)
- [x] **Phase 12: AI Agent (LLM Integration)** - Connect Claude/GPT to conversation engine; agent answers using inventory context; rule-based fallback (completed 2026-03-28)
- [x] **Phase 13: Analytics Dashboard** - Conversion funnel, lead stats over time, top brands/models, CSV export (completed 2026-03-28)
- [ ] **Phase 14: Client Onboarding** - Guided setup wizard in Admin UI; all instructions built-in (WA Business, ML app); client provides data → system configures itself
- [ ] **Phase 15: Test Deployment** - VPS deploy without domain (IP or free subdomain); full end-to-end test with real WhatsApp and ML

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

### Phase 11: MercadoLibre Inventory Sync
**Goal**: AI agent operates on live inventory data pulled from MercadoLibre — dealership's ML listings become the knowledge base
**Depends on**: Phase 10
**Success Criteria** (what must be TRUE):
  1. Admin UI has a "Sync from MercadoLibre" button that imports all active ML listings as InventoryItems
  2. Celery periodic task syncs ML inventory automatically (configurable interval)
  3. Sync handles pagination, updates existing items, marks sold/paused items accordingly
  4. AI agent answers inventory questions using ML-sourced data (brand, model, year, price, km, photos)
  5. Sync errors are logged and visible in Admin UI — dealer sees what failed and why
**Plans**: 3 plans
Plans:
- [ ] 11-01-PLAN.md — Migration 009 + Dealership model sync columns + MercadoLibreAdapter.sync_all_listings() with pagination
- [ ] 11-02-PLAN.md — Celery task sync_ml_inventory_all_dealers + upsert + mark-sold + beat schedule
- [ ] 11-03-PLAN.md — Admin UI: POST /cars/sync-ml route + cars.html button/status line + 6 unit tests

### Phase 12: AI Agent (LLM Integration)
**Goal**: Conversation engine uses Claude/GPT to generate natural, context-aware responses using live inventory data
**Depends on**: Phase 11
**Success Criteria** (what must be TRUE):
  1. llm_service.py is fully wired into conversation_engine.py — LLM generates responses when llm_enabled=True
  2. LLM receives inventory context (matching cars, specs, prices) with every request
  3. Responses feel natural and Spanish-first — not template strings
  4. Rule-based engine remains as fallback when LLM is unavailable or times out
  5. Per-dealer LLM config: dealer can set their own API key and model in Admin UI
**Plans**: 3 plans
Plans:
- [ ] 12-01-PLAN.md — Migration 010 + Dealership model: add llm_api_key, llm_model, llm_enabled columns
- [ ] 12-02-PLAN.md — conversation_engine.py: replace rephrase() hook with full generate_response() + silent fallback
- [ ] 12-03-PLAN.md — Admin Settings UI: 3 new LLM fields + save route updates + 3 unit tests

### Phase 13: Analytics Dashboard
**Goal**: Dealership owner has clear visibility into bot performance and lead conversion
**Depends on**: Phase 12
**Success Criteria** (what must be TRUE):
  1. Dashboard shows conversion funnel: conversations → leads → visits scheduled → closed
  2. Lead stats chart shows volume over time (last 7d / 30d / 90d)
  3. Top 10 requested brands/models ranked by inquiry count
  4. Average bot response time and handoff rate visible
  5. All data exportable as CSV
**Plans**: 3 plans
Plans:
- [x] 13-01-PLAN.md — Extend metrics_page(): range param, funnel queries, lead-volume-over-time data
- [x] 13-02-PLAN.md — Update metrics.html: funnel stat-cards, Chart.js line chart, range toggle buttons
- [x] 13-03-PLAN.md — CSV export: GET /leads/export-csv route + Exportar CSV button on leads.html
**UI hint**: yes

### Phase 14: Client Onboarding
**Goal**: New dealership can go from zero to fully configured without any manual help from us
**Depends on**: Phase 13
**Success Criteria** (what must be TRUE):
  1. Admin UI has a step-by-step onboarding wizard (WA Business setup → ML app → inventory sync → test message)
  2. Every step has built-in instructions in Spanish — no external docs needed
  3. Progress checklist shows what's configured and what's missing
  4. System validates each step before allowing the next (e.g., can't proceed without WA credentials saved)
  5. Dealer can send a test WhatsApp message to themselves from the onboarding UI
**Plans**: TBD
**UI hint**: yes

### Phase 15: Test Deployment
**Goal**: Full system running on a VPS and reachable for end-to-end testing with real WhatsApp — no domain purchase required
**Depends on**: Phase 14
**Success Criteria** (what must be TRUE):
  1. System deployed on VPS (Hetzner CX21 or equivalent) via docker-compose.prod.yml
  2. Accessible via IP or free subdomain (sslip.io / nip.io) with HTTPS
  3. Real WhatsApp message flows end-to-end: receive → AI response → send back
  4. MercadoLibre webhook receives and processes a real ML inquiry
  5. Admin UI accessible and functional at the deployment URL
**Plans**: TBD

## Progress

**Execution Order:**
Phases 1–12 complete. Active: Phase 13 → 14 → 15

| Phase | Status | Completed |
|-------|--------|-----------|
| 1. Refactoring & Tech Debt | ✅ Complete | 2026-03-28 |
| 2. Security Hardening | ✅ Complete | 2026-03-28 |
| 3. Engine Consolidation | ✅ Complete | 2026-03-28 |
| 4. Outbound Flow | ✅ Complete | 2026-03-28 |
| 5. Follow-Up Automation | ✅ Complete | 2026-03-28 |
| 6. Multi-Tenancy | ✅ Complete | 2026-03-28 |
| 7. Admin Dashboard & Analytics | ✅ Complete | 2026-03-28 |
| 8. Billing | ✅ Complete | 2026-03-28 |
| 9. Production Deployment | ✅ Complete | 2026-03-28 |
| 10. Client Integration Setup | ✅ Complete | 2026-03-28 |
| 11. MercadoLibre Inventory Sync | ✅ Complete | 2026-03-28 |
| 12. AI Agent (LLM Integration) | ✅ Complete | 2026-03-28 |
| 13. Analytics Dashboard | 🔄 Planned | - |
| 14. Client Onboarding | 🔄 Not started | - |
| 15. Test Deployment | 🔄 Not started | - |
