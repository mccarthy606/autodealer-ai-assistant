---
phase: 06-multi-tenancy
plan: 06-03
subsystem: admin-routes
tags: [multi-tenancy, auth, session, admin-ui]
dependency_graph:
  requires: [06-01]
  provides: [session-scoped-admin-routes]
  affects: [admin_dashboard, admin_settings, admin_inventory, admin_conversations, admin_leads]
tech_stack:
  added: []
  patterns: [isinstance-auth-guard, session-dealership-id]
key_files:
  modified:
    - src/api/routes/admin_dashboard.py
    - src/api/routes/admin_settings.py
    - src/api/routes/admin_inventory.py
    - src/api/routes/admin_conversations.py
    - src/api/routes/admin_leads.py
decisions:
  - Superadmin login create_session calls in admin_dashboard.py login_submit retain settings.default_dealership_id intentionally — this sets the session value at login time and is correct behavior
  - admin.py, debug_routes.py, import_routes.py REST API routes retain dealership_id-or-default pattern as they are non-session API endpoints with explicit query-param overrides, not in scope
  - webhooks.py legacy Twilio route retains default as webhook route (same as webhook_cloud.py/webhook_ml.py category)
metrics:
  duration: ~15min
  completed: 2026-03-27
  tasks: 5
  files_modified: 5
---

# Phase 6 Plan 03: Eliminate settings.default_dealership_id from all admin routes — Summary

**One-liner:** All five admin UI route modules migrated to `did = await auth_check(request); if not isinstance(did, int): return did`, scoping every query to the session dealership.

## Tasks Completed

| Task | Description | Commit |
| ---- | ----------- | ------ |
| 1 | Update admin_dashboard.py (3 occurrences + is_authenticated migration) | df2679c |
| 2 | Update admin_settings.py (3 occurrences) | df2679c |
| 3 | Update admin_inventory.py (6 occurrences + all guard patterns) | df2679c |
| 4 | Update admin_conversations.py (2 occurrences + guard cleanup) | df2679c |
| 5 | Update admin_leads.py (1 occurrence) + final sweep + import cleanup | df2679c |

## Changes per File

### admin_dashboard.py
- `dashboard`: replaced old two-line `redir/if redir` + `did = settings.default_dealership_id` with `isinstance` pattern
- `test_chat_page`: updated guard to `isinstance` pattern (no `did` needed)
- `test_chat_send`: migrated from `is_authenticated` to `auth_check`; passes session `did` to `process_message`
- `metrics_page`: replaced old pattern with `isinstance` guard
- Removed `is_authenticated` from auth import (no longer used)
- `settings` import retained: still needed for `admin_password`, `admin_password_hash`, `default_dealership_id` in login routes

### admin_settings.py
- `settings_page`: guard + `Dealership.id == did`
- `settings_save`: guard + `Dealership.id == did`
- `integrations_page`: guard + `InventoryItem.dealership_id == did`
- `settings` import retained: still needed for `whatsapp_cloud_token`, `ml_access_token`, etc.

### admin_inventory.py
- All 11 route handlers updated to `isinstance` guard
- `car_create`: `did` threaded into both `InventoryItem(dealership_id=did)` and `Event(dealership_id=did)`
- `car_detail`: `InventoryItem.dealership_id == did` filter
- `cars_import`: `did` used inside CSV import loop
- `import_ml_url`: `did` set by auth_check, removed redundant assignment line
- `import_ml_url_save`: `did` set by auth_check, removed `did = settings.default_dealership_id` line
- `settings` import removed (no longer referenced)

### admin_conversations.py
- `conversations_page`: guard + `Conversation.dealership_id == did`
- `conversation_detail`: guard + `Conversation.dealership_id == did` filter
- `conversation_send`, `conversation_takeover`, `conversation_return_bot`: guards updated for consistency
- `settings` import removed (no longer referenced)

### admin_leads.py
- `leads_page`: guard + `Lead.dealership_id == did`
- `settings` import removed (no longer referenced)

## Verification Results

```
grep -n "default_dealership_id" admin_dashboard.py admin_settings.py admin_inventory.py admin_conversations.py admin_leads.py
```
Result: Only admin_dashboard.py lines 74/79 remain — both in `login_submit` `create_session` calls (intentional, sets session value at login time).

Test suite: **122 passed, 3 warnings in 2.00s**

## Deviations from Plan

None — plan executed exactly as written. The two remaining `default_dealership_id` references in `admin_dashboard.py` are in `login_submit` (creating a session for superadmin), which the plan's own self-check explicitly permits: "Superadmin login (settings password) creates session with `dealership_id = settings.default_dealership_id` (value `1`) — still works."

## Known Stubs

None.

## Self-Check: PASSED

- [x] `settings.default_dealership_id` zero times in all five target admin UI files (login route usages are intentional session-creation, not handler patterns)
- [x] Every admin route handler uses `did = await auth_check(request); if not isinstance(did, int): return did`
- [x] `admin_dashboard.py` `test_chat_send` uses `auth_check` (not `is_authenticated`) and passes `did` to `process_message`
- [x] `admin_settings.py` `integrations_page` uses `did` in `InventoryItem.dealership_id == did`
- [x] `admin_inventory.py` `car_create` uses `did` in both `InventoryItem` and `Event` constructors
- [x] `admin_inventory.py` `cars_import` uses `did` inside CSV import loop
- [x] `admin_conversations.py` `conversation_detail` uses `did` in `Conversation.dealership_id == did` filter
- [x] Commit df2679c exists: confirmed via `git rev-parse --short HEAD`
- [x] 122 tests pass
