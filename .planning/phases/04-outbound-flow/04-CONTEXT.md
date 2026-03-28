# Phase 4: Outbound Flow - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the core outbound business flow: MercadoLibre inquiry arrives → system detects which car → finds customer phone → bot writes customer on WhatsApp FIRST with car info → outbound conversation script guides toward scheduling a dealership visit → visit confirmed → lead created + manager notified.

This is the CORE revenue-generating feature — everything before was preparation.

</domain>

<decisions>
## Implementation Decisions

### ML Inquiry Detection (OUT-01, OUT-02)
- **D-01:** Use existing `webhook_ml.py` as foundation. Current flow handles ML questions but doesn't initiate outbound WhatsApp. Extend to: detect inquiry → identify item_id → match to InventoryItem → get customer phone.
- **D-02:** ML question webhook provides: question_id, item_id, from.id (user). Use ML API to get the question text and the user's contact info.
- **D-03:** Match `item_id` to `InventoryItem.ml_item_id` in DB to identify the specific car. If no match, still proceed with basic item info from ML API.
- **D-04:** For customer phone: ML API may provide phone via `/users/{user_id}` endpoint (requires ML token). If phone unavailable, respond to ML question with invitation to WhatsApp (fallback).

### Outbound First Contact (OUT-03)
- **D-05:** First WhatsApp message must be a template message (Meta 24h rule — can't send free-form to someone who hasn't messaged you). Template should include: car name, price, key specs, dealership name, invitation to chat.
- **D-06:** Template message example (submit to Meta for approval):
  ```
  Hola {{1}}! Vi que te interesó el {{2}} ({{3}}).
  Está disponible por {{4}}.
  Querés que te cuente más o pasar a verlo en {{5}}?
  ```
  Parameters: customer_name, car_title, year+km, price, dealership_address
- **D-07:** WhatsApp template name convention: `outbound_car_inquiry_v1`
- **D-08:** If WhatsApp phone not available from ML, respond to ML question directly with car details + invitation to continue on WhatsApp.

### Outbound Conversation Script (OUT-04)
- **D-09:** After first contact, if customer replies → conversation enters existing engine in PRESENTING state (not NEW). The engine already handles details, photos, visit, financing flows.
- **D-10:** New state: `OUTBOUND_INIT` — set when bot sends first message. If customer replies, transition to `PRESENTING` with the ML car pre-selected as `selected_car_id`.
- **D-11:** Outbound conversation state stores: `source: "mercadolibre"`, `ml_question_id`, `ml_item_id`, `outbound: true`.

### Visit Confirmation + Lead (OUT-05)
- **D-12:** Visit flow already exists in engine (VISIT intent → lead creation + handoff). No changes needed — outbound conversations will naturally hit this flow.
- **D-13:** Manager notification via existing `notifications.py` handoff system.

### Processing Speed
- **D-14:** Process ML webhook synchronously (not Celery). Target: <60 seconds from ML inquiry to WhatsApp message. ML webhook is already async FastAPI.
- **D-15:** If WhatsApp template send fails, log error and respond to ML question as fallback.

### Claude's Discretion
- WhatsApp template message sending implementation details
- ML API endpoint specifics for user contact info
- Error handling and fallback chains
- New Alembic migration if model changes needed

</decisions>

<canonical_refs>
## Canonical References

### ML Integration Code
- `src/api/routes/webhook_ml.py` — Current ML webhook (handles questions, needs outbound extension)
- `src/adapters/mercadolibre.py` — ML API adapter (question fetching, item details, HTML scraping)
- `src/adapters/whatsapp_cloud.py` — WhatsApp Cloud adapter (send_text, send_images)

### Engine Code
- `src/services/conversation_engine.py` — Unified engine with state machine
- `src/services/lead_service.py` — Lead creation
- `src/services/notifications.py` — Manager notification

### Models
- `src/db/models.py` — Conversation, Message, Lead, InventoryItem models

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `webhook_ml.py` — Already receives ML question notifications, fetches question text and item_id
- `MercadoLibreAdapter` — Has `sync_listings()`, `get_questions()`, item fetching
- `WhatsAppCloudAdapter.send_text()` — Works in mock mode when not configured
- `InventoryService.search()` — Can match by ml_item_id
- `conversation_engine.process_message()` — Handles all intents including VISIT → lead + handoff
- `_car_to_dict()` — Formats car for response

### What Needs Building
1. **Template message sending** — WhatsAppCloudAdapter needs `send_template()` method
2. **ML→WhatsApp bridge** — webhook_ml.py needs to initiate WhatsApp contact after question
3. **OUTBOUND_INIT state** — New state in engine for outbound-initiated conversations
4. **ML user phone lookup** — API call to get customer's phone from ML user_id
5. **Outbound conversation state** — Track source=mercadolibre, outbound=true

### Integration Points
- `webhook_ml.py` — Main entry point (extend existing)
- `whatsapp_cloud.py` — Add send_template() method
- `conversation_engine.py` — Add OUTBOUND_INIT state handling
- `models.py` — Conversation.state already supports arbitrary JSONB data

</code_context>

<specifics>
## Specific Ideas

No specific requirements from user — all decisions delegated to Claude. Key business insight: the goal is SPEED — respond to ML inquiry on WhatsApp before the customer goes to a competitor.

</specifics>

<deferred>
## Deferred Ideas

- ML messaging integration (reply through ML messages, not just questions) — Phase later / v2
- A/B testing of outbound scripts — v2
- Smart timing (send based on business hours) — v2

</deferred>

---

*Phase: 04-outbound-flow*
*Context gathered: 2026-03-27*
