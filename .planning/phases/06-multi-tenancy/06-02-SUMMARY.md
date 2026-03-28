---
phase: 06-multi-tenancy
plan: "06-02"
subsystem: adapters, webhooks, tasks
tags: [multi-tenancy, whatsapp, mercadolibre, routing, per-tenant]
dependency_graph:
  requires: [06-01 model columns (already present in models.py)]
  provides: [per-tenant WA adapter, phone_number_id webhook routing, ml_user_id webhook routing]
  affects: [webhook_cloud, webhook_ml, outbound_service, followup_task]
tech_stack:
  added: []
  patterns: [per-tenant credential injection, dealership lookup by external ID]
key_files:
  created: []
  modified:
    - src/adapters/whatsapp_cloud.py
    - src/adapters/mercadolibre.py
    - src/api/routes/webhook_cloud.py
    - src/api/routes/webhook_ml.py
    - src/services/outbound_service.py
    - src/tasks/followup_task.py
decisions:
  - WhatsAppCloudAdapter constructor is fully backward-compatible (no-arg still works via settings fallback)
  - Silent 200 on unknown phone_number_id per D-12 (Meta must not receive 4xx)
  - Rate limiter key changed from "rate:whatsapp:{phone}" to "rate:wa:{dealership_id}:{phone}"
  - ML webhook falls back to settings.default_dealership_id when no dealership matched
  - followup_task adapter created per-conversation inside loop for correct per-dealer credentials
metrics:
  duration: "~15 min"
  completed: "2026-03-27"
  tasks_completed: 4
  files_modified: 6
---

# Phase 6 Plan 02: WhatsApp adapter per-tenant + webhook routing by phone_number_id + ML routing by ml_user_id Summary

**One-liner:** Per-tenant WhatsApp adapter with optional credential injection, WA webhook routing by phone_number_id, ML webhook routing by ml_user_id, and namespaced rate-limit keys.

## What Was Built

### Task 1 — WhatsAppCloudAdapter per-tenant constructor

`WhatsAppCloudAdapter.__init__` now accepts `phone_number_id: Optional[str] = None` and `token: Optional[str] = None`. When provided, those values are used directly; when omitted, falls back to `settings.whatsapp_phone_number_id` and `settings.whatsapp_cloud_token`. Fully backward-compatible.

`parse_incoming_message` upgraded from 3-tuple to 4-tuple: now returns `(phone, text, wamid, phone_number_id)` where `phone_number_id` is extracted from `value.metadata.phone_number_id` (always present in real Meta payloads).

New module-level async helper `get_dealership_by_wa(db, phone_number_id)` does `SELECT WHERE whatsapp_phone_number_id = ?` and returns `Optional[Dealership]`.

### Task 2 — WA webhook multi-tenant routing

`webhook_cloud.py` completely rewritten:

- **GET handler:** tries per-dealership `whatsapp_verify_token` first (by `phone_number_id` query param), falls back to `settings.whatsapp_verify_token`.
- **POST handler:** unpacks 4-tuple, resolves dealership via `get_dealership_by_wa`; returns `{"status": "ok"}` silently when dealership not found (never 4xx to Meta). Rate limit key is now `f"rate:wa:{dealership_id}"`. Adapter instantiated with per-dealership credentials.

### Task 3 — ML webhook multi-tenant routing

New `get_dealership_by_ml(db, ml_user_id)` helper added to `mercadolibre.py` (`SELECT WHERE ml_user_id = ?`).

`webhook_ml.py` updated: extracts `seller_id = str(parsed.get("user_id") or "")`, resolves dealership, uses `dealership_id` (with `settings.default_dealership_id` fallback) when calling `handle_ml_inquiry`.

### Task 4 — Outbound service + followup task per-tenant credentials

`outbound_service.py`: after loading dealership, extracts `dealer.whatsapp_phone_number_id` and `dealer.whatsapp_access_token`, passes both to `WhatsAppCloudAdapter(phone_number_id=..., token=...)`.

`followup_task.py`: removed global `wa_adapter = WhatsAppCloudAdapter()` before the loop. Inside the `for conv in candidates:` loop (after `if not should_send: continue`), loads `dealer = session.get(Dealership, conv.dealership_id)` and constructs `wa_adapter = WhatsAppCloudAdapter(phone_number_id=wa_phone_id, token=wa_token)` per conversation. Added `Dealership` to imports.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Dealership model already had whatsapp_access_token**

- **Found during:** Task 1 check
- **Issue:** The plan said to check if `whatsapp_access_token` was in the model; it was already present in `src/db/models.py` (along with `admin_username` and `admin_password_hash`) before this plan ran — likely applied by a linter or previous session.
- **Fix:** No change needed to models.py; the columns were already there matching what migration 006 adds.
- **Files modified:** none

**2. [Rule 2 - Missing import] outbound_service.py missing `settings` import**

- **Found during:** Task 4a
- **Issue:** `outbound_service.py` did not import `settings` but the new code needed `settings.whatsapp_phone_number_id` and `settings.whatsapp_cloud_token` for the fallback.
- **Fix:** Added `from src.config import settings` to the imports.
- **Files modified:** `src/services/outbound_service.py`

## Self-Check

- [x] `WhatsAppCloudAdapter(phone_number_id="X", token="Y")` uses provided values (verified: `is_configured=True, phone_number_id='X', token='Y'`)
- [x] `WhatsAppCloudAdapter()` falls back to settings (verified: `is_configured=False` with no env vars)
- [x] `parse_incoming_message` returns 4-tuple with `phone_number_id` as 4th element
- [x] `get_dealership_by_wa` exists in `whatsapp_cloud.py`
- [x] `get_dealership_by_ml` exists in `mercadolibre.py`
- [x] WA webhook POST resolves dealership from `phone_number_id`; returns `200 ok` silently when no dealership found
- [x] WA webhook GET falls back to `settings.whatsapp_verify_token` if no dealership matched
- [x] Rate limiter key is now `rate:wa:{dealership_id}:{phone}`
- [x] ML webhook reads `user_id` from parsed notification, resolves dealership, falls back to `settings.default_dealership_id`
- [x] `outbound_service.py` passes dealership WABA credentials to adapter
- [x] `followup_task.py` creates adapter INSIDE the per-conversation loop with per-dealership credentials
- [x] 122 tests pass

## Test Results

```
122 passed, 3 warnings in 2.67s
```

All existing tests continue to pass with no regressions.

## Self-Check: PASSED

- `src/adapters/whatsapp_cloud.py` — FOUND and verified
- `src/adapters/mercadolibre.py` — FOUND and verified
- `src/api/routes/webhook_cloud.py` — FOUND and verified
- `src/api/routes/webhook_ml.py` — FOUND and verified
- `src/services/outbound_service.py` — FOUND and verified
- `src/tasks/followup_task.py` — FOUND and verified
- Commit d95c36b — FOUND
