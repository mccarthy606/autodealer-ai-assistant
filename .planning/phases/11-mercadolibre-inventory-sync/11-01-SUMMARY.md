---
plan: 11-01
phase: 11-mercadolibre-inventory-sync
status: complete
completed_date: 2026-03-28
duration_minutes: 5
tasks_completed: 3
tasks_total: 3
files_created:
  - alembic/versions/009_ml_sync_columns.py
files_modified:
  - src/db/models.py
  - src/adapters/mercadolibre.py
commits:
  - hash: 51c0e80
    message: "feat(11-01): add ML sync columns, Dealership ORM fields, and sync_all_listings()"
key_decisions:
  - "Used lazy import of get_valid_token inside sync_all_listings() to match existing pattern in _ensure_token()"
  - "Pagination terminates on empty results OR offset >= paging.total — handles both exact-count and empty-last-page edge cases"
tags: [mercadolibre, sync, migration, orm, pagination]
---

# Phase 11 Plan 01: ML Sync Columns + Adapter Method Summary

Added the foundational database columns and adapter method that Phase 11's Celery task (Plan 02) and Admin UI (Plan 03) depend on.

## What Was Done

**Task 1 — Migration 009 (`alembic/versions/009_ml_sync_columns.py`)**

Created Alembic migration with `revision = "009"` and `down_revision = "008"`. The `upgrade()` function adds 4 nullable columns to the `dealerships` table:

- `ml_last_sync_at` (DateTime, nullable) — timestamp of last completed sync
- `ml_last_sync_added` (Integer, nullable) — count of items added during last sync
- `ml_last_sync_updated` (Integer, nullable) — count of items updated during last sync
- `ml_last_sync_sold` (Integer, nullable) — count of items marked sold during last sync

The `downgrade()` drops all 4 in reverse order.

**Task 2 — Dealership ORM model (`src/db/models.py`)**

Added the 4 matching columns to the `Dealership` class after `ml_client_secret`. Used already-imported `DateTime` and `Integer` types — no new imports added. All 4 are nullable with no default, remaining NULL until the first sync runs.

**Task 3 — `MercadoLibreAdapter.sync_all_listings()` (`src/adapters/mercadolibre.py`)**

Added new method immediately after the existing `sync_listings()` (which was left unchanged for backward compatibility). Key behaviors:

- Accepts `dealership_id: int` and `dealer` (ORM row) arguments
- Sets `self.token` via `get_valid_token(dealership_id, dealer)` — supports per-dealer OAuth tokens
- Sets `self.user_id` from `getattr(dealer, "ml_user_id", None)` — safe fallback for mock objects
- Returns `[]` early if not configured
- Paginates with `limit=50&offset=N`, incrementing offset by `len(page_ids)` each iteration
- Loop exits when `results == []` OR `offset >= paging["total"]`
- Delegates batch detail fetching to existing `_fetch_items_details(client, all_item_ids)`
- Catches all exceptions, logs with dealer context, returns `[]` on error

## Verification Results

```
Dealership columns OK: ['ml_last_sync_at', 'ml_last_sync_added', 'ml_last_sync_updated', 'ml_last_sync_sold']
sync_all_listings OK
revision = "009" / down_revision = "008"
201 passed, 5 warnings in 2.25s
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All new columns are intentionally NULL until the Celery sync task (Plan 02) writes to them.

## Self-Check: PASSED

- `alembic/versions/009_ml_sync_columns.py` — FOUND
- `src/db/models.py` updated with 4 columns — FOUND
- `src/adapters/mercadolibre.py` with `sync_all_listings` — FOUND
- Commit `51c0e80` — FOUND
- 201 tests pass — CONFIRMED
