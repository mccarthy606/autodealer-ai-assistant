---
plan: 11-03
status: complete
phase: 11-mercadolibre-inventory-sync
subsystem: admin-ui, inventory-sync
tags: [mercadolibre, admin, celery, tests]
key-files:
  modified:
    - src/api/routes/admin_inventory.py
    - src/templates/admin/cars.html
  created:
    - tests/test_ml_sync.py
decisions:
  - Added JSONResponse import and Dealership model import to admin_inventory.py to support new route and template data
  - ML sync button only renders when dealer has ml_access_token set, preventing UI clutter for non-ML dealers
metrics:
  completed: 2026-03-28
  tasks: 3
  files_modified: 2
  files_created: 1
  tests_added: 6
  tests_total_passing: 207
---

# Phase 11 Plan 03: ML Sync Button — Admin UI Summary

Added a manual MercadoLibre sync trigger to the Admin UI cars page with a POST API route and 6 unit tests covering all sync scenarios.

## What Was Done

### Task 1 — admin_inventory.py

Two changes to `src/api/routes/admin_inventory.py`:

1. **cars_list route**: Now fetches the `Dealership` row for the authenticated dealer and passes `dealer` to the template context, enabling the template to conditionally render ML-related UI.

2. **POST /cars/sync-ml route**: New endpoint that calls `sync_ml_inventory_all_dealers.delay()` via Celery and returns `{"status": "ok", "message": "Sincronizando..."}`. Auth-checked via `auth_check`.

Imports updated: added `JSONResponse` to `fastapi.responses` import, added `Dealership` to `src.db.models` import.

### Task 2 — cars.html

Inserted an ML sync card at the top of `{% block content %}` in `src/templates/admin/cars.html`. The card only renders when `dealer and dealer.ml_access_token` is truthy. It shows:
- Last sync stats (added/updated/sold) if `ml_last_sync_at` is set, otherwise "Nunca sincronizado"
- A "Sincronizar desde MercadoLibre" button that POSTs to `/admin/ui/cars/sync-ml` via `fetch()`, disables itself during the request, shows status message, then reloads the page after 3 seconds.

### Task 3 — tests/test_ml_sync.py

Created 6 unit tests using `unittest.mock`, all passing (207 total suite passes):

| Test | What it covers |
|------|----------------|
| `test_sync_skips_unconfigured_dealer` | `sync_ml_inventory_all_dealers` returns zero counts when no ML-configured dealers exist |
| `test_sync_adds_new_items` | New ML items create `InventoryItem` rows with `source="mercadolibre"` and `status=available` |
| `test_sync_updates_existing_item` | Existing items get price updated; result counts `updated=1, added=0` |
| `test_sync_marks_sold` | Items present in DB but absent from ML response get `status=sold` |
| `test_sync_does_not_mark_csv_items_sold` | CSV-sourced items are not touched by the sold-marking logic |
| `test_sync_logs_event` | An `Event(type="ml_sync")` with `added/updated/sold/duration_seconds` keys is logged |

## Deviations from Plan

None — plan executed exactly as written. One minor cleanup: the original file had a duplicate `from fastapi.responses import HTMLResponse, RedirectResponse` line that was consolidated with the new `JSONResponse` addition into a single clean import line.

## Self-Check

- `src/api/routes/admin_inventory.py` — modified, committed 9647c3d
- `src/templates/admin/cars.html` — modified, committed 9647c3d
- `tests/test_ml_sync.py` — created, committed 9647c3d
- Route `/admin/ui/cars/sync-ml` present: verified True
- Template contains "Sincronizar desde MercadoLibre": verified True
- 6 new tests: all PASSED
- Full suite: 207 passed

## Self-Check: PASSED
