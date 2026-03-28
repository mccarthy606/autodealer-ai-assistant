# Phase 8: Billing (Lemon Squeezy) - Research

**Researched:** 2026-03-27
**Domain:** Lemon Squeezy webhooks, SQLAlchemy Alembic migrations, FastAPI dependency injection
**Confidence:** HIGH (payload structure cross-verified from multiple independent sources)

---

## Summary

This phase adds Lemon Squeezy subscription billing to the AutoDealer AI platform. Six nullable columns land on the `dealerships` table via a single Alembic migration (007). A refactored `webhook_lemon.py` handler parses five lifecycle events, links them to dealerships via `meta.custom_data.dealership_id`, and writes subscription state to the DB. A pure-Python `is_subscription_active()` helper gates the WhatsApp inbound path and the Celery follow-up task. The admin settings page gains a read-only subscription status badge.

All decisions are locked in CONTEXT.md. The primary research value is the exact Lemon Squeezy JSON payload paths (verified from three independent sources) and answers to the four technical integration questions the planner needs.

**Primary recommendation:** Use `.get()` defensively throughout the webhook handler because `trial_ends_at` is `null` when the subscription is not in trial, and `subscription_payment_failed` delivers a `subscription_invoices` object (not `subscriptions`) — the subscription ID is at `data.attributes.subscription_id`, not `data.id`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add subscription columns directly to `Dealership` table (NOT a separate table). One dealership = one subscription.
- **D-02:** New columns: `subscription_status VARCHAR(32)`, `subscription_id VARCHAR(128)`, `ls_customer_id VARCHAR(128)`, `plan VARCHAR(64)`, `trial_ends_at DATETIME`, `grace_period_ends_at DATETIME` — all nullable.
- **D-03:** Migration file: `007_billing_subscription_columns.py` (next in chain after 006).
- **D-04:** Link via `custom_data.dealership_id` in LS checkout — `payload["meta"]["custom_data"]["dealership_id"]`.
- **D-05:** Extract `dealership_id` from `meta.custom_data.dealership_id` (as integer).
- **D-06:** Missing `custom_data.dealership_id` or unknown dealership → log warning + return 200 OK.
- **D-07:** Handle: `subscription_created`, `subscription_updated`, `subscription_payment_failed`, `subscription_cancelled`, `subscription_expired`.
- **D-08:** LS status mapping: `on_trial`→`trial`, `active`→`active`, `past_due`→`past_due`, `paused`→`past_due`, `unpaid`→`past_due`, `cancelled`→`cancelled`, `expired`→`expired`.
- **D-09:** Webhook handler needs `db: AsyncSession = Depends(get_db)`.
- **D-10:** 7-day trial. Credit card captured upfront by LS.
- **D-11:** `trial_ends_at` from LS `attributes.trial_ends_at`; fallback `now + 7 days` if null on creation.
- **D-12:** On `subscription_payment_failed`: `grace_period_ends_at = now() + timedelta(days=7)`.
- **D-13:** During grace period (`past_due` + `now < grace_period_ends_at`): service continues.
- **D-14:** After grace period: block service.
- **D-15:** Gate in `webhook_cloud.py` after `get_dealership_by_wa()`, before `process_message()`.
- **D-16:** Active if: `status in ("trial", "active")` OR (`status == "past_due"` AND `grace_period_ends_at > now()`).
- **D-17:** `is_subscription_active(dealership)` in `src/services/billing.py`.
- **D-18:** `webhook_ml.py` NOT gated.
- **D-19:** `subscription_status is None` → BLOCK. Exception: `trial_ends_at` in future → treat as trial.
- **D-20:** `followup_task.py` checks subscription — skip non-active dealerships.
- **D-21:** Read-only subscription status badge in `settings.html`. No management UI.
- **D-22 to D-28:** File list: `007_billing_subscription_columns.py`, `models.py`, `billing.py`, `webhook_lemon.py`, `webhook_cloud.py`, `followup_task.py`, `admin_settings.py` + `settings.html`.

### Claude's Discretion
- Exact LS payload field paths for subscription data (`attributes.status`, `attributes.trial_ends_at`, etc.) — verify from LS docs or handle defensively with `.get()`
- Whether to also gate `webhook_ml.py` outbound send or only `webhook_cloud.py`
- Exact settings.html additions for subscription display
- Error handling if DB update fails during webhook processing

### Deferred Ideas (OUT OF SCOPE)
- Checkout link generation from admin UI
- Invoice/payment history display
- Usage limits per plan (max N conversations)
- Multiple plans (basic/pro) with feature gating
- Automatic email on trial expiry
- Webhook retry/replay handling
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BILL-01 | Subscription model: plan → tenant → status columns | Migration pattern (Q2), model column structure (Q6 fixtures), LS status values (Q1) |
| BILL-02 | Lemon Squeezy webhook handler for lifecycle events | Full payload paths documented (Q1), DB dependency pattern safe (Q3) |
| BILL-03 | Subscription check before processing messages | Gate insertion point identified in webhook_cloud.py (Q4), pure-Python helper safe in sync context (Q5) |
| BILL-04 | Grace period on payment failure | `subscription_payment_failed` payload type confirmed (Q1), grace field pattern established |
</phase_requirements>

---

## Q1: Lemon Squeezy Webhook Payload Structure

**Confidence:** HIGH — cross-verified from: official LS dev blog examples, NdoleStudio/lemonsqueezy-go type definitions, lmsqueezy/nextjs-billing official sample repo, and DEV Community real payload dumps.

### Top-Level Envelope (all events)

```json
{
  "meta": {
    "event_name": "subscription_created",
    "webhook_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "test_mode": true,
    "custom_data": {
      "dealership_id": "42"
    }
  },
  "data": {
    "type": "subscriptions",
    "id": "123456",
    "attributes": { ... },
    "relationships": { ... }
  }
}
```

**Key meta paths:**
- `payload["meta"]["event_name"]` — string, e.g. `"subscription_created"`
- `payload["meta"]["custom_data"]["dealership_id"]` — string (must cast to `int`). Key exists only if custom data was passed at checkout. Always use `.get()`.

### subscription_created and subscription_updated

Both deliver `data.type = "subscriptions"`.

```python
attrs = payload["data"]["attributes"]

subscription_id  = payload["data"]["id"]          # string, e.g. "123456"
customer_id      = attrs["customer_id"]            # integer
status           = attrs["status"]                 # "on_trial" | "active" | "past_due" | "unpaid" | "paused" | "cancelled" | "expired"
trial_ends_at    = attrs.get("trial_ends_at")      # ISO 8601 string OR null
variant_name     = attrs.get("variant_name")       # string, e.g. "Default" or "Pro"
renews_at        = attrs.get("renews_at")          # ISO 8601 string
ends_at          = attrs.get("ends_at")            # ISO 8601 string or null
cancelled        = attrs.get("cancelled", False)   # bool
```

Full confirmed attributes list (from real payload dumps):
`store_id`, `order_id`, `order_item_id`, `product_id`, `variant_id`, `product_name`, `variant_name`, `user_name`, `user_email`, `status`, `status_formatted`, `card_brand`, `card_last_four`, `payment_processor`, `pause`, `cancelled`, `trial_ends_at`, `billing_anchor`, `renews_at`, `ends_at`, `created_at`, `updated_at`, `test_mode`, `first_subscription_item`.

**Status values (confirmed from Go library source and official docs):**
| LS value | Our mapping | Notes |
|----------|-------------|-------|
| `on_trial` | `trial` | `trial_ends_at` is a date string |
| `active` | `active` | `trial_ends_at` is null |
| `past_due` | `past_due` | Payment failed, retrying |
| `paused` | `past_due` | Treat same as past_due per D-08 |
| `unpaid` | `past_due` | After all retries exhausted |
| `cancelled` | `cancelled` | Customer or admin cancelled |
| `expired` | `expired` | Past cancellation date |

**trial_ends_at behavior:**
- When `status == "on_trial"`: ISO 8601 datetime string, e.g. `"2026-04-03T13:43:48.000000Z"`
- All other statuses: `null`
- Confirmed by official docs: "If the subscription has a free trial, `trial_ends_at` will be an ISO 8601 formatted date-time string indicating when the trial period ends. For all other status values, this will be null."

### subscription_payment_failed — CRITICAL DIFFERENCE

**This event delivers a `subscription_invoices` object, NOT a `subscriptions` object.**

```json
{
  "meta": {
    "event_name": "subscription_payment_failed",
    "custom_data": { "dealership_id": "42" }
  },
  "data": {
    "type": "subscription_invoices",
    "id": "789",
    "attributes": {
      "store_id": 1,
      "subscription_id": 123456,
      "customer_id": 555,
      "user_name": "...",
      "user_email": "...",
      "billing_reason": "renewal",
      "status": "failed",
      "refunded": false,
      "subtotal": 999,
      "total": 999,
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

**For `subscription_payment_failed`, the subscription ID is:**
```python
subscription_id = str(payload["data"]["attributes"]["subscription_id"])
# NOT payload["data"]["id"] — that is the invoice ID
```

The `customer_id` is still available at `payload["data"]["attributes"]["customer_id"]`.

**Implication for D-09:** When handling `subscription_payment_failed`, the handler cannot get a new `status` from the subscription object — it must set `subscription_status = "past_due"` directly (per D-12) rather than reading from `attrs["status"]`. The lookup to find which dealership to update must use `subscription_id` from `attrs["subscription_id"]` (not `data.id`) to look up `Dealership.subscription_id` in DB. Alternatively (and simpler per D-05), rely on `meta.custom_data.dealership_id` — this is still present even on invoice events.

**Recommendation:** For `subscription_payment_failed`, use `meta.custom_data.dealership_id` as primary lookup (consistent with all other events, per D-05). Only fall back to `attrs["subscription_id"]` if custom_data is missing.

### subscription_cancelled

Delivers `data.type = "subscriptions"`. `attrs["status"]` will be `"cancelled"`. `attrs["cancelled"]` will be `True`.

```python
status = attrs["status"]  # "cancelled"
```

### subscription_expired

Delivers `data.type = "subscriptions"`. `attrs["status"]` will be `"expired"`.

```python
status = attrs["status"]  # "expired"
```

### HMAC Verification Header

The signature is in: `X-Signature` header (NOT `X-Hub-Signature-256`). Already correctly implemented in the existing `_verify_signature` function in `webhook_lemon.py`. No changes needed to the verification code.

---

## Q2: Alembic Migration Chain

**Confidence:** HIGH — read all files directly from disk.

### Current migration chain (confirmed):

```
001_initial_schema.py          revision="001", down_revision=None
002_mvp_schema_extensions.py   revision="002", down_revision="001"
003_add_wamid_column.py        (inferred from filename order)
004_add_ml_item_id_index.py    revision="004"
006_multi_tenancy_dealership_columns.py  revision="006", down_revision="004"
```

**Observations:**
- There is NO migration `005` — the chain jumps from `004` to `006`.
- Migration `006` has `down_revision = "004"` (skips 005).
- The next migration MUST have `down_revision = "006"`.
- The filename `007_billing_subscription_columns.py` is correct per D-03.

**Correct migration header for 007:**
```python
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None
```

### Column addition pattern (from 006):

```python
def upgrade() -> None:
    op.add_column(
        "dealerships",
        sa.Column("column_name", sa.String(N), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("dealerships", "column_name")
```

For DateTime columns, the pattern is `sa.Column("col", sa.DateTime, nullable=True)` — no `timezone=True` used in this codebase (existing `DateTime` columns in models.py have no timezone argument; UTC is handled at application layer via `_utcnow()`).

---

## Q3: FastAPI Raw Body + Depends(get_db) — Safety Confirmed

**Confidence:** HIGH — verified from Neon FastAPI webhooks guide and FastAPI internals documentation.

### The answer: safe, no ordering issue

FastAPI buffers the request body on first read. Once `await request.body()` is called, the result is cached on the `Request` object (in Starlette's `_body` attribute). Subsequent reads — including any that happen via `await request.json()` — return the cached bytes. `Depends(get_db)` is resolved before the route function body executes, but it does NOT read the request body; it only creates a DB session. Therefore:

1. FastAPI resolves dependencies (creates DB session) — body not touched.
2. Route handler starts executing.
3. `raw_body = await request.body()` — reads and caches body.
4. `_verify_signature(raw_body, ...)` — uses cached bytes.
5. `payload = json.loads(raw_body)` — parses same cached bytes.
6. DB queries use `db` session — entirely separate from body.

**Pattern for the updated handler:**

```python
@router.post("")
async def lemon_squeezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    secret = settings.lemon_squeezy_webhook_secret
    if not secret:
        ...

    raw_body = await request.body()     # safe — cached after first read
    signature = request.headers.get("x-signature", "")

    if not _verify_signature(raw_body, signature, secret):
        ...

    payload = json.loads(raw_body)      # same cached bytes — no double-read issue
    ...
    # db is available throughout
    dealership_id = int(payload.get("meta", {}).get("custom_data", {}).get("dealership_id", 0))
    stmt = select(Dealership).where(Dealership.id == dealership_id)
    result = await db.execute(stmt)
    dealer = result.scalar_one_or_none()
```

**No middleware changes needed.** The existing `Depends(get_db)` pattern from `webhook_cloud.py` is directly reusable.

---

## Q4: admin_settings.py and settings.html — Current State and Insertion Point

**Confidence:** HIGH — read both files directly.

### Current settings.html structure

The page has two `<div class="card">` sections:

1. **"Dealership information"** — editable fields: name, address, business_hours, default_language.
2. **"Bot behavior"** — read-only env var display: LLM enabled, Follow-ups enabled.

Below these cards: `<div class="form-actions">` with the Save button.

### Current admin_settings.py route

The GET `/settings` route already passes `dealer` (the `Dealership` object) and `settings` to the template. After Phase 8 columns are added to the model, `dealer.subscription_status`, `dealer.plan`, `dealer.trial_ends_at`, and `dealer.grace_period_ends_at` will be available in the template automatically — **no Python route changes required**.

### Insertion point for subscription display

Add a third `<div class="card">` block **between the "Bot behavior" card and the `<div class="form-actions">` save button**. This card is read-only (no form fields), consistent with the "Bot behavior" card pattern. Place it outside the `<form>` tag OR inside it — since the subscription fields are display-only with no input elements, inside the form is fine (no hidden data will be submitted).

Recommended insertion point (after line 55, before line 57 in current settings.html):

```html
<!-- INSERT AFTER: </div> closing "Bot behavior" card -->
<!-- INSERT BEFORE: <div class="form-actions"> -->

<div class="card">
    <h3>Subscription</h3>
    <div class="info-list">
        <div class="info-item">
            <span>Status</span>
            <strong class="{% if dealer and dealer.subscription_status in ('trial', 'active') %}text-success{% elif dealer and dealer.subscription_status in ('past_due',) %}text-warning{% else %}text-muted{% endif %}">
                {{ dealer.subscription_status | upper if dealer and dealer.subscription_status else 'No subscription' }}
            </strong>
        </div>
        {% if dealer and dealer.plan %}
        <div class="info-item">
            <span>Plan</span>
            <strong>{{ dealer.plan }}</strong>
        </div>
        {% endif %}
        {% if dealer and dealer.trial_ends_at %}
        <div class="info-item">
            <span>Trial ends</span>
            <strong>{{ dealer.trial_ends_at.strftime('%Y-%m-%d') }}</strong>
        </div>
        {% endif %}
        {% if dealer and dealer.subscription_status == 'past_due' and dealer.grace_period_ends_at %}
        <div class="info-item">
            <span>Grace period ends</span>
            <strong class="text-warning">{{ dealer.grace_period_ends_at.strftime('%Y-%m-%d') }}</strong>
        </div>
        {% endif %}
    </div>
</div>
```

The existing CSS classes `text-success`, `text-muted`, `info-list`, `info-item` are already used in `settings.html` and `integrations.html` — no new CSS needed.

The `admin_settings.py` GET handler needs no changes — `dealer` is already passed. The POST handler also needs no changes — subscription fields are not editable from the UI.

---

## Q5: followup_task.py — Subscription Check Insertion Point

**Confidence:** HIGH — read file directly.

### Current flow in `send_followups()`

```
_get_candidates() → [Conversation list]
for conv in candidates:
    _should_followup(conv, now) → (should_send, followup_num)
    if not should_send: skip
    dealer = session.get(Dealership, conv.dealership_id)   ← ALREADY LOADED HERE
    ... build template, send, update state
```

### Recommended insertion: AFTER `dealer = session.get(...)`, BEFORE template build

Line 181-182 in current file already loads the dealership. The subscription check belongs immediately after that load, before any WhatsApp API calls:

```python
dealer = session.get(Dealership, conv.dealership_id)

# BILLING GATE (Phase 8)
if not is_subscription_active(dealer):
    skipped += 1
    continue

wa_phone_id = (dealer.whatsapp_phone_number_id if dealer else None) or ...
```

**Why here and not in `_should_followup()`:**
- `_should_followup()` does not have access to the `Dealership` object — it only receives `conv: Conversation`. Adding it there would require changing the function signature.
- The dealership is already loaded at line 181 — no additional DB query.
- `is_subscription_active(dealership)` is a pure-Python function (no async, no DB). Safe in sync Celery context. ✓

**None situation (dealer is None):**
If `dealer` is `None` (orphaned conversation), `is_subscription_active(None)` must handle this gracefully. The implementation in `billing.py` should return `False` if `dealership is None`.

---

## Q6: Test Fixtures — Current State and Required Additions

**Confidence:** HIGH — read conftest.py directly.

### Current `dealership` fixture (does NOT have billing fields)

```python
d = Dealership(
    id=1,
    name="Test Dealership",
    address=...,
    business_hours=...,
    timezone=...,
    default_language=...,
    whatsapp_phone_number_id="1111111111",
    whatsapp_access_token="test-wa-token-1",
    whatsapp_verify_token="test-verify-token-1",
    ml_user_id="123456789",
    admin_username="dealer1",
    admin_password_hash=_DEALER1_HASH,
    # NO subscription fields
)
```

### Fields that do NOT need to be added to the existing fixture

The existing `dealership` fixture should remain unchanged (all subscription columns are nullable and default to `None`). The model `Dealership` will have these columns after migration, but not setting them is valid (they are nullable).

### New fixtures needed for billing tests

Add to `conftest.py` (Phase 8):

```python
@pytest_asyncio.fixture
async def active_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with active subscription."""
    from datetime import datetime, UTC, timedelta
    d = Dealership(
        id=10,
        name="Active Sub Dealership",
        whatsapp_phone_number_id="3333333333",
        admin_username="dealer_active",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="active",
        subscription_id="sub_active_001",
        ls_customer_id="cust_001",
        plan="basic",
    )
    db_session.add(d)
    await db_session.flush()
    return d

@pytest_asyncio.fixture
async def trial_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership in 7-day trial."""
    from datetime import datetime, UTC, timedelta
    d = Dealership(
        id=11,
        name="Trial Dealership",
        whatsapp_phone_number_id="4444444444",
        admin_username="dealer_trial",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="trial",
        subscription_id="sub_trial_001",
        ls_customer_id="cust_002",
        plan="basic",
        trial_ends_at=datetime.now(UTC) + timedelta(days=5),
    )
    db_session.add(d)
    await db_session.flush()
    return d

@pytest_asyncio.fixture
async def past_due_in_grace_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership past_due but still within grace period."""
    from datetime import datetime, UTC, timedelta
    d = Dealership(
        id=12,
        name="Grace Dealership",
        whatsapp_phone_number_id="5555555555",
        admin_username="dealer_grace",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="past_due",
        subscription_id="sub_grace_001",
        ls_customer_id="cust_003",
        grace_period_ends_at=datetime.now(UTC) + timedelta(days=3),
    )
    db_session.add(d)
    await db_session.flush()
    return d

@pytest_asyncio.fixture
async def expired_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with expired subscription — should be blocked."""
    d = Dealership(
        id=13,
        name="Expired Dealership",
        whatsapp_phone_number_id="6666666666",
        admin_username="dealer_expired",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="expired",
        subscription_id="sub_expired_001",
        ls_customer_id="cust_004",
    )
    db_session.add(d)
    await db_session.flush()
    return d

@pytest_asyncio.fixture
async def no_subscription_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with no subscription at all (subscription_status=None) — blocked."""
    d = Dealership(
        id=14,
        name="No Sub Dealership",
        whatsapp_phone_number_id="7777777777",
        admin_username="dealer_nosub",
        admin_password_hash=_DEALER1_HASH,
        # subscription fields all None
    )
    db_session.add(d)
    await db_session.flush()
    return d
```

**Test coverage matrix for `is_subscription_active()`:**

| Fixture | Expected result | Rule |
|---------|----------------|------|
| `active_dealership` | `True` | D-16 |
| `trial_dealership` | `True` | D-16 |
| `past_due_in_grace_dealership` | `True` | D-16 |
| past_due, grace expired (inline) | `False` | D-14 |
| `expired_dealership` | `False` | D-16 |
| `no_subscription_dealership` | `False` | D-19 |
| `None` passed directly | `False` | Defensive |

---

## Q7: Alembic Migration Column Addition Pattern

**Confidence:** HIGH — read migration 006 directly.

### Confirmed pattern from 006_multi_tenancy_dealership_columns.py

```python
import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dealerships", sa.Column("subscription_status", sa.String(32), nullable=True))
    op.add_column("dealerships", sa.Column("subscription_id", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("ls_customer_id", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("plan", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("trial_ends_at", sa.DateTime, nullable=True))
    op.add_column("dealerships", sa.Column("grace_period_ends_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("dealerships", "grace_period_ends_at")
    op.drop_column("dealerships", "trial_ends_at")
    op.drop_column("dealerships", "plan")
    op.drop_column("dealerships", "ls_customer_id")
    op.drop_column("dealerships", "subscription_id")
    op.drop_column("dealerships", "subscription_status")
```

**Notes:**
- `sa.DateTime` with no `timezone=True` — consistent with all existing DateTime columns in this codebase.
- `nullable=True` on all — matching the requirement and the 006 pattern.
- `downgrade()` drops in reverse order — consistent with 006.
- No `server_default` needed — columns start as `NULL` for existing rows.

---

## Architecture Patterns

### billing.py — Pure Python, no I/O

`is_subscription_active(dealership)` must be a pure Python function with zero I/O (no DB, no async). This makes it callable from both async FastAPI routes and the sync Celery worker without any context issues.

```python
from datetime import UTC, datetime

def is_subscription_active(dealership) -> bool:
    if dealership is None:
        return False
    status = dealership.subscription_status
    if status in ("active", "trial"):
        return True
    if status == "past_due":
        gpe = dealership.grace_period_ends_at
        if gpe is not None:
            now = datetime.now(UTC)
            # Handle naive datetime (DB may return without tzinfo)
            if gpe.tzinfo is None:
                gpe = gpe.replace(tzinfo=UTC)
            return now < gpe
    # D-19: None status — check trial_ends_at fallback
    if status is None:
        tea = dealership.trial_ends_at
        if tea is not None:
            now = datetime.now(UTC)
            if tea.tzinfo is None:
                tea = tea.replace(tzinfo=UTC)
            return now < tea
    return False
```

**Datetime naive/aware hazard:** SQLAlchemy with `DateTime` (no timezone) stores naive datetimes. When comparing to `datetime.now(UTC)` (aware), Python raises `TypeError`. Always normalize DB datetimes with `.replace(tzinfo=UTC)` before comparison if `.tzinfo is None`.

### LS Status Mapping Helper

```python
LS_STATUS_MAP = {
    "on_trial":  "trial",
    "active":    "active",
    "past_due":  "past_due",
    "paused":    "past_due",
    "unpaid":    "past_due",
    "cancelled": "cancelled",
    "expired":   "expired",
}

def map_ls_status(ls_status: str) -> str:
    return LS_STATUS_MAP.get(ls_status, "expired")  # safe default
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HMAC signature verify | Custom hash compare | Already in `_verify_signature()` + `hmac.compare_digest()` | Timing-safe comparison required |
| Subscription state machine | Custom FSM | Simple column + helper function | One dealership = one subscription, no concurrency needed |
| Webhook retry queue | Custom retry logic | Return 200 always (per D-06) | LS retries on non-2xx; returning 200 prevents retry storms |

---

## Common Pitfalls

### Pitfall 1: subscription_payment_failed has a different payload type

**What goes wrong:** Handler reads `payload["data"]["id"]` expecting subscription ID, gets the invoice ID instead.
**Why it happens:** LS delivers `subscription_invoices` objects for payment events, not `subscriptions` objects.
**How to avoid:** For `subscription_payment_failed`, read subscription ID from `payload["data"]["attributes"]["subscription_id"]` — or, better, always use `meta.custom_data.dealership_id` as the primary lookup key (per D-05), making `data.id` irrelevant.
**Warning signs:** Dealership lookups return None for every payment_failed event.

### Pitfall 2: Naive vs. aware datetime comparison

**What goes wrong:** `datetime.now(UTC) < dealership.grace_period_ends_at` raises `TypeError: can't compare offset-naive and offset-aware datetimes`.
**Why it happens:** SQLAlchemy `DateTime` (no tz) stores and returns naive datetimes. Application writes aware datetimes with UTC, but on read the tzinfo is stripped.
**How to avoid:** Always check `if dt.tzinfo is None: dt = dt.replace(tzinfo=UTC)` before comparing with `datetime.now(UTC)`. This codebase uses this pattern elsewhere (`followup_task.py` line 145-147 — confirmed).

### Pitfall 3: custom_data.dealership_id is a string

**What goes wrong:** `int(payload["meta"]["custom_data"]["dealership_id"])` raises `ValueError` or returns wrong type.
**Why it happens:** LS passes custom_data values as strings even when they're numeric. The `int()` cast is mandatory.
**How to avoid:** Always cast: `int(payload.get("meta", {}).get("custom_data", {}).get("dealership_id", 0))`. Check for 0 as sentinel for missing.

### Pitfall 4: Missing event not returning 200

**What goes wrong:** Unknown event name raises an unhandled exception → LS receives 500 → LS retries → thundering herd.
**Why it happens:** Event dispatch via if/elif chain misses new LS events.
**How to avoid:** Always have a final `else: logger.info("Unhandled event: %s", event_name); return {"status": "ok"}`.

### Pitfall 5: is_subscription_active called before columns added to model

**What goes wrong:** `AttributeError: 'Dealership' object has no attribute 'subscription_status'`.
**Why it happens:** Migration not run, or model.py updated but old object cached.
**How to avoid:** Run `alembic upgrade head` before starting the app. In tests, `db_session` fixture runs `Base.metadata.create_all` which picks up all ORM-defined columns.

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| Separate subscriptions table | Column on dealerships table | Per D-01 — correct for 1:1 relationship |
| `datetime.utcnow()` | `datetime.now(UTC)` | This codebase already uses the correct approach (`_utcnow()`) |
| Store raw LS payload | Store only mapped fields | Keeps schema simple; raw payload not needed for access gating |

---

## Open Questions

1. **Does `subscription_updated` fire on trial→active transition?**
   - What we know: LS fires `subscription_updated` for any subscription attribute change. The trial→active transition changes `status` from `on_trial` to `active`.
   - What's unclear: Whether LS also fires a separate `subscription_activated` event — not found in any source.
   - Recommendation: Handle `subscription_updated` to update status from `attributes.status` — this covers the trial→active transition without needing a separate event. The CONTEXT.md (D-07) confirms this approach.

2. **Does `subscription_cancelled` fire before `subscription_expired`?**
   - What we know: In LS, when a subscription is cancelled, it typically runs until the period ends, then fires `subscription_expired`. `subscription_cancelled` fires when the cancellation is scheduled.
   - What's unclear: Whether there is a gap where status is `cancelled` but service should still run.
   - Recommendation: Per D-08, both map to distinct statuses. `cancelled` → block immediately (per D-16, only `trial`, `active`, `past_due`-in-grace are allowed). If the dealership needs to run until period end, LS typically keeps status `active` until expiry. This is consistent with the locked decision.

3. **SQLite DateTime in tests — naive datetimes**
   - What we know: Tests use SQLite via aiosqlite. SQLite does not enforce timezone info. Datetimes written as aware UTC will be read back as naive strings.
   - Recommendation: `is_subscription_active()` must always normalize with `.replace(tzinfo=UTC)` if `tzinfo is None`, making it safe in both SQLite test environment and PostgreSQL production.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 8 is purely Python code and SQL schema changes. No new external tools, services, or CLIs beyond the project's existing stack (PostgreSQL, Redis, Celery) are required. Lemon Squeezy is an external SaaS — no local instance needed, only webhook handling.

---

## Sources

### Primary (HIGH confidence)
- NdoleStudio/lemonsqueezy-go pkg.go.dev — TypeScript-equivalent Go structs for all webhook events including full status enum (`on_trial`, `active`, `past_due`, `unpaid`, `cancelled`, `expired`) and confirmation that `subscription_payment_failed` delivers `subscription_invoices` type
- DEV Community real payload dump (notearthian) — confirmed `data.attributes` field list: `status`, `variant_name`, `customer_id`, `trial_ends_at`, `renews_at`, `cancelled`, `card_brand`
- lmsqueezy/nextjs-billing GitHub (official LS sample repo) — confirmed `eventBody.data.attributes.status`, `eventBody.data.attributes.trial_ends_at`, `eventBody.meta.custom_data.user_id` paths
- Neon FastAPI webhooks guide — confirmed `await request.body()` is cached and safe alongside `Depends(get_db)` in same route

### Secondary (MEDIUM confidence)
- feliche93 Zod schema gist — confirmed `data.id` = subscription ID (string), `data.attributes.customer_id` (number), `data.attributes.status`, `data.attributes.trial_ends_at`, `data.attributes.variant_name`
- LS official docs (indirect, via search summaries) — `trial_ends_at` is ISO 8601 string when on_trial, null otherwise; `custom_data` lives in `meta` object for all subscription events

### Tertiary (LOW confidence)
- Multiple search result summaries referencing LS docs (403 blocked from direct fetch) — corroborating evidence for status values and payload structure. These findings are all cross-confirmed by HIGH sources above.

---

## Metadata

**Confidence breakdown:**
- LS payload field paths: HIGH — verified from 4 independent sources
- Migration chain: HIGH — read files directly from disk
- FastAPI body safety: HIGH — verified from official guide with code example
- Template insertion: HIGH — read HTML file directly
- followup_task insertion: HIGH — read Python file directly
- Test fixtures: HIGH — read conftest.py directly, gaps identified by absence

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (LS API v1 — stable, changes rarely)
