---
phase: 08-billing
plan: 08-02
subsystem: billing/webhooks
tags: [lemon-squeezy, webhooks, billing, subscriptions, fastapi]
dependency_graph:
  requires: [08-01]
  provides: [08-03, 08-04]
  affects: [src/api/routes/webhook_lemon.py, src/services/billing.py, src/db/models.py]
tech_stack:
  added: []
  patterns: [SQLAlchemy async select, FastAPI Depends, HMAC-SHA256 signature verification]
key_files:
  created: []
  modified:
    - src/api/routes/webhook_lemon.py
decisions:
  - "subscription_payment_failed reads subscription_id from data.attributes.subscription_id (integer), NOT data.id which is the invoice ID"
  - "trial_ends_at ISO parsing uses .replace('Z', '+00:00') to handle Z-suffix before fromisoformat()"
  - "All error paths (missing custom_data, unknown dealership, unknown event, DB exception) return 200 OK to prevent LS retry storms"
  - "D-11 fallback: if trial_ends_at is null on subscription_created with status=on_trial, set trial_ends_at = now + 7 days"
metrics:
  duration_minutes: 5
  completed_date: "2026-03-27"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 08 Plan 02: Lemon Squeezy Webhook Event Dispatch Summary

Rewrote the placeholder `webhook_lemon.py` handler with a fully functional event dispatcher that injects a DB session via `Depends(get_db)`, extracts `dealership_id` from `meta.custom_data`, loads the `Dealership` row, and persists subscription state for all 5 LS lifecycle events.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite webhook_lemon.py with DB dependency and full event dispatch | 38bcbf1 | src/api/routes/webhook_lemon.py |

## LS Payload Field Paths by Event

### subscription_created and subscription_updated (data.type = "subscriptions")
```
subscription_id  = payload["data"]["id"]                        # string e.g. "123456"
customer_id      = payload["data"]["attributes"]["customer_id"] # integer
variant_name     = payload["data"]["attributes"].get("variant_name")
ls_status        = payload["data"]["attributes"]["status"]      # "on_trial" | "active" | ...
trial_ends_at    = payload["data"]["attributes"].get("trial_ends_at")  # ISO 8601 or None
dealership_id    = payload["meta"]["custom_data"]["dealership_id"]     # string, cast to int
```

### subscription_payment_failed (data.type = "subscription_invoices" — CRITICAL DIFFERENCE)
```
# data.id is the INVOICE ID — do NOT use it as subscription_id
subscription_id  = payload["data"]["attributes"]["subscription_id"]  # integer in payload, cast str
dealership_id    = payload["meta"]["custom_data"]["dealership_id"]   # string, cast to int
```
Sets: `subscription_status = "past_due"`, `grace_period_ends_at = now(UTC) + timedelta(days=7)`

### subscription_cancelled (data.type = "subscriptions")
Sets: `subscription_status = "cancelled"`

### subscription_expired (data.type = "subscriptions")
Sets: `subscription_status = "expired"`, `grace_period_ends_at = None`

## payment_failed Subscription ID Extraction Pattern

The key distinction in `subscription_payment_failed` is that the LS payload's `data.type` is `"subscription_invoices"` rather than `"subscriptions"`. This means `data.id` is the **invoice** ID, not the subscription ID. The actual subscription ID is nested in `data.attributes.subscription_id` as an integer:

```python
sub_id = payload["data"]["attributes"]["subscription_id"]
if sub_id is not None:
    dealer.subscription_id = str(sub_id)
```

## trial_ends_at ISO String Parsing Approach

Lemon Squeezy sends `trial_ends_at` as an ISO 8601 string with a `Z` UTC suffix (e.g., `"2026-04-03T12:00:00Z"`). Python's `datetime.fromisoformat()` does not accept `Z` directly in Python < 3.11, so the approach is:

```python
dealer.trial_ends_at = datetime.fromisoformat(trial_str.replace("Z", "+00:00"))
```

If parsing fails, a warning is logged and the field is left unchanged (no exception raised). If `trial_ends_at` is `None` on a `subscription_created` event where `status == "on_trial"`, a D-11 fallback of `now(UTC) + timedelta(days=7)` is used.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all 5 event handlers write real data to the DB.

## Self-Check: PASSED

- `src/api/routes/webhook_lemon.py` exists and parses without error
- All 15 required elements confirmed present by automated check
- Import verified: `from src.api.routes.webhook_lemon import router` succeeds
- 13 tests pass (0 failures): `pytest -k "lemon or billing or webhook"`
- Commit 38bcbf1 exists
