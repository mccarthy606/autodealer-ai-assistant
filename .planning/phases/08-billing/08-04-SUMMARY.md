---
phase: 08-billing
plan: 08-04
title: "Billing tests — is_subscription_active(), webhook_lemon events, access gate"
status: complete
completed_date: "2026-03-27"
duration_minutes: 15
tasks_completed: 2
tasks_total: 2
test_count: 25
test_pass_rate: "25/25 (100%)"
subsystem: billing
tags: [billing, tests, is_subscription_active, webhook_lemon, access_gate, followup_task]
dependency_graph:
  requires: [08-01, 08-02, 08-03]
  provides: [billing_test_coverage]
  affects: [ci_pipeline]
tech_stack:
  added: []
  patterns:
    - httpx.ASGITransport + AsyncClient for FastAPI route integration tests
    - app.dependency_overrides[get_db] to inject test db_session into routes
    - StubDealer class for pure-unit tests without DB or fixtures
    - monkeypatch.setattr(settings, ...) to override lemon_squeezy_webhook_secret per test
    - unittest.mock.patch context managers for isolating webhook_cloud and followup_task
key_files:
  created:
    - tests/test_billing.py
  modified:
    - tests/conftest.py
    - .planning/phases/08-billing/08-04-PLAN.md
decisions:
  - Used StubDealer dataclass for 15 pure-unit tests — no DB, no fixtures, fast
  - Shared app_client fixture injects db_session via dependency_overrides to avoid second engine
  - followup_task test patches _SyncSession factory (not the engine) to return controlled mock data
  - monkeypatch.setattr on settings object keeps webhook secret scoped to each test
key_decisions:
  - StubDealer stub approach for unit tests — avoids async fixture overhead for pure logic tests
  - app.dependency_overrides[get_db] pattern — established project convention, no second engine needed
---

# Phase 08 Plan 04: Billing Tests Summary

**One-liner:** 25-test billing coverage suite validating subscription gating, naive datetime normalization, and payment_failed invoice-vs-subscription-id distinction.

## What Was Built

Two files were modified/created:

**tests/conftest.py** — 5 new billing fixtures appended (ids 10-14):
- `active_dealership` (id=10): subscription_status="active", plan="basic"
- `trial_dealership` (id=11): subscription_status="trial", trial_ends_at=now+5d
- `past_due_in_grace_dealership` (id=12): subscription_status="past_due", grace_period_ends_at=now+3d
- `expired_dealership` (id=13): subscription_status="expired"
- `no_subscription_dealership` (id=14): all subscription fields None

**tests/test_billing.py** — 25 tests across 5 groups:

| Group | Count | Description |
|-------|-------|-------------|
| is_subscription_active() unit | 11 | All branches including None dealership and naive datetime |
| map_ls_status() unit | 4 | on_trial, paused, unpaid, unknown |
| webhook_lemon integration | 7 | subscription_created, payment_failed, cancelled, expired, missing custom_data, unknown dealership, invalid signature |
| webhook_cloud gate | 2 | expired drops silently, active processes |
| followup_task gate | 1 | expired dealership skipped, send_template not called |

## Critical Edge Cases Verified

### Naive Datetime Normalization
`test_naive_datetime_no_typeerror` creates a `grace_period_ends_at` with `tzinfo=None` (simulating SQLAlchemy stripping timezone info during SQLite round-trip). Confirms `is_subscription_active()` returns `True` without raising `TypeError`, validating the `.replace(tzinfo=UTC)` normalization in `billing.py`.

### payment_failed Invoice-vs-Subscription-ID
`test_webhook_subscription_payment_failed_uses_attrs_subscription_id` explicitly uses:
- `data.id = "invoice_888"` — the invoice ID (wrong field, would be a silent production bug)
- `data.attributes.subscription_id = 999` — the real subscription ID (correct field)

Asserts `dealership.subscription_id == "999"` confirming the handler reads from `data.attributes.subscription_id`, not `data.id`.

## Test Patterns Used

- **StubDealer class** for is_subscription_active() and map_ls_status() tests — pure Python, no DB, no async overhead
- **app_client fixture** uses `httpx.ASGITransport(app=app)` + `app.dependency_overrides[get_db]` to inject the test SQLite session into FastAPI routes
- **monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", "test-webhook-secret")** — scoped per-test override without side effects
- **unittest.mock.patch context managers** for webhook_cloud and followup_task isolation
- **followup_task** tested by patching `_SyncSession` factory directly (sync task, not async)

## Deviations from Plan

None — plan executed exactly as written. All 25 specified tests are present and pass green.

## Final Verification

```
175 passed, 3 warnings in 1.88s
```

- Full test suite: 175 passed (0 failures, 0 errors)
- Warnings are pre-existing (FastAPI `on_event` deprecation, unrelated inventory test coroutine warning)
- pytest exit code: 0

## Known Stubs

None — all tests verify real behavior against the implemented billing code.

## Self-Check: PASSED

- `tests/test_billing.py` exists: FOUND
- `tests/conftest.py` modified: FOUND
- Task 1 commit `7021921`: FOUND
- Task 2 commit `c18bb05`: FOUND
- 25 tests collected and passed: CONFIRMED
