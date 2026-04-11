# Phase 11: MercadoLibre Inventory Sync — Research

**Status:** RESEARCH COMPLETE
**Confidence:** HIGH

## Summary

No new dependencies needed. Every library required (celery, httpx, sqlalchemy, fastapi, jinja2) is already installed. This is pure wiring work.

## Key Findings

### 1. ML Adapter — Pagination Gap
`sync_listings()` in `src/adapters/mercadolibre.py` fetches only the first 50 items (`?status=active&limit=50`) with no pagination. A new `sync_all_listings(dealership_id, dealer)` method must be added using offset/paging.total loop. The existing `sync_listings()` should remain unchanged (backward compat).

ML API pagination pattern:
```
GET /users/{user_id}/items/search?status=active&limit=50&offset=0
GET /users/{user_id}/items/search?status=active&limit=50&offset=50
...until results == [] or paging.total reached
```
Response includes `paging.total`, `paging.offset`, `paging.limit` and `results` (array of item IDs).

### 2. Schema Change — Migration 009
Four nullable columns on `dealerships` to store sync results for D-08 status display:
- `ml_last_sync_at` — DateTime (when last sync ran)
- `ml_last_sync_added` — Integer (new items count)
- `ml_last_sync_updated` — Integer (updated items count)
- `ml_last_sync_sold` — Integer (marked sold count)

These columns avoid an extra query on page load — just read from Dealership row.

### 3. Mark-Sold Safety Filter (CRITICAL)
The stale-item query MUST filter `source == "mercadolibre"`. Without this, manually-added or CSV-imported cars with `status=available` would incorrectly be marked as `sold` when ML sync runs.

Pattern:
```python
# Get all ML-sourced items currently available
stmt = select(InventoryItem).where(
    InventoryItem.dealership_id == dealer.id,
    InventoryItem.source == "mercadolibre",
    InventoryItem.status == StatusEnum.available,
)
```
Then compute: `active_ids_from_ml - ids_in_db_available` → mark those as `sold`.

### 4. Multi-Tenant Adapter Fix
`MercadoLibreAdapter.__init__()` reads `settings.ml_user_id` (global). For multi-dealer sync, must override `adapter.user_id` per dealer before calling sync:
```python
adapter = MercadoLibreAdapter()
adapter.user_id = dealer.ml_user_id
adapter.token = await get_valid_token(dealer.id, dealer)
adapter.is_configured = bool(adapter.token and adapter.user_id)
```

### 5. Celery Task Architecture
Use `asyncio.run()` pattern from `followup_task.py` — Celery workers are sync, ML calls are async.
Use `SyncSession` from `import_tasks.py` for DB operations in Celery context.

Single task looping all dealers (not per-dealer tasks) — correct at current scale.

Beat schedule entry:
```python
"ml-inventory-sync-every-4h": {
    "task": "src.tasks.import_tasks.sync_ml_inventory_all_dealers",
    "schedule": 14400,  # 4 hours in seconds
},
```

### 6. Upsert Key
Use `ml_item_id` as the upsert key (not `external_id`). The unique index `ix_inv_external_id` is on `(dealership_id, external_id)` — ML-synced items should NOT use this index. Instead:
```python
stmt = select(InventoryItem).where(
    InventoryItem.dealership_id == dealer_id,
    InventoryItem.ml_item_id == item["ml_item_id"],
)
```

### 7. Admin UI — Cars Page Changes
- `src/templates/admin/cars.html` — add button + status line at top
- `src/api/routes/admin_inventory.py` — add `POST /admin/ui/cars/sync-ml` route
- Route triggers `sync_ml_inventory_all_dealers.delay()` (or per-dealer variant)
- Returns JSON `{status: "ok", message: "Sincronizando..."}` (async, task runs in background)
- On next page load, reads `dealer.ml_last_sync_at` etc. to show status

### 8. Event Logging
Reuse existing `Event` model — store sync result as:
```python
Event(dealership_id=did, type="ml_sync", payload={
    "added": N, "updated": N, "sold": N, "errors": [],
    "duration_seconds": N
})
```

## Implementation Plan Sketch

**Wave 1 (no dependencies):**
- Plan A: Migration 009 + Dealership model columns + MercadoLibreAdapter.sync_all_listings() with pagination
- Plan B: Celery task sync_ml_inventory_all_dealers + beat schedule

**Wave 2 (depends on Wave 1):**
- Plan C: Admin UI — POST /sync-ml route + cars.html button/status + Event logging + tests

## File Map

| File | Change |
|------|--------|
| `alembic/versions/009_ml_sync_columns.py` | New migration |
| `src/db/models.py` | 4 new columns on Dealership |
| `src/adapters/mercadolibre.py` | Add `sync_all_listings()` with pagination |
| `src/tasks/import_tasks.py` | Add `sync_ml_inventory_all_dealers` Celery task |
| `src/tasks/celery_app.py` | Add beat schedule entry |
| `src/api/routes/admin_inventory.py` | Add `POST /cars/sync-ml` route |
| `src/templates/admin/cars.html` | Add sync button + status line |
| `tests/test_ml_sync.py` | New test file |
