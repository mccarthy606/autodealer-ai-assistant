---
phase: 10-client-integration-setup
plan: "02"
subsystem: ml-token-manager
tags: [ml, oauth, redis, multi-tenancy, per-dealer]
dependency_graph:
  requires: [10-01]
  provides: [per-dealer-ml-token-management]
  affects: [src/services/ml_token_manager.py, src/adapters/mercadolibre.py]
tech_stack:
  added: []
  patterns: [per-dealer-redis-key-namespacing, db-first-credential-fallback]
key_files:
  created: []
  modified:
    - src/services/ml_token_manager.py
    - src/adapters/mercadolibre.py
decisions:
  - "Per-dealer Redis key namespacing: ml:{did}:access_token pattern used consistently across all 4 keys"
  - "DB-first credential reads in _do_refresh: dealer object checked before settings singleton"
  - "Settings singleton mutation removed: _do_refresh no longer writes to settings.ml_access_token or settings.ml_refresh_token"
  - "_ensure_token default args (dealership_id=1, dealer=None) preserve backward compatibility for existing no-arg callers"
metrics:
  duration: "8min"
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_modified: 2
---

# Phase 10 Plan 02: Per-Dealer ML Token Namespacing Summary

## One-liner

Per-dealer Redis key namespacing for ML OAuth tokens (ml:{did}:access_token) with DB-first credential reads and settings singleton mutation removed.

## What Was Built

Refactored `ml_token_manager.py` from a single global token store to a per-dealer namespaced model. Added `_ml_keys(did)` helper that generates four dealer-scoped Redis keys. Updated all internal helpers to accept `did` and `dealer` parameters. Removed settings singleton mutation. Updated `MercadoLibreAdapter._ensure_token()` to accept and forward dealer context while preserving backward compatibility.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Refactor ml_token_manager.py for per-dealer key namespacing | 3a15897 | src/services/ml_token_manager.py |
| 2 | Update MercadoLibreAdapter._ensure_token() to pass dealer context | 2364437 | src/adapters/mercadolibre.py |

## Key Changes

### ml_token_manager.py

- Removed global constants: `REDIS_TOKEN_KEY`, `REDIS_REFRESH_KEY`, `REDIS_EXPIRES_KEY`
- Added `_ml_keys(did: int) -> tuple[str, str, str, str]` returning `(token_key, refresh_key, expires_key, lock_key)` all namespaced as `ml:{did}:*`
- Changed `get_valid_token()` signature to `async def get_valid_token(dealership_id: int = 1, dealer=None) -> str`
- Changed `_read_from_redis(redis, did: int)`, `_refresh_with_lock(redis, did: int, dealer=None)`, `_do_refresh(redis, did: int, dealer=None)`
- DB-first credential resolution in `_do_refresh`: `dealer.ml_refresh_token/ml_app_id/ml_client_secret` before `settings.*`
- Removed `settings.ml_access_token = new_access` and `settings.ml_refresh_token = new_refresh` mutations

### mercadolibre.py

- Updated `_ensure_token(self, dealership_id: int = 1, dealer=None) -> None`
- Forwards `dealership_id=dealership_id, dealer=dealer` to `get_valid_token()`
- All existing callers (`send_text`, `sync_listings`, `get_questions`, `get_buyer_contact`) use `await self._ensure_token()` with no args — continue to work unchanged via defaults

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Both files are fully wired. Per-dealer token resolution requires callers to pass `dealership_id` and `dealer` — existing callers fall back to defaults (dealer 1, no dealer object).

## Self-Check: PASSED

- `src/services/ml_token_manager.py` exists and passes `ast.parse()`
- `src/adapters/mercadolibre.py` exists and passes `ast.parse()`
- Commit `3a15897` exists: `feat(10-02): refactor ml_token_manager for per-dealer Redis key namespacing`
- Commit `2364437` exists: `feat(10-02): update MercadoLibreAdapter._ensure_token to pass dealer context`
- `grep "settings.ml_access_token = "` returns nothing (mutation removed)
- `grep "ml:{did}:access_token"` finds the `_ml_keys` f-string line
