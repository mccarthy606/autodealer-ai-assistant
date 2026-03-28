---
plan: 11-02
phase: 11-mercadolibre-inventory-sync
status: complete
subsystem: tasks/celery
tags: [celery, mercadolibre, inventory-sync, beat-schedule]
dependency_graph:
  requires: [11-01]
  provides: [sync_ml_inventory_all_dealers Celery task, ml-inventory-sync-every-4h beat schedule]
  affects: [src/tasks/import_tasks.py, src/tasks/celery_app.py]
tech_stack:
  added: []
  patterns: [asyncio.run inside sync Celery task, per-dealer token via sync_all_listings]
key_files:
  created: []
  modified:
    - src/tasks/import_tasks.py
    - src/tasks/celery_app.py
decisions:
  - Used asyncio.run() to call async sync_all_listings from synchronous Celery worker context
  - Filtered sold-item marking to source=="mercadolibre" only to avoid touching sheet/manual inventory
  - Upsert by ml_item_id per dealer, with fallback defaults (year=2000, brand/model="Desconocido")
metrics:
  duration: ~5 minutes
  completed: 2026-03-28
  tasks_completed: 2
  files_modified: 2
---

# Phase 11 Plan 02: ML Inventory Sync Celery Task Summary

Implemented the `sync_ml_inventory_all_dealers` Celery task and `_sync_dealer_inventory` helper, plus registered a 4-hour beat schedule entry to drive periodic MercadoLibre inventory synchronisation across all configured dealerships.

## What Was Done

### Task 1 — src/tasks/import_tasks.py

Added missing imports (`asyncio`, `time`, `datetime`/`UTC`, `select`, `Dealership`, `Event`) to the existing import block.

Added two functions at the bottom of the file:

**`sync_ml_inventory_all_dealers()`** — Celery task registered with explicit task name. Queries all `Dealership` rows where `ml_access_token IS NOT NULL AND ml_user_id IS NOT NULL`, calls `_sync_dealer_inventory()` for each, accumulates totals, commits once, returns summary dict.

**`_sync_dealer_inventory(session, dealer)`** — synchronous helper (not a Celery task). Calls `asyncio.run(adapter.sync_all_listings(dealer.id, dealer))` to fetch all active ML listings with pagination. Upserts `InventoryItem` rows by `ml_item_id`. After processing active items, marks any previously-available `source=="mercadolibre"` items whose `ml_item_id` is no longer in the active set as `StatusEnum.sold`. Updates dealer sync-stats columns (`ml_last_sync_at/added/updated/sold`) and writes an `Event` row with type `"ml_sync"`.

### Task 2 — src/tasks/celery_app.py

Added `"ml-inventory-sync-every-4h"` entry to `beat_schedule` alongside the existing `followup-every-15-min` entry, with `schedule: 14400` (4 hours in seconds).

## Verification Results

```
python -c "from src.tasks.import_tasks import sync_ml_inventory_all_dealers, _sync_dealer_inventory; print('OK')"
# OK

python -c "from src.tasks.celery_app import celery_app; sched = celery_app.conf.beat_schedule; assert 'ml-inventory-sync-every-4h' in sched; print(list(sched.keys()))"
# ['followup-every-15-min', 'ml-inventory-sync-every-4h']

python -m pytest tests/ -x -q 2>&1 | tail -5
# 201 passed, 5 warnings in 2.15s
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- src/tasks/import_tasks.py — modified, functions present
- src/tasks/celery_app.py — modified, beat schedule entry present
- Commit 79e7115 — verified
