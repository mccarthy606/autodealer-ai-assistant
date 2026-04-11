# Phase 11: MercadoLibre Inventory Sync - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Pull ML listings into InventoryItems DB per dealer using the ML API. Celery beat auto-syncs every 4 hours. Manual trigger from cars page. AI agent (Phase 12) operates on this data.

This phase does NOT include: publishing listings TO ML, AI response logic, or the Phase 12 LLM integration.

</domain>

<decisions>
## Implementation Decisions

### Sync Method
- **D-01:** API-based sync (`sync_listings()`) is the primary method — uses `ml_access_token` + `ml_user_id` from Dealership table (saved in Phase 10). `fetch_seller_items_public()` (HTML scraping) is reserved as a fallback only if token is missing, not a first-class path.
- **D-02:** Full pagination — loop through all pages using `offset` until ML returns empty results. Do NOT limit to first 50 items. A dealer may have 200+ cars.

### Sold/Inactive Items
- **D-03:** ML is the source of truth for status. When an item exists in DB with `status=available` but is absent from the current active ML listing — auto-mark it `status=sold`. Dealer can override manually.

### Data Conflicts
- **D-04:** ML always wins. Every sync overwrites price, km, photos, title from ML data. Dealers edit prices in ML, not in Admin UI. No partial-update logic needed.

### Sync Frequency & Trigger
- **D-05:** Celery beat auto-sync every 4 hours (schedule: 14400 seconds). Add `ml-sync-every-4h` task to beat_schedule in `celery_app.py`.
- **D-06:** Manual trigger button on the inventory page (`/admin/ui/cars`) — "Sincronizar desde MercadoLibre". Runs the sync task immediately via `.delay()`.
- **D-07:** Auto-sync runs only for Dealerships where `ml_access_token IS NOT NULL`. Skip unconfigured dealers silently.

### UI / Status Display
- **D-08:** Manual sync button is on the inventory page (`/admin/ui/cars`), not on the integrations page.
- **D-09:** After sync (manual or auto), store result in DB or Redis and display: `"Sincronizado: {updated} actualizados, {added} nuevos, {sold} marcados vendidos — hace {N} min"`. Show this line on the cars page.

### Upsert Key
- **D-10:** Upsert by `ml_item_id` (not `external_id`) for ML-sourced items. `source = "mercadolibre"`. Existing CSV/manual items (different source) are not touched by ML sync.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing ML Adapter
- `src/adapters/mercadolibre.py` — `sync_listings()`, `_fetch_items_details()`, `_parse_ml_item()` all exist. Full pagination needs to be added to `sync_listings()`. Scraping fallback in `fetch_seller_items_public()`.

### Inventory Model
- `src/db/models.py` — `InventoryItem` has: `ml_item_id`, `source`, `status` (StatusEnum: available/sold/etc), `external_id`, `photos` (JSONB), `price`, `km`, `brand`, `model`, `year`, `condition`.
- `ix_inv_external_id` is a unique index on `(dealership_id, external_id)` — upsert by `ml_item_id` needs its own query pattern (select → update or insert), NOT the external_id index.

### Existing Import Pattern
- `src/tasks/import_tasks.py` — `import_from_google_sheet()` is the Celery task pattern to follow. Uses `SyncSession` (sync SQLAlchemy session for Celery workers).
- `src/api/routes/import_routes.py` — CSV import upsert logic pattern.

### Celery Beat
- `src/tasks/celery_app.py` — existing `beat_schedule` with `followup-every-15-min`. Add `ml-sync-every-4h` alongside it.

### Per-Dealer Credentials
- `src/db/models.py` — `Dealership.ml_access_token`, `Dealership.ml_user_id`, `Dealership.ml_refresh_token` (Phase 10 additions).
- `src/services/ml_token_manager.py` — `get_valid_token(dealership_id, dealer)` handles token refresh per dealer.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MercadoLibreAdapter.sync_listings()`: fetches active item IDs, then calls `_fetch_items_details()` in batches of 20. Returns list of parsed dicts. Needs pagination added (currently hardcoded `limit=50`).
- `_parse_ml_item()`: parses ML API response → dict with all InventoryItem fields. Already handles brand/model extraction from attributes and title fallback.
- `import_from_google_sheet()`: Celery task pattern with `SyncSession` — copy this pattern for `sync_ml_inventory()` task.
- `MercadoLibreAdapter._ensure_token()`: already calls `get_valid_token(dealership_id, dealer)` — works per-dealer.

### Established Patterns
- Celery tasks use sync SQLAlchemy session (`SyncSession` from `sync_engine`) — async sessions don't work in Celery workers.
- CSV import uses upsert pattern: `select by key → update existing or insert new`.
- Beat schedule: add to `beat_schedule` dict in `celery_app.conf.update()`.

### Integration Points
- New Celery task: `src/tasks/import_tasks.py` (add `sync_ml_inventory` task)
- Beat schedule: `src/tasks/celery_app.py` (add entry)
- Admin UI: `src/api/routes/admin_inventory.py` + `src/templates/admin/cars.html` (add button + status line)
- New route: `POST /admin/ui/cars/sync-ml` → triggers task, returns result

</code_context>

<specifics>
## Specific Ideas

- Sync result should be stored so it's visible on page refresh (not just flash message). Use a simple `Event` row (dealership_id, type="ml_sync", payload={added, updated, sold, timestamp}) — already available in the Event model.
- The cars page already shows an ML cars table in the integrations page (from Phase 10). After Phase 11, the primary inventory table on the cars page becomes the source of truth.
- Pagination: ML API uses `scroll_id` or `offset` — test which works for `/users/{id}/items/search`. Use offset-based pagination (offset=0, 50, 100...) until results is empty.

</specifics>

<deferred>
## Deferred Ideas

- Publishing listings FROM admin TO MercadoLibre — different direction, own phase
- Scraping fallback as automatic switch (when API returns 401) — could be added later as resilience improvement
- Per-dealer configurable sync frequency — keep it simple for now, 4h for all

</deferred>

---

*Phase: 11-mercadolibre-inventory-sync*
*Context gathered: 2026-03-28*
