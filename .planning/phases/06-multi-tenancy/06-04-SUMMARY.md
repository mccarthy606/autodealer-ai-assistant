---
phase: 06-multi-tenancy
plan: "06-04"
subsystem: tests
tags: [multi-tenancy, tests, auth, session, routing, redis, isolation]
dependency_graph:
  requires: [06-01 auth.py, 06-02 adapters/routing, 06-03 admin routes]
  provides: [MT-01 coverage, MT-02 coverage, MT-03 coverage, MT-04 coverage]
  affects: [tests/conftest.py, tests/test_auth_session.py, tests/test_multi_tenancy_routing.py]
tech_stack:
  added: []
  patterns: [module-level bcrypt constants, in-memory session fallback testing, pipeline mock pattern]
key_files:
  created:
    - tests/test_auth_session.py
    - tests/test_multi_tenancy_routing.py
  modified:
    - tests/conftest.py
decisions:
  - "bcrypt hashes computed at module level (_DEALER1_HASH, _DEALER2_HASH) not per-fixture to avoid per-test CPU cost"
  - "dealership fixture updated in-place (not replaced) — all existing tests unaffected as they don't access new fields"
  - "is_authenticated test patches settings.admin_password to force session-check path (otherwise short-circuits to True)"
  - "pipeline mock uses mock_pipe.execute = AsyncMock (not MagicMock) since rate_limit.py awaits pipe.execute()"
metrics:
  duration: ~10 min
  completed: 2026-03-27
  tasks: 4
  files: 3
---

# Phase 6 Plan 04: Tests for multi-tenancy — session, webhook routing, adapter credentials, Redis isolation — Summary

**One-liner:** 20 new tests covering all four MT requirements: per-dealership session storage, WA/ML webhook lookup, adapter credential injection, data isolation, and Redis key namespacing.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Extend conftest.py fixtures | baa712f | tests/conftest.py |
| 2 | test_auth_session.py (MT-02) | baa712f | tests/test_auth_session.py |
| 3 | test_multi_tenancy_routing.py (MT-01, MT-03, MT-04) | baa712f | tests/test_multi_tenancy_routing.py |
| 4 | Full suite regression check | baa712f | (no changes needed) |

## What Was Built

### conftest.py updates

- Added `import bcrypt` and two module-level constants `_DEALER1_HASH` and `_DEALER2_HASH` computed once at import time.
- Updated the existing `dealership` fixture (id=1) to include all multi-tenant fields: `whatsapp_phone_number_id="1111111111"`, `whatsapp_access_token`, `whatsapp_verify_token`, `ml_user_id="123456789"`, `admin_username="dealer1"`, `admin_password_hash=_DEALER1_HASH`.
- Added new `dealership2` fixture (id=2) with distinct phone_number_id, ml_user_id, and admin_username.

### test_auth_session.py (7 tests, MT-02)

- `test_create_session_stores_dealership_id`: in-memory fallback path — create session, retrieve same dealership_id.
- `test_create_session_different_dealerships`: two sessions produce distinct tokens; cross-check confirms tokens don't swap dealership_ids.
- `test_is_authenticated_returns_true_when_session_exists`: valid token returns True (settings patched to force real check).
- `test_is_authenticated_returns_false_for_unknown_token`: garbage token returns False.
- `test_get_session_dealership_id_returns_none_for_missing_token`: None and "" both return None.
- `test_backward_compat_old_session_value`: direct int insertion into `_admin_sessions` dict is retrieved correctly.
- `test_superadmin_login_creates_session_with_dealership_id_1`: superadmin login path calls `create_session(resp, settings.default_dealership_id)` producing a session scoped to id=1 (D-08).

### test_multi_tenancy_routing.py (13 tests, MT-01/MT-03/MT-04)

**Section A — parse_incoming_message 4-tuple:**
- Returns 4-tuple with phone_number_id as 4th element.
- Returns None for empty messages array.
- Returns None or 4th element as None when metadata absent.

**Section B — get_dealership_by_wa:**
- Finds correct dealership by phone_number_id="1111111111".
- Returns None for unknown phone_number_id.

**Section C — get_dealership_by_ml:**
- Finds correct dealership by ml_user_id="123456789".
- Returns None for unknown ml_user_id.
- `parse_incoming_question` extracts question_id and user_id from notification payload.

**Section D — WhatsAppCloudAdapter credentials:**
- Explicit phone_number_id+token used when provided; is_configured=True.
- Falls back to settings values when no args given.
- is_configured=False when both settings values are empty.

**Section E — Data isolation (MT-01):**
- InventoryItem rows scoped to dealership_id=1 and dealership_id=2 are correctly isolated in queries.

**Section F — Redis key namespacing (MT-04):**
- `check_rate_limit(key="5491112345678", prefix="rate:wa:1")` → Redis key = `"rate:wa:1:5491112345678"`.
- `check_rate_limit(key="5491112345678", prefix="rate:wa:2")` → Redis key = `"rate:wa:2:5491112345678"`.
- Confirmed via `mock_pipe.incr.assert_called_once_with(...)`.

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

```
142 passed, 3 warnings in 2.41s
```

All 142 tests pass (122 pre-existing + 20 new). Zero regressions from conftest.py fixture update.

## Known Stubs

None.

## Self-Check: PASSED

- [x] tests/test_auth_session.py — FOUND (7 test functions)
- [x] tests/test_multi_tenancy_routing.py — FOUND (13 test functions)
- [x] conftest.py dealership fixture has all multi-tenant fields — VERIFIED
- [x] conftest.py dealership2 fixture exists with id=2 — VERIFIED
- [x] bcrypt hashes at module level (_DEALER1_HASH, _DEALER2_HASH) — VERIFIED
- [x] All existing tests pass (no regressions) — 142 passed
- [x] Rate limiter mock uses AsyncMock for execute, asserts exact Redis key — VERIFIED
- [x] Commit baa712f — FOUND
