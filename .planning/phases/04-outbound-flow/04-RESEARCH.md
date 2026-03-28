# Phase 4: Outbound Flow - Research

**Researched:** 2026-03-27
**Domain:** MercadoLibre Questions API + WhatsApp Business Cloud API Template Messages + Outbound Conversation State Machine
**Confidence:** MEDIUM

## Summary

The outbound flow is a bridge between two external APIs (MercadoLibre Questions and WhatsApp Cloud) plus an extension of the existing conversation engine. The existing codebase already has working ML webhook reception (`webhook_ml.py`), ML API adapter, WhatsApp send capabilities, and a full state machine in `conversation_engine.py`. The main work is: (1) adding a `send_template()` method to WhatsApp adapter, (2) extending the ML webhook to initiate outbound WhatsApp contact, (3) adding `OUTBOUND_INIT` state to the engine, and (4) building the ML-to-phone lookup bridge.

The critical risk area is **ML user phone availability**. MercadoLibre's Questions API for the vehicles category provides buyer contact info (phone, email, name) via `/questions/{id}?api_version=4` -- but this requires proper ML OAuth scopes and the seller account must be `car_dealer` type. If phone is unavailable, the fallback is answering the ML question directly with an invitation to WhatsApp. WhatsApp template messages are well-documented and straightforward to implement with the Graph API.

**Primary recommendation:** Build the outbound flow as a pipeline in `webhook_ml.py`: receive notification -> fetch question with `api_version=4` -> match item to InventoryItem -> attempt phone lookup -> send WhatsApp template OR fallback to ML answer. Add `OUTBOUND_INIT` state so when the customer replies on WhatsApp, the engine picks up with the car already selected.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Use existing `webhook_ml.py` as foundation. Extend to: detect inquiry -> identify item_id -> match to InventoryItem -> get customer phone.
- D-02: ML question webhook provides: question_id, item_id, from.id (user). Use ML API to get the question text and the user's contact info.
- D-03: Match `item_id` to `InventoryItem.ml_item_id` in DB to identify the specific car. If no match, still proceed with basic item info from ML API.
- D-04: For customer phone: ML API may provide phone via `/users/{user_id}` endpoint. If phone unavailable, respond to ML question with invitation to WhatsApp (fallback).
- D-05: First WhatsApp message must be a template message (Meta 24h rule). Template includes: car name, price, key specs, dealership name, invitation to chat.
- D-06: Template message with parameters: customer_name, car_title, year+km, price, dealership_address.
- D-07: WhatsApp template name convention: `outbound_car_inquiry_v1`
- D-08: If WhatsApp phone not available from ML, respond to ML question directly with car details + invitation to continue on WhatsApp.
- D-09: After first contact, if customer replies -> conversation enters existing engine in PRESENTING state (not NEW).
- D-10: New state: `OUTBOUND_INIT` -- set when bot sends first message. If customer replies, transition to `PRESENTING` with the ML car pre-selected as `selected_car_id`.
- D-11: Outbound conversation state stores: `source: "mercadolibre"`, `ml_question_id`, `ml_item_id`, `outbound: true`.
- D-12: Visit flow already exists in engine. No changes needed -- outbound conversations will naturally hit this flow.
- D-13: Manager notification via existing `notifications.py` handoff system.
- D-14: Process ML webhook synchronously (not Celery). Target: <60 seconds from ML inquiry to WhatsApp message.
- D-15: If WhatsApp template send fails, log error and respond to ML question as fallback.

### Claude's Discretion
- WhatsApp template message sending implementation details
- ML API endpoint specifics for user contact info
- Error handling and fallback chains
- New Alembic migration if model changes needed

### Deferred Ideas (OUT OF SCOPE)
- ML messaging integration (reply through ML messages, not just questions) -- Phase later / v2
- A/B testing of outbound scripts -- v2
- Smart timing (send based on business hours) -- v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OUT-01 | System monitors incoming ML inquiries in real time | Existing `webhook_ml.py` already receives ML notifications. Extend to trigger outbound flow. |
| OUT-02 | System identifies the specific car the customer is interested in | Use `item_id` from question -> match to `InventoryItem.ml_item_id`. Fallback: fetch item info from ML API. |
| OUT-03 | System automatically writes customer on WhatsApp first with car info | WhatsApp Cloud API `send_template()` with `outbound_car_inquiry_v1` template. Requires phone from ML API. |
| OUT-04 | Bot follows outbound conversation script toward scheduling visit | `OUTBOUND_INIT` state in engine. On customer reply, transition to `PRESENTING` with car pre-selected. Engine already handles VISIT flow. |
| OUT-05 | Visit confirmation creates lead and notifies manager | Already implemented: VISIT intent -> `create_lead_from_conversation()` -> `handoff_to_manager()`. No changes needed. |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.26.0 | ML API calls, WhatsApp Graph API calls | Already used throughout adapters |
| FastAPI | >=0.109.0 | Async webhook endpoint | Already the HTTP framework |
| SQLAlchemy | >=2.0.25 | InventoryItem lookup by ml_item_id | Already the ORM |

### Supporting (no new dependencies needed)
This phase requires NO new pip packages. All external API calls use `httpx` which is already installed. The WhatsApp template message sending uses the same Graph API endpoint already used by `send_text()`.

## Architecture Patterns

### Recommended Changes to Existing Structure
```
src/
  api/routes/
    webhook_ml.py        # MODIFY: add outbound flow after question fetch
  adapters/
    mercadolibre.py      # MODIFY: add get_user_phone() method
    whatsapp_cloud.py    # MODIFY: add send_template() method
  services/
    conversation_engine.py  # MODIFY: add OUTBOUND_INIT state handling
    outbound_service.py     # NEW: orchestrate ML->WhatsApp bridge
  db/
    models.py            # NO CHANGE: state JSONB already supports arbitrary fields
```

### Pattern 1: Outbound Service as Orchestrator
**What:** A new `outbound_service.py` that contains the full pipeline: question -> car lookup -> phone lookup -> send template -> create conversation with OUTBOUND_INIT state.
**When to use:** Called from `webhook_ml.py` after parsing the ML notification.
**Why separate:** Keeps webhook_ml.py thin (routing only), puts business logic in service layer (matches existing pattern of `lead_service.py`, `notifications.py`).
**Example:**
```python
# src/services/outbound_service.py
async def handle_ml_inquiry(
    session: AsyncSession,
    dealership_id: int,
    question_id: str,
    item_id: str,
    from_user_id: str,
    question_text: str,
) -> OutboundResult:
    """
    Full outbound pipeline:
    1. Match item_id to InventoryItem
    2. Attempt to get buyer phone from ML
    3. If phone: send WhatsApp template, create conversation in OUTBOUND_INIT
    4. If no phone: answer ML question with car details + WhatsApp invitation
    """
```

### Pattern 2: OUTBOUND_INIT State in Engine
**What:** New state that acts as a "waiting for reply" state. When a customer replies to the template message, the engine detects OUTBOUND_INIT and transitions to PRESENTING with the car pre-selected.
**When to use:** Only for outbound-initiated conversations (not inbound).
**Example:**
```python
# In conversation_engine.py process_message(), before intent processing:
if stage == "OUTBOUND_INIT":
    # Customer replied to our outbound template
    # Transition to PRESENTING with pre-selected car
    state["stage"] = "PRESENTING"
    # Car is already set in state["selected_car_id"]
    # Fall through to normal intent handling
```

### Pattern 3: WhatsApp Template Message Sending
**What:** `send_template()` method on WhatsAppCloudAdapter.
**Example:**
```python
async def send_template(
    self, to: str, template_name: str, language_code: str,
    components: list[dict],
) -> dict:
    """Send a template message via WhatsApp Cloud API."""
    if not self.is_configured:
        logger.info("[WhatsApp MOCK] send_template to=%s template=%s", to, template_name)
        return {"status": "mock", "to": to}

    url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }
    return await self._post(url, payload)
```

### Pattern 4: ML User Phone Lookup
**What:** Method on MercadoLibreAdapter to fetch buyer phone from question data.
**Implementation:** Use `/questions/{id}?api_version=4` which returns buyer contact info for vehicles category.
**Example:**
```python
async def get_buyer_contact(self, question_id: str) -> dict | None:
    """
    Fetch buyer contact info from ML question (api_version=4).
    Returns {phone, email, name} or None.
    For vehicles category, ML provides contact info when buyer clicks
    'Quiero que me contacten'.
    """
    if not self.is_configured:
        return None
    url = f"{ML_API_URL}/questions/{question_id}?api_version=4"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=self._headers())
        data = resp.json()
        buyer = data.get("from", {})
        # api_version=4 may include phone in buyer object
        phone = buyer.get("phone", {})
        if phone and phone.get("number"):
            area = phone.get("area_code", "")
            number = phone.get("number", "")
            return {
                "phone": f"+54{area}{number}",  # Argentina format
                "email": buyer.get("email"),
                "name": buyer.get("first_name", ""),
            }
    return None
```

### Anti-Patterns to Avoid
- **Sending free-form first message on WhatsApp:** Meta's 24-hour rule means the FIRST outbound message MUST be an approved template. Free-form messages only work within the 24-hour customer-initiated window.
- **Blocking the ML webhook response:** The webhook should return 200 quickly. The outbound flow should run async within the same request but not hold up the response indefinitely. If external API calls fail, log and fallback.
- **Creating duplicate conversations:** When outbound conversation is created, use real phone number as `user_phone`. When customer replies on WhatsApp, `_get_or_create_conversation()` will find the existing conversation by phone + dealership.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template message format | Custom JSON builder | Direct Graph API payload dict | Simple enough -- just 3 fields: name, language, components |
| Phone number formatting | Complex phone parser | Simple string concat with country code | Argentina only, format is consistent: +54 + area + number |
| Item matching | Full-text search on ML data | Direct `InventoryItem.ml_item_id` column match | Already exists, exact match is sufficient |
| Retry logic | Custom retry framework | Simple try/except with fallback | Only 2 API calls, fallback is answering ML question directly |

## Common Pitfalls

### Pitfall 1: ML Phone Number Availability
**What goes wrong:** ML may NOT provide buyer phone for regular questions -- only for "Quiero que me contacten" (contact request) clicks in the vehicles category. Regular questions only provide `from.id` (user ID).
**Why it happens:** MercadoLibre restricts contact data sharing. Phone/email are only available in certain contexts (vehicles category, car_dealer seller type, api_version=4).
**How to avoid:** Always implement the fallback path (D-08): if phone is unavailable, answer the ML question directly with car info + WhatsApp number invitation. The fallback path may be the PRIMARY path in practice.
**Warning signs:** `get_buyer_contact()` returns None for all questions -- means the ML account doesn't have vehicle category contact permissions.

### Pitfall 2: WhatsApp Template Not Approved
**What goes wrong:** Template messages require Meta approval (24-72 hours). If template `outbound_car_inquiry_v1` is not yet approved, `send_template()` will return an error.
**Why it happens:** Meta reviews templates for policy compliance before allowing them to be used.
**How to avoid:** Submit template for approval early. In code, handle the "template not approved" error gracefully and fall back to ML question answer. The system should work end-to-end even when template is pending approval.
**Warning signs:** HTTP 400 from Graph API with error about template status.

### Pitfall 3: Phone Number Format Mismatch
**What goes wrong:** WhatsApp requires phone in international format without `+` (e.g., `5491112345678`). ML may return phone in local format (e.g., `011-1234-5678`).
**Why it happens:** Different APIs use different phone formats.
**How to avoid:** Normalize phone to E.164 format before storing. Strip all non-digit characters, ensure starts with country code `54` for Argentina.
**Warning signs:** WhatsApp API returns "invalid phone number" errors.

### Pitfall 4: Conversation Conflict Between ML and WhatsApp
**What goes wrong:** ML questions create a conversation with `phone=ml_{user_id}` (line 64 of current webhook_ml.py). If the same user later contacts via WhatsApp with their real phone, two separate conversations exist.
**Why it happens:** Current code uses `ml_{user_id}` as phone identifier for ML channel conversations. Outbound flow needs to use the real phone number.
**How to avoid:** The outbound flow should create a NEW conversation with the real WhatsApp phone number (not `ml_{user_id}`). The ML question processing should remain as-is (answering ML questions through ML). The outbound WhatsApp conversation is a separate interaction.
**Warning signs:** Duplicate or orphaned conversations in DB.

### Pitfall 5: ml_item_id Column Has No Index
**What goes wrong:** Looking up `InventoryItem.ml_item_id` for each webhook will do a sequential scan.
**Why it happens:** The column exists but has no index. Current indexes are on `(dealership_id, status)` and `(dealership_id, brand, model)`.
**How to avoid:** Add an Alembic migration to create an index on `(dealership_id, ml_item_id)`. This will be needed for every incoming ML question.
**Warning signs:** Slow queries on inventory lookup.

## Code Examples

### WhatsApp Template Message Payload (verified from Meta docs)
```python
# Source: Meta WhatsApp Cloud API docs
# POST https://graph.facebook.com/v18.0/{phone_number_id}/messages
{
    "messaging_product": "whatsapp",
    "to": "5491112345678",
    "type": "template",
    "template": {
        "name": "outbound_car_inquiry_v1",
        "language": {"code": "es_AR"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Juan"},           # {{1}} customer_name
                    {"type": "text", "text": "Toyota Hilux SRV"},  # {{2}} car_title
                    {"type": "text", "text": "2023 - 45.000 km"},  # {{3}} year+km
                    {"type": "text", "text": "$18.000.000 ARS"},   # {{4}} price
                    {"type": "text", "text": "Av. Libertador 1234, CABA"},  # {{5}} address
                ]
            }
        ]
    }
}
```

### ML Question Webhook Notification (from existing code)
```python
# Incoming ML webhook payload:
{
    "topic": "questions",
    "resource": "/questions/12345678",
    "user_id": "seller_user_id"
}

# Fetched question data (current code, line 49-55 of webhook_ml.py):
# GET https://api.mercadolibre.com/questions/12345678
{
    "id": 12345678,
    "text": "Hola, esta disponible?",
    "item_id": "MLA1234567890",
    "from": {"id": 98765432},
    "status": "UNANSWERED"
}

# With api_version=4 (vehicles category, needs testing):
# GET https://api.mercadolibre.com/questions/12345678?api_version=4
# Response MAY include extended buyer info in "from" object
```

### InventoryItem Lookup by ml_item_id
```python
# Match ML item to local inventory
from sqlalchemy import select
from src.db.models import InventoryItem

stmt = select(InventoryItem).where(
    InventoryItem.dealership_id == dealership_id,
    InventoryItem.ml_item_id == item_id,  # e.g., "MLA1234567890"
)
result = await session.execute(stmt)
car = result.scalar_one_or_none()
```

### Outbound Conversation Creation
```python
# Create conversation in OUTBOUND_INIT state
conv = Conversation(
    dealership_id=dealership_id,
    user_phone=customer_phone,  # real WhatsApp phone, NOT ml_{user_id}
    channel="whatsapp",
    state={
        "stage": "OUTBOUND_INIT",
        "source": "mercadolibre",
        "ml_question_id": question_id,
        "ml_item_id": item_id,
        "outbound": True,
        "selected_car_id": car.id if car else None,
        "language": "es",
    },
    mode="bot",
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| WhatsApp conversation pricing | Per-template pricing (no 24h conversation fee) | July 2025 | Each template message now charged individually |
| Graph API v18.0 | Graph API v23.0 latest | Rolling | Existing code uses v18.0 which still works, but v20.0+ recommended |
| ML Questions API v1 | Questions API with api_version=4 | ~2024 | Vehicle category gets contact info (phone, email) with v4 |

**Notes:**
- The project currently uses Graph API v18.0 (`GRAPH_API_URL = "https://graph.facebook.com/v18.0"`). This still works but consider upgrading to v20.0+ when convenient. Not blocking for this phase.
- WhatsApp template pricing changed in July 2025: each delivered template is charged separately, no more flat 24-hour conversation windows.

## Open Questions

1. **ML api_version=4 phone availability**
   - What we know: ML docs for vehicles category mention buyer contact info via api_version=4. The seller must have `car_dealer` user_type.
   - What's unclear: Whether the specific ML account being used has the correct permissions/category to receive buyer phone numbers in question responses.
   - Recommendation: Implement both paths (WhatsApp outbound + ML answer fallback). Test with real ML account. The fallback path must work perfectly since it may be the primary path.

2. **Template approval timeline**
   - What we know: Meta reviews templates in 24-72 hours. Template must follow WhatsApp Business Messaging Policy.
   - What's unclear: Whether the specific WhatsApp Business Account has been set up to submit templates.
   - Recommendation: Code should work end-to-end with mock mode. Template submission is a manual/admin task outside code scope.

3. **Argentine phone number format from ML**
   - What we know: WhatsApp needs numbers in format `5491XXXXXXXX` (country code 54, mobile prefix 9, area code, number).
   - What's unclear: Exact format ML returns (may be `011-XXXX-XXXX` local, or `+54 11 XXXX-XXXX`, or just digits).
   - Recommendation: Build a phone normalization function that handles common Argentine formats and normalizes to E.164.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4+ with pytest-asyncio (mode: auto) |
| Config file | pyproject.toml (pytest section) |
| Quick run command | `python -m pytest tests/test_outbound.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OUT-01 | ML webhook triggers outbound flow | unit | `python -m pytest tests/test_outbound.py::test_ml_webhook_triggers_outbound -x` | Wave 0 |
| OUT-02 | Item_id matched to InventoryItem.ml_item_id | unit | `python -m pytest tests/test_outbound.py::test_item_matched_to_inventory -x` | Wave 0 |
| OUT-03 | WhatsApp template sent with car info | unit | `python -m pytest tests/test_outbound.py::test_whatsapp_template_sent -x` | Wave 0 |
| OUT-03 | Fallback: ML answer when no phone | unit | `python -m pytest tests/test_outbound.py::test_fallback_ml_answer_no_phone -x` | Wave 0 |
| OUT-04 | OUTBOUND_INIT -> PRESENTING on reply | unit | `python -m pytest tests/test_outbound.py::test_outbound_init_to_presenting -x` | Wave 0 |
| OUT-04 | Outbound conversation follows script to visit | integration | `python -m pytest tests/test_outbound.py::test_outbound_full_flow_to_visit -x` | Wave 0 |
| OUT-05 | Visit creates lead from outbound conversation | unit | `python -m pytest tests/test_outbound.py::test_outbound_visit_creates_lead -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_outbound.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_outbound.py` -- covers OUT-01 through OUT-05 (all 7 test cases above)
- [ ] Fixtures needed: `sample_car_with_ml_id` (InventoryItem with ml_item_id set)

## Sources

### Primary (HIGH confidence)
- Existing codebase: `webhook_ml.py`, `mercadolibre.py`, `whatsapp_cloud.py`, `conversation_engine.py`, `models.py` -- direct inspection
- Meta WhatsApp Cloud API docs: template message payload format

### Secondary (MEDIUM confidence)
- MercadoLibre Developers docs (questions, vehicles contacts) -- confirmed api_version=4 for contact info, but could not access full docs (403)
- [MercadoLibre Questions API](https://developers.mercadolibre.com.ar/en_us/questions)
- [MercadoLibre Vehicle Contacts](https://developers.mercadolibre.com.ar/vehiculos-gestiona-preguntas-y-contactos)
- [WhatsApp Cloud API Template Messages](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates/)

### Tertiary (LOW confidence)
- ML api_version=4 phone field structure -- confirmed by multiple web search results but could not verify exact JSON schema (ML docs blocked with 403)
- Argentine phone number format from ML -- needs runtime validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing libraries
- Architecture: HIGH - extends existing patterns (adapter method, service layer, state machine)
- ML phone availability: LOW - confirmed in docs but untested with real account, may not work for all question types
- WhatsApp template format: HIGH - well-documented Meta API, verified payload structure
- Pitfalls: MEDIUM - identified from API documentation and codebase inspection

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable APIs, unlikely to change)
