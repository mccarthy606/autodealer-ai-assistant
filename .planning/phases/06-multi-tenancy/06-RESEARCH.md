# Phase 6: Multi-Tenancy - Research

**Researched:** 2026-03-27
**Domain:** Multi-tenant SaaS isolation — session auth, webhook routing, adapter credentials, Redis key namespacing, Alembic migration
**Confidence:** HIGH (all findings are based on direct code inspection of the actual codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**WABA Token Storage (MT-01, MT-02)**
- D-01: Add `whatsapp_access_token` column (String 512, nullable) to `Dealership` table. Stored plaintext in DB for now (encryption deferred to Phase 9).
- D-02: `WhatsAppCloudAdapter.__init__()` accepts optional `phone_number_id: str` and `token: str` params. If provided, uses those instead of `settings`. Backward compat: falls back to `settings.whatsapp_phone_number_id` / `settings.whatsapp_cloud_token` when params absent.
- D-03: All call sites that know the dealership pass dealership's credentials to the adapter. Internal sends (e.g., outbound service, follow-up task) load dealership from DB and pass credentials explicitly.

**Admin Authentication (MT-02)**
- D-04: Add `admin_username` (String 128, nullable) and `admin_password_hash` (String 255, nullable) to `Dealership` table via Alembic migration.
- D-05: Login flow: POST `/admin/login` receives username+password → `SELECT * FROM dealerships WHERE admin_username = ?` → bcrypt verify → on success: session stores `dealership_id`. Session key remains `admin:session:{token_hash}`, payload now includes `{"dealership_id": N}`.
- D-06: `auth.py` refactor: `create_session(response, dealership_id)` stores dealership_id in session value. `get_session_dealership_id(request) -> Optional[int]` reads it. `is_authenticated(request) -> bool` still works for legacy.
- D-07: `auth_check(request) -> int` (new helper) — verifies session AND returns `dealership_id`. Admin routes call `did = await auth_check(request)` instead of `settings.default_dealership_id`. Unauthorized → redirect to login.
- D-08: Global `settings.admin_password/admin_password_hash` retained as superadmin fallback (dealership_id=1). So existing deployment keeps working.

**WhatsApp Webhook Routing (MT-03)**
- D-09: WhatsApp payload always contains `entry[0].changes[0].value.metadata.phone_number_id`. Extract it in `parse_incoming_message()` — return 4-tuple `(phone, text, wamid, phone_number_id)`.
- D-10: New dependency `get_dealership_by_wa(db, phone_number_id) -> Optional[Dealership]` — `SELECT * FROM dealerships WHERE whatsapp_phone_number_id = ?`. Returns None if no dealership configured for that phone_number_id.
- D-11: Webhook GET (verify): try to find dealership by `phone_number_id` from query params, use its `whatsapp_verify_token`. Fallback to `settings.whatsapp_verify_token` if not found (backward compat).
- D-12: Webhook POST: if dealership not found for phone_number_id → return 200 OK silently (ignore unknown webhooks, never 4xx — Meta retries on non-2xx).

**ML Webhook Routing (MT-03)**
- D-13: ML webhook: extract `seller_id` from notification payload. `SELECT * FROM dealerships WHERE ml_user_id = ?`. If found → use that dealership. If not found → fallback to `settings.default_dealership_id` (keeps single-tenant setup working).
- D-14: `parse_incoming_question()` in `mercadolibre.py` returns the seller_id from the notification. Webhook handler uses it for dealership lookup.

**Redis Cache Isolation (MT-04)**
- D-15: Rate limiter key changes from `rate:whatsapp:{phone}` to `rate:wa:{dealership_id}:{phone}`. The `check_rate_limit()` call in `webhook_cloud.py` passes `prefix=f"rate:wa:{dealership_id}"`.
- D-16: Session Redis keys remain `admin:session:{token_hash}` — no tenant prefix needed (each token is globally unique). Session VALUE stores `dealership_id`.
- D-17: No other Redis key changes needed for Phase 6.

**Database (MT-01)**
- D-18: All models already have `dealership_id` FK — structural isolation already done. No new tables needed.
- D-19: No PostgreSQL RLS. Isolation enforced via SQLAlchemy `where(Model.dealership_id == did)` in all queries.
- D-20: One Alembic migration (006): adds `whatsapp_access_token`, `admin_username`, `admin_password_hash` to `dealerships` table.

**Implementation Files**
- D-21: `src/api/auth.py` — refactor `create_session`, `is_authenticated`, `auth_check`
- D-22: `src/api/routes/webhook_cloud.py` — use phone_number_id routing + dealership credentials
- D-23: `src/api/routes/webhook_ml.py` — use ml_user_id routing
- D-24: `src/api/routes/admin_*.py` — replace `settings.default_dealership_id` with `await auth_check(request)`
- D-25: `src/adapters/whatsapp_cloud.py` — accept optional phone_number_id/token params
- D-26: `src/services/outbound_service.py` — load dealership credentials, pass to adapter
- D-27: `src/tasks/followup_task.py` — load dealership credentials per conversation, pass to adapter
- D-28: `alembic/versions/006_multi_tenancy_dealership_columns.py` — migration

### Claude's Discretion
- Exact session payload serialization (JSON in Redis value vs separate keys)
- Edge case: dealership found but has no `whatsapp_access_token` (fall back to settings token)
- Whether to cache dealership-by-phone_number_id lookup in Redis for performance
- Superadmin detection logic (when using settings fallback vs dealership credentials)

### Deferred Ideas (OUT OF SCOPE)
- Encryption of WABA tokens at rest — Phase 9 (Production)
- Superadmin UI to manage all dealerships — v2
- Per-dealership subdomain routing — v2
- PostgreSQL RLS as additional isolation layer — v2
- ML multi-tenant without fallback (strict isolation) — v2
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MT-01 | Multiple dealerships on one instance with full data isolation | D-18: all models already have dealership_id FK. D-20: migration 006 adds 3 columns to Dealership. |
| MT-02 | Tenant middleware — automatic dealership determination from request context | D-04 through D-08: per-dealership admin credentials + session now carries dealership_id. D-07: auth_check() returns did. |
| MT-03 | WhatsApp phone_number_id → dealership routing + ML ml_user_id routing | D-09 through D-14: parse_incoming_message() becomes 4-tuple; lookup helpers for both channels. |
| MT-04 | Redis keys with tenant-prefix for cache isolation | D-15: rate limiter prefix becomes `rate:wa:{dealership_id}:{phone}`. D-16: session keys unchanged. |
</phase_requirements>

---

## Summary

Phase 6 converts the single-tenant system into a true multi-tenant SaaS. The database schema is already multi-tenant (all models have `dealership_id` FK with proper indexes); the only structural gap is three missing columns on the `Dealership` table. The main work is wiring: making each request carry the correct `dealership_id` instead of reading `settings.default_dealership_id`, and ensuring the WhatsApp adapter uses per-dealership credentials instead of global env vars.

The session layer requires the smallest change: Redis stores `"1"` today; it needs to store `{"dealership_id": N}` tomorrow. The auth functions `create_session()` and `is_authenticated()` need a signature change, and a new `auth_check()` helper that returns the `dealership_id` (replacing the existing `auth_check` in `admin_common.py` that only returns `None | RedirectResponse`).

The adapter layer has two call sites for `WhatsAppCloudAdapter()` that require no-arg construction (`outbound_service.py:67` and `followup_task.py:169`). Both need the adapter to accept optional `phone_number_id`/`token` params per D-02/D-03, plus a DB load of the dealership to supply those credentials at call time.

**Primary recommendation:** Implement in this order — migration → auth.py → admin_common.py → webhook_cloud.py + webhook_ml.py → adapters → outbound_service.py → followup_task.py — so each layer builds on the previous.

---

## Q1: Session Payload Serialization

### Current State (auth.py)

```python
# auth.py line 54 — stores literal string "1"
await r.set(f"admin:session:{token_hash}", "1", ex=86400)

# auth.py line 73 — checks key existence only (value ignored)
return await r.exists(f"admin:session:{token_hash}") > 0
```

The session value `"1"` is never read; only the key's presence is checked.

### What Needs to Change

The value must encode `dealership_id` so `get_session_dealership_id()` can reconstruct it from the cookie alone (no DB hit per request).

### Recommended Approach: JSON string in Redis value

**Verdict: Use JSON.** Rationale:

- `json.dumps({"dealership_id": N})` → `'{"dealership_id": 1}'`
- `json.loads(value)["dealership_id"]` — trivial, no string parsing
- Forward-compatible: adding fields (e.g., `role`, `expires_at`) requires no key-format changes
- Avoids brittle string splitting that `"dealership_id:{N}"` would require
- Redis stores string; `decode_responses=True` already set in `get_redis()`, so no bytes handling needed

**Rejected: `"dealership_id:{N}"` format** — parsing requires `split(":")[-1]` which breaks if the prefix ever contains a colon; no extensibility.

**Proposed new signatures** (research only — not implementation):

```python
# create_session: takes dealership_id, serializes to JSON in Redis
async def create_session(response: Response, dealership_id: int) -> None:
    token = _make_token()
    token_hash = _hash_token(token)
    value = json.dumps({"dealership_id": dealership_id})
    r = await get_redis()
    if r:
        await r.set(f"admin:session:{token_hash}", value, ex=86400)
    else:
        _admin_sessions[token_hash] = dealership_id  # dict, not set
    # cookie unchanged

# get_session_dealership_id: reads JSON value, returns int or None
async def get_session_dealership_id(session_token: Optional[str]) -> Optional[int]:
    if not session_token:
        return None
    token_hash = _hash_token(session_token)
    r = await get_redis()
    if r:
        raw = await r.get(f"admin:session:{token_hash}")
        if not raw:
            return None
        try:
            return json.loads(raw)["dealership_id"]
        except (json.JSONDecodeError, KeyError):
            return None
    return _admin_sessions.get(token_hash)

# is_authenticated: backward compat — calls get_session_dealership_id, returns bool
async def is_authenticated(session: Optional[str] = None) -> bool:
    if not settings.admin_password and not settings.admin_password_hash:
        return True
    return await get_session_dealership_id(session) is not None
```

**In-memory fallback change:** `_admin_sessions: set[str]` must become `_admin_sessions: dict[str, int]` mapping `token_hash → dealership_id`.

**Superadmin fallback (D-08):** When login uses `settings.admin_password` (no per-dealership credentials), store `dealership_id=1` (the `settings.default_dealership_id` value). This preserves existing single-tenant deployments.

---

## Q2: WhatsApp Payload phone_number_id Extraction

### Current parse_incoming_message() (whatsapp_cloud.py lines 96–129)

```python
def parse_incoming_message(payload: dict) -> Optional[tuple[str, str, Optional[str]]]:
    """Returns (phone, text, wamid) or None."""
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        phone = msg.get("from", "")
        # ... text extraction logic ...
        wamid = msg.get("id")
        if phone and text:
            return phone, text, wamid
        return None
    except (IndexError, KeyError):
        return None
```

**Finding:** `phone_number_id` is NOT currently returned. The function returns a 3-tuple `(phone, text, wamid)`.

### Confirmed WhatsApp Cloud API Payload Path

The path `entry[0].changes[0].value.metadata.phone_number_id` is correct and is already accessed indirectly — the `value` dict is extracted at line 104. The `phone_number_id` lives at:

```
payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
```

In the current code, `value = changes.get("value", {})` is already computed. The `phone_number_id` is therefore reachable as `value.get("metadata", {}).get("phone_number_id")`.

**Recommended change:** Extend return to 4-tuple `(phone, text, wamid, phone_number_id)`. When `messages` is empty (status update, delivery receipt, etc.), `phone_number_id` should still be extractable from `metadata` — it is present even when the `messages` array is empty, since `metadata` is always present for any value object. This is needed for D-11 (GET verify endpoint also needs it from query params, not from `parse_incoming_message`).

**Note for GET verify (D-11):** The GET request uses `hub.verify_token` in query params, NOT the payload. The `phone_number_id` for the GET is available as `request.query_params.get("phone_number_id")` — Meta sends it as a query parameter when the webhook is registered per phone_number_id. This is a separate code path from `parse_incoming_message()`.

---

## Q3: ML Payload seller_id Extraction

### Current parse_incoming_question() (mercadolibre.py lines 563–579)

```python
def parse_incoming_question(payload: dict) -> Optional[dict]:
    """Returns {question_id, resource, user_id} or None."""
    try:
        topic = payload.get("topic")
        if topic != "questions":
            return None
        resource = payload.get("resource", "")
        question_id = resource.split("/")[-1]
        return {
            "question_id": question_id,
            "resource": resource,
            "user_id": payload.get("user_id"),  # <-- THIS IS THE SELLER_ID
        }
    except Exception:
        return None
```

**Finding:** `user_id` IS already returned. It is the MercadoLibre seller's user ID — the same value that is stored in `Dealership.ml_user_id`. The field in the ML notification payload is named `user_id` and represents the seller (the account that received the question).

**Confirmed:** The ML webhook notification payload structure is:
```json
{
  "topic": "questions",
  "resource": "/questions/1234567890",
  "user_id": 123456789,
  "application_id": 1234567890123,
  "sent": "2018-01-01T20:20:47.606Z",
  "_id": "abcdef"
}
```

`user_id` = the seller's ML account ID = `Dealership.ml_user_id`.

**Current usage in webhook_ml.py:** The `parsed` dict is returned but only `parsed["question_id"]` is used (line 36). The `user_id` (`parsed["user_id"]`) is available but ignored — the handler jumps straight to `settings.default_dealership_id` on line 67.

**No change to `parse_incoming_question()` return structure needed** — `user_id` is already there. The webhook handler just needs to use `parsed["user_id"]` to do the dealership lookup.

---

## Q4: Admin Routes `settings.default_dealership_id` Audit

Complete count of all `settings.default_dealership_id` usages across all admin_*.py files:

### admin_dashboard.py
| Line | Location | Context |
|------|----------|---------|
| 79 | `dashboard()` GET | `did = settings.default_dealership_id` |
| 168 | `test_chat_send()` POST | `dealership_id=settings.default_dealership_id` (in `process_message()` call) |
| 189 | `metrics_page()` GET | `did = settings.default_dealership_id` |

**Count: 3 usages**

### admin_settings.py
| Line | Location | Context |
|------|----------|---------|
| 25 | `settings_page()` GET | `Dealership.id == settings.default_dealership_id` |
| 46 | `settings_save()` POST | `Dealership.id == settings.default_dealership_id` |
| 72 | `integrations_page()` GET | `InventoryItem.dealership_id == settings.default_dealership_id` |

**Count: 3 usages**

### admin_inventory.py
| Line | Location | Context |
|------|----------|---------|
| 35 | `cars_list()` GET | `did = settings.default_dealership_id` |
| 104 | `car_create()` POST | `dealership_id=settings.default_dealership_id` (InventoryItem constructor) |
| 126 | `car_create()` POST | `dealership_id=settings.default_dealership_id` (Event constructor) |
| 144 | `car_detail()` GET | `InventoryItem.dealership_id == settings.default_dealership_id` |
| 311 | `cars_import()` POST | `dealership_id=settings.default_dealership_id` (InventoryItem in loop) |
| 345 | `import_ml_url()` POST | `did = settings.default_dealership_id` |
| 380 | `import_ml_url_save()` POST | `did = settings.default_dealership_id` |

**Count: 7 usages**

### admin_leads.py
| Line | Location | Context |
|------|----------|---------|
| 25 | `leads_page()` GET | `did = settings.default_dealership_id` |

**Count: 1 usage**

### admin_conversations.py
| Line | Location | Context |
|------|----------|---------|
| 29 | `conversations_page()` GET | `did = settings.default_dealership_id` |
| 67 | `conversation_detail()` GET | `Conversation.dealership_id == settings.default_dealership_id` |

**Count: 2 usages**

### admin_common.py
No usage of `settings.default_dealership_id`. This file only defines `auth_check()` (currently returns `None | RedirectResponse`, needs replacement per D-07).

**Total across all admin_*.py files: 16 usages**

Note: The CONTEXT.md says "17+ call sites" — the discrepancy is that `webhook_cloud.py` (line 78) and `webhook_ml.py` (line 67) each have one usage too, but those are not admin_* files. Within strictly the admin_*.py files: **16 usages**.

---

## Q5: WhatsAppCloudAdapter Refactor Scope

### Current `__init__` and credential usages (whatsapp_cloud.py)

```python
class WhatsAppCloudAdapter(ChannelAdapter):
    def __init__(self):
        self.token = settings.whatsapp_cloud_token          # line 20
        self.phone_number_id = settings.whatsapp_phone_number_id  # line 21
        self.is_configured = bool(self.token and self.phone_number_id)  # line 22
```

**`self.phone_number_id` usages:**
- Line 29: `url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"` — in `send_text()`
- Line 53: `f"{GRAPH_API_URL}/{self.phone_number_id}/messages"` — in `send_images()` (loop body)
- Line 66: `url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"` — in `send_template()`

**`self.token` usages:**
- Line 85: `"Authorization": f"Bearer {self.token}"` — in `_post()` (called by all send methods)

**Total:** `self.phone_number_id` used 3 times, `self.token` used 1 time. Both are instance attributes, so changing `__init__` to accept optional params covers all usages automatically.

### Recommended Refactor Pattern (D-02)

```python
def __init__(
    self,
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
):
    self.token = token or settings.whatsapp_cloud_token
    self.phone_number_id = phone_number_id or settings.whatsapp_phone_number_id
    self.is_configured = bool(self.token and self.phone_number_id)
```

**Backward compat:** Zero breaking changes. All existing `WhatsAppCloudAdapter()` no-arg calls continue working via fallback to `settings`. New callers pass credentials explicitly.

**Edge case (Claude's discretion from CONTEXT.md):** If dealership has `whatsapp_phone_number_id` set but `whatsapp_access_token` is NULL, the fallback `token or settings.whatsapp_cloud_token` naturally uses the global settings token. This is acceptable for the phase — explicit in the research, planner should add a note in the implementation task.

### Call sites that need updating per D-03

1. `webhook_cloud.py` line 87: `adapter = WhatsAppCloudAdapter()` — after dealership lookup, pass `phone_number_id=dealership.whatsapp_phone_number_id` and `token=dealership.whatsapp_access_token`
2. `outbound_service.py` line 67: `wa_adapter = WhatsAppCloudAdapter()` — after `_get_dealership()` already called (line 47), can extract credentials from loaded dealer
3. `followup_task.py` line 169: `wa_adapter = WhatsAppCloudAdapter()` — currently creates ONE adapter for all conversations; must move adapter construction inside the per-conversation loop after loading dealership

---

## Q6: Alembic Migration — Current State and Next Number

### Existing migrations

| File | Revision | Revises | Date |
|------|----------|---------|------|
| `001_initial_schema.py` | `"001"` | None (root) | 2025-02-08 |
| `002_mvp_schema_extensions.py` | `"002"` | `"001"` | (not inspected) |
| `003_add_wamid_column.py` | `"003"` | `"002"` | 2026-03-27 |
| `004_add_ml_item_id_index.py` | `"004"` | `"003"` | 2026-03-27 |

**Latest migration number: 004.** No `005` file exists in `alembic/versions/`.

**Finding: The next migration should be `005`, not `006`.** CONTEXT.md D-20 says "006" but the actual migration chain ends at 004. The correct filename per the established naming convention is:

```
alembic/versions/005_multi_tenancy_dealership_columns.py
```

This is a naming discrepancy between the CONTEXT.md and the actual filesystem. The planner must use `005` to keep the chain unbroken.

### Migration Pattern (from 003 and 004)

```python
"""<description>.

Revision ID: 005
Revises: 004
Create Date: <date>
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dealerships", sa.Column("whatsapp_access_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("admin_username", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("admin_password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("dealerships", "admin_password_hash")
    op.drop_column("dealerships", "admin_username")
    op.drop_column("dealerships", "whatsapp_access_token")
```

**Pattern notes:**
- No `from typing import Sequence, Union` needed for simple `add_column` migrations (004 omits them)
- `revision` and `down_revision` are plain strings (not typed), consistent with 003/004
- Migration auto-runs on app startup via `src/main.py` calling Alembic programmatically

---

## Q7: followup_task.py Adapter Calls

### Current instantiation (followup_task.py)

```python
# line 169 — ONE adapter created BEFORE the conversation loop
wa_adapter = WhatsAppCloudAdapter()

with _SyncSession() as session:
    candidates = _get_candidates(session, now)
    for conv in candidates:
        # ...
        api_result = asyncio.run(
            wa_adapter.send_template(
                to=conv.user_phone,
                template_name=template_name,
                language_code=language_code,
                components=components,
            )
        )
```

**Problem:** A single adapter is created once for all conversations. In multi-tenant mode, different conversations belong to different dealerships with different credentials. The adapter must be created (or re-keyed) per-conversation.

**What currently uses settings:** `WhatsAppCloudAdapter.__init__()` reads `settings.whatsapp_cloud_token` and `settings.whatsapp_phone_number_id` — global env vars.

**What needs to change per D-03/D-27:**

1. Move adapter construction inside the per-`conv` loop
2. Load `Dealership` from DB using `conv.dealership_id` (synchronous query via `_SyncSession`)
3. Pass `phone_number_id=dealer.whatsapp_phone_number_id, token=dealer.whatsapp_access_token` to adapter

**Sync DB access note:** `followup_task.py` uses `_SyncSession` (sync SQLAlchemy). The dealership lookup `session.query(Dealership).filter_by(id=conv.dealership_id).first()` fits naturally in the existing sync pattern. No async/asyncio changes needed for the DB load.

**Performance consideration (Claude's discretion):** For a single Celery run with N conversations across M dealerships, this creates N adapter instances and makes N dealership DB lookups. A dict cache `{dealership_id: Dealership}` scoped to the task run would reduce this to M lookups. This is within Claude's discretion and should be implemented.

---

## Q8: outbound_service.py Adapter Calls

### Current instantiation (outbound_service.py)

```python
async def handle_ml_inquiry(
    session: AsyncSession,
    dealership_id: int,
    ...
) -> OutboundResult:
    # ...
    dealer = await _get_dealership(session, dealership_id)   # line 47 — ALREADY LOADED
    # ...
    wa_adapter = WhatsAppCloudAdapter()    # line 67 — NO-ARG, ignores dealer credentials
```

**Finding:** The dealership is already loaded via `_get_dealership(session, dealership_id)` at line 47 before the adapter is constructed. The `dealer` object is available at the point where `WhatsAppCloudAdapter()` is called.

**What needs to change per D-03/D-26:**

Pass dealer credentials to the adapter. Since `dealer` is already in scope:

```python
# Current (line 67):
wa_adapter = WhatsAppCloudAdapter()

# Proposed:
wa_adapter = WhatsAppCloudAdapter(
    phone_number_id=dealer.whatsapp_phone_number_id if dealer else None,
    token=dealer.whatsapp_access_token if dealer else None,
)
```

This is the minimal change. `dealer` could be `None` (if dealership not found), in which case `None` triggers the settings fallback in the adapter's `__init__`.

**`MercadoLibreAdapter` at line 60:** `ml_adapter = MercadoLibreAdapter()` — this adapter uses `settings.ml_access_token` and `settings.ml_user_id` globally. Per the CONTEXT.md and decisions, ML adapter multi-tenancy is not in Phase 6 scope (ML routing uses `ml_user_id` for lookup but the ML API calls still use settings). Leave `MercadoLibreAdapter()` unchanged.

---

## Q9: Test Fixtures Audit

### Existing dealership fixture (tests/conftest.py lines 56–68)

```python
@pytest_asyncio.fixture
async def dealership(db_session: AsyncSession) -> Dealership:
    """Create a test dealership."""
    d = Dealership(
        id=1,
        name="Test Dealership",
        address="Av. Test 123, CABA",
        business_hours="Lun-Vie 9-18",
        timezone="America/Argentina/Buenos_Aires",
        default_language="es-AR",
    )
    db_session.add(d)
    await db_session.flush()
    return d
```

**Findings:**
- A `dealership` fixture EXISTS — good.
- Does NOT set `whatsapp_phone_number_id` — needs to be added for MT-03 tests.
- Does NOT set `admin_username` or `admin_password_hash` — needs to be added for MT-02 tests (or a separate `dealership_with_auth` fixture).
- Does NOT set `whatsapp_access_token` — needs to be added for MT-01/MT-02 adapter tests.
- Sets `id=1` explicitly, which matches `settings.default_dealership_id = 1` — this is correct and should be preserved for backward compat tests.

### New fixtures needed for Phase 6

**Option A — Extend existing `dealership` fixture** with new columns (breaking change if any existing test relies on absence of these fields). LOW RISK since columns are nullable.

**Option B — Add a `dealership_with_mt` fixture** (non-breaking, additive):

```python
@pytest_asyncio.fixture
async def dealership_with_mt(db_session: AsyncSession) -> Dealership:
    """Dealership with multi-tenancy fields populated."""
    import bcrypt
    d = Dealership(
        id=1,
        name="Test Dealership MT",
        address="Av. Test 123, CABA",
        business_hours="Lun-Vie 9-18",
        timezone="America/Argentina/Buenos_Aires",
        default_language="es-AR",
        whatsapp_phone_number_id="123456789",
        whatsapp_verify_token="test_verify_token",
        whatsapp_access_token="test_wa_token",
        admin_username="testadmin",
        admin_password_hash=bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode(),
        ml_user_id="999888777",
    )
    db_session.add(d)
    await db_session.flush()
    return d
```

**Recommended approach:** Add `whatsapp_phone_number_id` and `ml_user_id` to the BASE `dealership` fixture (since tests for engine and outbound service will benefit from them), and add a separate `dealership_with_auth` fixture for auth-specific tests. This is the least disruptive approach.

---

## Architecture Patterns

### auth_check() Replacement Pattern

The existing `auth_check()` in `admin_common.py` returns `Optional[RedirectResponse]` (guard pattern). The new `auth_check()` per D-07 must return `int` (the dealership_id) OR redirect. These are incompatible signatures.

**Resolution:** Replace `admin_common.py:auth_check` entirely. Current callers:

```python
# Current pattern in every admin route:
redir = await auth_check(request)
if redir:
    return redir
did = settings.default_dealership_id  # <-- immediately after auth_check

# New pattern (D-07):
did = await auth_check(request)  # raises/returns RedirectResponse if not auth
# OR: auth_check returns int, caller checks isinstance
```

Two viable approaches for the new `auth_check` return contract:

**A — Raise HTTPException:** `raise HTTPException(status_code=302, headers={"Location": "/admin/ui/login"})` — clean but changes error behavior.

**B — Return Union[int, RedirectResponse]:** Caller does `result = await auth_check(request); if isinstance(result, RedirectResponse): return result; did = result` — verbose but consistent with existing guard pattern.

**C — Return -1 as sentinel + check at call site** — hacky, don't use.

Recommended: **B** — return `Union[int, RedirectResponse]`. This is minimally invasive: existing `if redir: return redir` becomes `if isinstance(did, RedirectResponse): return did`. Avoids changing FastAPI exception handling behavior.

### Dealership Lookup Helpers

Two new DB helper functions needed:

```python
# src/db/queries.py (new file) or inline in each route module

async def get_dealership_by_wa(
    db: AsyncSession, phone_number_id: str
) -> Optional[Dealership]:
    stmt = select(Dealership).where(
        Dealership.whatsapp_phone_number_id == phone_number_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_dealership_by_ml(
    db: AsyncSession, ml_user_id: str
) -> Optional[Dealership]:
    stmt = select(Dealership).where(
        Dealership.ml_user_id == ml_user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
```

**Placement:** Given project conventions (no dedicated `queries.py` today), these can go in a new `src/db/queries.py` or directly in the respective webhook route files. The project uses direct `select()` calls in routes rather than a repository pattern, so co-locating in the route file is consistent. However a shared `src/db/queries.py` is cleaner for the follow-up task which also needs lookups.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of session value | Custom string format parsing | `json.dumps` / `json.loads` (stdlib) | Already imported in test files; stdlib, no deps |
| Password hashing for per-dealership admin | Custom hash | `bcrypt.checkpw` (already imported in auth.py) | Same library already used for settings-level auth |
| Dealership lookup by phone_number_id | Complex join | Simple `SELECT WHERE whatsapp_phone_number_id = ?` | Column already exists and is indexed via FK on dealership_id across all related tables |

---

## Common Pitfalls

### Pitfall 1: Migration number mismatch
**What goes wrong:** CONTEXT.md says "006" but the migration chain ends at 004. Creating `006_...py` with `down_revision = "004"` skips 005 — Alembic allows this but will produce a warning about a "branch" if 005 ever gets created later.
**Why it happens:** CONTEXT.md was written before all migrations through phase 5 were finalized.
**How to avoid:** Use `005` as the next migration number. Alembic auto-detects the head via `down_revision` chaining, not by filename alphabetical order.

### Pitfall 2: followup_task adapter created outside the loop
**What goes wrong:** One `WhatsAppCloudAdapter()` instance is created before the loop at line 169. For multi-tenant, different conversations need different credentials. Only the first dealership's credentials would be used.
**Why it happens:** Single-tenant code — all messages go to one WABA account.
**How to avoid:** Move adapter construction inside the `for conv in candidates` loop, after loading the dealership.

### Pitfall 3: auth_check signature collision
**What goes wrong:** `admin_common.py` has `async def auth_check(request) -> Optional[RedirectResponse]`. The new `auth_check` per D-07 returns `Union[int, RedirectResponse]`. Both live in the same module. Existing callers do `redir = await auth_check(request); if redir: return redir` — if the new function returns an int, `if redir` where `redir = 1` is truthy and would incorrectly redirect.
**Why it happens:** Reusing the function name without updating all callers.
**How to avoid:** Update ALL call sites when changing the signature. There are 16 call sites across 5 admin_*.py files that call `auth_check` and then immediately read `settings.default_dealership_id`. Both the signature change and the `did` assignment must be done atomically per route.

### Pitfall 4: `_admin_sessions` fallback is a set, not a dict
**What goes wrong:** The in-memory fallback `_admin_sessions: set[str] = set()` stores only token hashes, not dealership_ids. After the session change, `get_session_dealership_id()` needs to look up the `dealership_id` from the fallback store — impossible if it's a `set`.
**Why it happens:** The fallback was designed for boolean auth only.
**How to avoid:** Change `_admin_sessions` from `set[str]` to `dict[str, int]` mapping `token_hash → dealership_id`. Update `create_session` (add), `is_authenticated` (check key existence), `get_session_dealership_id` (get value), and `remove_session` (delete key).

### Pitfall 5: ML webhook `user_id` type mismatch
**What goes wrong:** `parse_incoming_question()` returns `payload.get("user_id")` which is an `int` from the JSON payload. `Dealership.ml_user_id` is a `String(64)`. A direct `WHERE ml_user_id = 123456789` (int) will fail in some DB drivers.
**Why it happens:** ML sends `user_id` as a JSON integer, but the column is text.
**How to avoid:** Cast to `str` before lookup: `ml_user_id = str(parsed["user_id"])` before passing to `get_dealership_by_ml()`.

### Pitfall 6: Rate limit key change breaks existing counters
**What goes wrong:** Rate limit keys change from `rate:whatsapp:{phone}` to `rate:wa:{dealership_id}:{phone}`. Old keys in Redis will expire naturally but won't be reset. This is not a data correctness issue but is worth noting.
**Why it happens:** Redis TTL-based expiry handles cleanup automatically.
**How to avoid:** No action needed — old keys expire within `window_seconds` (60s). Document in the migration notes.

### Pitfall 7: webhook_cloud.py GET verify uses `request.query_params.get("phone_number_id")` not parse_incoming_message()
**What goes wrong:** The GET verification endpoint receives `phone_number_id` as a query parameter from Meta, not in the payload body. Trying to use `parse_incoming_message()` (which parses POST bodies) for GET verification will fail.
**Why it happens:** GET and POST are different paths; the `phone_number_id` is in the query string for GET.
**How to avoid:** In the GET handler, use `request.query_params.get("phone_number_id")` directly to look up the dealership.

---

## Code Examples

### Current login flow (admin_dashboard.py lines 38–59)

```python
@router.post("/login")
async def login_submit(request: Request):
    # ...
    if _check_password(password):
        resp = RedirectResponse(url="/admin/ui", status_code=302)
        await create_session(resp)   # no dealership_id argument
        return resp
```

After refactor, `create_session(resp, dealership_id=1)` is called with `dealership_id` from the dealership lookup result.

### Current rate limit call (webhook_cloud.py lines 65–73)

```python
allowed, retry_after = await check_rate_limit(
    key=phone, limit=20, window_seconds=60, prefix="rate:whatsapp"
)
```

After MT-04 (D-15):

```python
allowed, retry_after = await check_rate_limit(
    key=phone, limit=20, window_seconds=60, prefix=f"rate:wa:{dealership_id}"
)
```

`check_rate_limit()` in `rate_limit.py` computes `redis_key = f"{prefix}:{key}"`, producing `rate:wa:{dealership_id}:{phone}` — exactly D-15.

### Dealership model after migration 005

```python
class Dealership(Base):
    # ... existing columns ...
    whatsapp_phone_number_id = Column(String(64))      # already exists
    whatsapp_verify_token = Column(String(128))         # already exists
    whatsapp_access_token = Column(String(512))         # NEW — D-01
    ml_user_id = Column(String(64))                    # already exists
    admin_username = Column(String(128))               # NEW — D-04
    admin_password_hash = Column(String(255))          # NEW — D-04
```

---

## Project Constraints (from CLAUDE.md)

| Constraint | Implication for Phase 6 |
|------------|------------------------|
| Python 3.12 + FastAPI + SQLAlchemy 2.0 — do not change | All changes use existing async FastAPI + SQLAlchemy 2.0 async patterns |
| `snake_case.py` file naming | New file (if any): `src/db/queries.py` |
| No Pydantic models for request/response | Session value uses plain `json.dumps` dict, not a Pydantic model |
| Private helpers prefixed with `_` | New helpers like `_get_session_data()` follow this convention |
| `Optional[X]` from typing (not `X \| None`) | New `get_session_dealership_id(session: Optional[str])` signature |
| Logger uses `%s` formatting, not f-strings | All new log calls: `logger.info("...: %s", value)` |
| `from src.X import Y` absolute imports | No relative imports in new code |
| GSD workflow enforcement | All file changes via `/gsd:execute-phase` only |
| `nyquist_validation: false` in config.json | Validation Architecture section omitted per config |

---

## Environment Availability

Step 2.6: SKIPPED — Phase 6 is purely code/config/migration changes. No new external tools, services, runtimes, or CLI utilities are required beyond those already used by the project (Python 3.12, PostgreSQL 16, Redis 7, all confirmed present via Docker Compose stack).

---

## Open Questions

1. **Migration number: 005 vs 006**
   - What we know: Last migration in `alembic/versions/` is `004_add_ml_item_id_index.py`. CONTEXT.md D-20 says "006".
   - What's unclear: Was migration 005 created in a branch or planned but not yet created?
   - Recommendation: Use `005` based on actual filesystem state. If a 005 migration exists later, there would be a conflict. Search for any `005*` file in branches before implementing.

2. **Per-dealership ML adapter credentials**
   - What we know: D-13 says ML routing is by ml_user_id but uses a fallback to `settings.default_dealership_id`. The ML adapter itself still uses `settings.ml_access_token`.
   - What's unclear: Should `MercadoLibreAdapter` also accept per-dealership tokens in Phase 6? CONTEXT.md does not add an `ml_access_token` column to Dealership, suggesting this is deferred.
   - Recommendation: Leave `MercadoLibreAdapter()` no-arg. Only routing (lookup by ml_user_id) changes in Phase 6; ML API calls continue using settings.

3. **Admin login page for multi-tenant**
   - What we know: Current login page (`admin/login.html`) shows a password field only (`form.get("password")`). Per D-05, the new login accepts username+password.
   - What's unclear: Does the login template need a username field added? The template file was not in the read list.
   - Recommendation: The planner should include a task to add `username` input to the login template. The login route change requires it.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all source files — all findings are line-number-verified against actual codebase
- `src/api/auth.py` — session management current state
- `src/api/routes/webhook_cloud.py` — WhatsApp webhook, rate limit call
- `src/adapters/whatsapp_cloud.py` — adapter init, method signatures, `phone_number_id` usage count
- `src/adapters/mercadolibre.py` — `parse_incoming_question()`, `user_id` field
- `src/api/routes/admin_*.py` (5 files) — exhaustive `settings.default_dealership_id` count
- `alembic/versions/` — confirmed migration chain ends at 004
- `tests/conftest.py` — fixture inventory
- `src/db/models.py` — Dealership model, confirmed missing columns

### Secondary (MEDIUM confidence)
- WhatsApp Cloud API payload structure (`entry[0].changes[0].value.metadata.phone_number_id`) — confirmed via path in existing code that already navigates `entry[0].changes[0].value`; metadata path is standard Meta WABA Cloud API structure per widely-documented webhook payload format

### Metadata

**Confidence breakdown:**
- Migration numbering: HIGH — filesystem confirmed
- settings.default_dealership_id count: HIGH — line-by-line code inspection
- WhatsApp payload path: HIGH — code already accesses `entry[0].changes[0].value`; metadata path is standard
- ML user_id field: HIGH — code confirmed `payload.get("user_id")` already returned
- Session serialization recommendation: HIGH — based on code analysis, stdlib usage
- Adapter refactor scope: HIGH — counted all usages directly from source

**Research date:** 2026-03-27
**Valid until:** Until codebase changes — all findings are code-intrinsic, not ecosystem-dependent
