---
plan: 08-01
phase: 08-billing
subsystem: billing
tags: [billing, alembic, migration, orm, subscription]
dependency_graph:
  requires: [06-multi-tenancy]
  provides: [08-02, 08-03, 08-04, 08-05]
  affects: [src/db/models.py, alembic/versions/]
tech_stack:
  added: []
  patterns: [naive-datetime-normalization, pure-python-service, lemon-squeezy-status-mapping]
key_files:
  created:
    - alembic/versions/007_billing_subscription_columns.py
    - src/services/billing.py
  modified:
    - src/db/models.py
decisions:
  - "D-03: revision=007, down_revision=006 — migration chain is 001→002→003→004→006→007 (no 005)"
  - "D-08: LS_STATUS_MAP maps 7 LS status values; paused/unpaid both map to past_due"
  - "D-13/D-14: past_due is active only within grace_period_ends_at window"
  - "D-16: active and trial both immediately active (no date check needed for trial — LS manages)"
  - "D-19: status=None with future trial_ends_at counts as active (pre-subscription trial)"
  - "Naive datetime normalization: .replace(tzinfo=UTC) when tzinfo is None before any comparison"
metrics:
  duration: "< 5 minutes"
  completed: "2026-03-27"
  tasks: 3
  files: 3
---

# Phase 8 Plan 01: Migration 007 + Subscription Columns + Billing Service Summary

Adds Alembic migration 007, 6 ORM columns to Dealership, and a pure-Python billing.py service that gates subscription access. All 150 existing tests pass with zero regressions.

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `alembic/versions/007_billing_subscription_columns.py` | Created | DB migration adding 6 subscription columns to dealerships |
| `src/db/models.py` | Modified | 6 new nullable ORM columns on Dealership class |
| `src/services/billing.py` | Created | Pure-Python billing gate: is_subscription_active(), map_ls_status(), LS_STATUS_MAP |

## Column Definitions (exact names and types for downstream plans)

All columns added to `dealerships` table and `Dealership` ORM class:

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `subscription_status` | String(32) | True | Internal status: active, trial, past_due, cancelled, expired |
| `subscription_id` | String(128) | True | Lemon Squeezy subscription ID |
| `ls_customer_id` | String(128) | True | Lemon Squeezy customer ID |
| `plan` | String(64) | True | Plan identifier (e.g. "starter", "pro") |
| `trial_ends_at` | DateTime | True | UTC datetime; naive from DB, normalized before use |
| `grace_period_ends_at` | DateTime | True | UTC datetime; naive from DB, normalized before use |

## Key Decisions Implemented

**D-03 — Migration chain:** revision="007", down_revision="006". The chain skips 005 (004→006→007). This matches confirmed history from research.

**D-08 — LS_STATUS_MAP (7 entries):**
- `on_trial` → `trial`
- `active` → `active`
- `past_due` → `past_due`
- `paused` → `past_due`
- `unpaid` → `past_due`
- `cancelled` → `cancelled`
- `expired` → `expired`
- Unknown values → `expired` (most restrictive safe default)

**D-16 — Active states:** `active` and `trial` are immediately active (no date check). Lemon Squeezy manages the trial end date server-side.

**D-13/D-14 — Grace period:** `past_due` is active only when `grace_period_ends_at` is in the future. Missing grace period = inactive.

**D-19 — Pre-subscription trial:** When `subscription_status` is None but `trial_ends_at` is set and in the future, the dealership is considered active. This supports dealerships that have been given a trial before completing signup.

## Naive Datetime Normalization Pattern

SQLAlchemy `DateTime` columns without `timezone=True` return naive datetimes (tzinfo=None). Comparing a naive datetime with `datetime.now(UTC)` (aware) raises `TypeError`. The pattern used:

```python
now = datetime.now(UTC)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=UTC)
return now < dt
```

Applied to both `grace_period_ends_at` and `trial_ends_at` comparisons. Matches the pattern already in use in `followup_task.py` lines 145-147.

## Billing Service Public Contract

```python
LS_STATUS_MAP: dict[str, str]           # 7-entry status mapping dict
map_ls_status(ls_status: str) -> str    # returns "expired" for unknowns
is_subscription_active(dealership) -> bool  # pure Python, no I/O, no async
```

All exports are importable from `src.services.billing`.

## Test Results

- 150 passed, 3 warnings — zero regressions
- All 14 inline behavioral assertions for billing.py confirmed passing
- Migration file parses without syntax error
- All 6 ORM columns accessible on Dealership instances

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `alembic/versions/007_billing_subscription_columns.py` — exists, revision="007", down_revision="006"
- `src/db/models.py` — Dealership has all 6 new nullable columns
- `src/services/billing.py` — all 14 assertions pass
- Commit `bc0303d` — verified in git log
