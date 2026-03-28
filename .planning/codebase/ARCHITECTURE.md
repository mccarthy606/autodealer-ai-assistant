# Architecture

## High-Level Pattern

**Layered architecture** with clear separation:

```
Routes (API/Webhooks) → Services (Business Logic) → DB (Models/Session)
                      → Adapters (External APIs)
                      → Tasks (Background Jobs)
```

Not hexagonal — adapters are called directly from services, not injected via ports.

## Request Flow

### WhatsApp Webhook Flow
```
Meta WABA → POST /webhooks/whatsapp_cloud
  → webhook_cloud.py: verify signature, parse payload
  → conversation_engine.process_message(session, dealership_id, phone, text, channel)
    → _get_or_create_conversation()
    → Save inbound Message
    → detect_language() + extract_all() entities
    → detect_intent() — rule-based
    → Process by intent (search, details, photos, visit, financing, etc.)
    → check_handoff() if needed → _do_handoff()
    → Save outbound Message
    → Update Conversation.state (JSONB)
  → whatsapp_cloud adapter → send reply via Meta API
```

### Admin Test Chat Flow
```
Admin UI → POST /admin/ui/chat (admin_ui.py)
  → ConversationOrchestrator.process_message_debug()
    → Priority: visit intent detection (rule-based)
    → If LLM enabled: llm_service.generate_response()
    → Else: deterministic_responder.respond()
  → Return JSON {text, matched_inventory, state, conversation_id}
```

## Two Processing Paths

There are **two parallel conversation processors**:

1. **conversation_engine.py** (`process_message`) — Primary, used by webhooks
   - Pure state machine, deterministic
   - Handles all intents directly
   - No LLM dependency

2. **orchestrator.py** (`ConversationOrchestrator`) — Used by admin debug/test chat
   - Can use LLM (OpenAI) when configured
   - Falls back to `deterministic_responder` when LLM unavailable
   - Has visit intent priority bypass

## Conversation State Machine

```
NEW → BROWSING → PRESENTING → DETAILS → CLOSING → HANDOFF
                                       → NOTIFY_WAIT
```

**State stored in:** `Conversation.state` (JSONB column)

**State contents:**
- `stage`: current FSM stage
- `language`: detected language (es/en)
- `name`: extracted customer name
- `preferred_time`: visit time preference
- `preferences`: {brand, model, year, budget_min, budget_max, condition}
- `last_results_ids`: IDs of last search results
- `selected_car_id`: currently focused car
- `unhelpful_count`: counter for auto-handoff (threshold: 2)

**Intents (rule-based detection):**
SEARCH_CAR, ASK_PHOTOS, ASK_DETAILS, ASK_PRICE, ASK_KM, ASK_STATUS,
VISIT, FINANCING, TRADE_IN, GREETING, NOTIFY, HUMAN, OTHER

**Handoff triggers:**
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
Dealership (1) ──┬── (*) InventoryItem
                 ├── (*) Conversation ── (*) Message
                 ├── (*) Lead
                 └── (*) Event
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

1. `src/main.py` — FastAPI app, router registration, startup hook (auto-migration + seed)
2. `start_local.py` — uvicorn runner for local development
3. `src/tasks/celery_app.py` — Celery worker entry point
