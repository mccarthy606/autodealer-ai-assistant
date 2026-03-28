---
# Phase 8: Billing - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Lemon Squeezy subscription billing: new Dealership columns track subscription state, webhook handler processes LS lifecycle events, WhatsApp message processing is gated by active subscription status, 7-day trial with credit card captured upfront, 7-day grace period on payment failure.

</domain>

<decisions>
## Implementation Decisions

### Subscription Data Model (BILL-01)
- **D-01:** Add subscription columns directly to `Dealership` table (NOT a separate table). One dealership = one subscription. Simpler, no joins needed.
- **D-02:** New columns on `dealerships`:
  - `subscription_status VARCHAR(32)` nullable — values: `trial`, `active`, `past_due`, `cancelled`, `expired`. Null = no subscription (new dealership, service off).
  - `subscription_id VARCHAR(128)` nullable — Lemon Squeezy subscription ID (e.g. `sub_1234`)
  - `ls_customer_id VARCHAR(128)` nullable — Lemon Squeezy customer ID
  - `plan VARCHAR(64)` nullable — e.g. `"basic"`, `"pro"` (from LS variant name)
  - `trial_ends_at DATETIME` nullable — when trial period ends
  - `grace_period_ends_at DATETIME` nullable — deadline before hard block on payment failure
- **D-03:** Migration file: `007_billing_subscription_columns.py` (next in chain after 006).

### Lemon Squeezy → Dealership Linking (BILL-02)
- **D-04:** When creating a LS checkout, pass `dealership_id` in `custom_data`. LS returns this in every webhook: `payload["meta"]["custom_data"]["dealership_id"]`. This is the authoritative link.
- **D-05:** Webhook handler must extract `dealership_id` from `meta.custom_data.dealership_id` (as integer) and load the `Dealership` row to update.
- **D-06:** If `custom_data.dealership_id` is missing or dealership not found → log warning + return 200 OK (don't retry LS).

### Webhook Event Handling (BILL-02)
- **D-07:** Handle these Lemon Squeezy events in `webhook_lemon.py`:
  - `subscription_created` — status from LS (`on_trial` → our `trial`, `active` → our `active`). Set `subscription_id`, `ls_customer_id`, `plan`. Set `trial_ends_at` from LS data if on_trial.
  - `subscription_updated` — update status, trial_ends_at, plan from LS subscription data. This covers trial→active transition.
  - `subscription_payment_failed` — set `subscription_status = "past_due"`, set `grace_period_ends_at = now + 7 days`.
  - `subscription_cancelled` — set `subscription_status = "cancelled"`.
  - `subscription_expired` — set `subscription_status = "expired"`, clear grace_period_ends_at.
- **D-08:** LS subscription status mapping: `on_trial` → `trial`, `active` → `active`, `past_due` → `past_due`, `paused` → `past_due`, `unpaid` → `past_due`, `cancelled` → `cancelled`, `expired` → `expired`.
- **D-09:** Webhook handler needs DB access — add `db: AsyncSession = Depends(get_db)` to the route. Already has `request: Request`.

### Trial Period (BILL-01, BILL-04)
- **D-10:** 7-day trial. Credit card captured upfront by Lemon Squeezy — no card-free trial. LS handles billing natively; our code just needs to treat `trial` status as "service allowed".
- **D-11:** `trial_ends_at` is set from LS webhook data (LS sends `attributes.trial_ends_at`). If null on creation event, derive as `now + 7 days` as fallback.

### Grace Period (BILL-04)
- **D-12:** 7 days grace period on payment failure. When `subscription_payment_failed` event arrives, set `grace_period_ends_at = now() + timedelta(days=7)`.
- **D-13:** During grace period (status=`past_due`, `now < grace_period_ends_at`): service continues normally.
- **D-14:** After grace period expires (status=`past_due`, `now >= grace_period_ends_at`): block service.

### Access Gating (BILL-03)
- **D-15:** Gate in `webhook_cloud.py` AFTER dealership lookup (after `get_dealership_by_wa()`), BEFORE `process_message()`. If dealership subscription is not active → return 200 OK silently (no reply to customer).
- **D-16:** Access allowed if: `subscription_status in ("trial", "active")` OR (`subscription_status == "past_due"` AND `grace_period_ends_at` is not None AND `grace_period_ends_at > now()`).
- **D-17:** New helper function `is_subscription_active(dealership: Dealership) -> bool` in a new file `src/services/billing.py`. Keeps gating logic testable and separate from route code.
- **D-18:** ML webhook (`webhook_ml.py`) is NOT gated — ML questions come in regardless, but outbound WhatsApp sending is gated via the same dealership check before `handle_ml_inquiry()`.
- **D-19:** If `subscription_status` is None (new dealership, never subscribed) → BLOCK (no service without subscription). Exception: if `trial_ends_at` is in the future → treat as trial.
- **D-20:** Follow-up task (`followup_task.py`) also checks subscription — skip sending follow-ups for non-active dealerships.

### Admin UI (DASH-01 scope extension)
- **D-21:** Show subscription status badge in `admin_settings.py` settings page (existing template `settings.html`). Read-only display: plan name, status, trial/grace end date. No billing management from admin UI — managed via LS portal.

### Implementation Files
- **D-22:** `alembic/versions/007_billing_subscription_columns.py` — migration
- **D-23:** `src/db/models.py` — 6 new columns on Dealership
- **D-24:** `src/services/billing.py` — `is_subscription_active(dealership)` + LS status mapping
- **D-25:** `src/api/routes/webhook_lemon.py` — replace placeholder with real event handling + DB dependency
- **D-26:** `src/api/routes/webhook_cloud.py` — add subscription gate after dealership lookup
- **D-27:** `src/tasks/followup_task.py` — skip non-active dealerships in `_should_followup()`
- **D-28:** `src/api/routes/admin_settings.py` + `src/templates/admin/settings.html` — show subscription info

### Claude's Discretion
- Exact LS payload field paths for subscription data (`attributes.status`, `attributes.trial_ends_at`, etc.) — verify from LS docs or handle defensively with `.get()`
- Whether to also gate `webhook_ml.py` outbound send or only `webhook_cloud.py`
- Exact settings.html additions for subscription display
- Error handling if DB update fails during webhook processing

</decisions>

<canonical_refs>
## Canonical References

### Existing Code
- `src/api/routes/webhook_lemon.py` — has signature verification + placeholder handler; add DB + real events
- `src/db/models.py` — Dealership model (add 6 columns)
- `src/api/routes/webhook_cloud.py` — add subscription gate after dealership lookup
- `src/tasks/followup_task.py` — add subscription check in `_should_followup()`
- `src/config.py` — already has `lemon_squeezy_webhook_secret`
- `src/api/routes/admin_settings.py` — show subscription status

### Research Needed
- Exact Lemon Squeezy webhook payload structure (field paths for subscription data)
- Which events LS actually sends for trial→active transition

</canonical_refs>

<code_context>
## Existing Code Insights

### webhook_lemon.py already has:
- HMAC-SHA256 signature verification (`_verify_signature`)
- Reads raw body before JSON parse ✅
- Extracts `event_name` from `payload["meta"]["event_name"]`
- Just needs: DB session, `custom_data.dealership_id` extraction, event dispatch

### Access gate insertion point in webhook_cloud.py:
```python
# After:
dealership = await get_dealership_by_wa(db, phone_number_id)
if not dealership:
    return {"status": "ok"}
# Add here:
if not is_subscription_active(dealership):
    return {"status": "ok"}  # silent drop
```

### followup_task.py gate:
- In `_should_followup()`: add check `if not is_subscription_active(conv_dealership): return False, 0`
- Or: in `send_followups()` before processing each conversation, load dealership and check

</code_context>

<specifics>
## Specific Requirements

- 7-day trial (LS handles natively, card required at signup)
- 7-day grace period on payment_failed
- Link: custom_data.dealership_id in LS checkout
- Data: columns in Dealership table (not separate table)
- Gate: in webhook_cloud.py (silent 200 drop) + followup_task.py

</specifics>

<deferred>
## Deferred Ideas

- Checkout link generation from admin UI — v2
- Invoice/payment history display — v2
- Usage limits per plan (max N conversations) — v2
- Multiple plans (basic/pro) with feature gating — v2
- Automatic email on trial expiry — v2
- Webhook retry/replay handling — v2

</deferred>

---

*Phase: 08-billing*
*Context gathered: 2026-03-27*
