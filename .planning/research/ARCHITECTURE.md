# Architecture Research — SaaS Evolution

## Current Architecture

```
WhatsApp Cloud API → Webhook → conversation_engine → DB
                                                    → WhatsApp adapter (reply)
MercadoLibre API → Webhook → ML adapter → DB
Admin Browser → Jinja2 UI → Admin routes → DB
```

Single-tenant, single-process, no real-time.

## Target Architecture

```
                    ┌─────────────────────┐
                    │   Caddy (TLS/proxy) │
                    └──────┬──────────────┘
                           │
                    ┌──────▼──────────────┐
                    │  FastAPI App         │
                    │  ├─ Webhooks         │──→ WhatsApp Cloud API
                    │  ├─ Admin API        │
                    │  ├─ Manager Dashboard│──→ SSE (real-time)
                    │  ├─ Billing webhooks │──→ Lemon Squeezy
                    │  └─ Tenant middleware│
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │ PostgreSQL │ │ Redis │ │  Celery   │
        │ (RLS)      │ │       │ │  Workers  │
        └────────────┘ └───────┘ │  + Beat   │
                                 └───────────┘
```

## Component Boundaries

### 1. Tenant Middleware (NEW)
- Extract `dealership_id` from request context (webhook phone → dealership mapping, admin auth → tenant)
- Inject into all DB queries via SQLAlchemy event listeners
- **Connects to:** Every route, every DB query

### 2. Manager Dashboard (NEW)
- SSE endpoint for real-time conversation updates
- Reply-to-customer UI (sends via WhatsApp adapter)
- Lead queue with status transitions
- **Connects to:** Conversation model, WhatsApp adapter, SSE events

### 3. Follow-Up Worker (NEW)
- Celery Beat periodic task (every 15 min)
- Finds conversations with no activity > threshold
- Sends WhatsApp template messages (requires Meta-approved templates)
- **Connects to:** Conversation model, WhatsApp adapter, Celery

### 4. Analytics Aggregator (NEW)
- SQL views/materialized views for metrics
- API endpoints serving dashboard data
- **Connects to:** Event model, Message model, Lead model

### 5. Billing Service (NEW)
- Lemon Squeezy webhook handler
- Subscription model (tenant → plan → status)
- Middleware to check active subscription before processing
- **Connects to:** Dealership model, Lemon Squeezy API

### 6. Unified Engine (REFACTOR)
- Merge conversation_engine.py and orchestrator.py
- Single entry point for all channels
- **Connects to:** All services that currently depend on either engine

## Data Flow

### Inbound Message
```
Meta WABA → webhook_cloud.py
  → tenant_middleware (resolve dealership_id from phone_number_id)
  → unified_engine.process_message()
  → SSE broadcast to manager dashboard
  → save to DB
  → reply via WhatsApp adapter
```

### Manager Reply
```
Dashboard UI → POST /api/conversations/{id}/reply
  → tenant_middleware (from admin auth)
  → WhatsApp adapter.send_text()
  → save to DB
  → SSE broadcast (update conversation)
```

### Follow-Up
```
Celery Beat (every 15 min)
  → query: conversations with no activity > 24h, not handed off, not followed up
  → per conversation: send WhatsApp template message
  → mark as followed_up in DB
```

## Suggested Build Order

```
Phase 1: Security + Refactoring (foundation)
  → Webhook verification, CORS, auth hardening
  → Merge two engines
  → Split admin_ui.py

Phase 2: Multi-Tenancy (data isolation)
  → Tenant middleware
  → Phone number → dealership routing
  → Tenant-scoped queries

Phase 3: Manager Dashboard (core value)
  → Real-time conversation view
  → Reply through dashboard
  → Lead management

Phase 4: Follow-Up Automation
  → Celery Beat setup
  → WhatsApp template messages
  → Follow-up rules engine

Phase 5: Analytics
  → Metrics API
  → Dashboard visualizations
  → Conversion tracking

Phase 6: Billing (Lemon Squeezy)
  → Subscription model
  → Webhook handler
  → Access control by subscription

Phase 7: Production Deployment
  → Caddy + TLS
  → Monitoring (Sentry)
  → Backup strategy
  → Production Docker Compose
```

**Note:** Deployment could be Phase 1 instead — "deploy first, iterate in production" approach. Depends on client timeline.
