---
plan: 01-03
phase: 01-refactoring-tech-debt
status: complete
started: 2026-03-27
completed: 2026-03-27
---

# Plan 01-03: Fix datetime.utcnow() — Summary

## What Was Done

Replaced all 21 occurrences of deprecated `datetime.utcnow()` with `datetime.now(UTC)` across 7 source files.

### Task 1: Fix SQLAlchemy model defaults
- Added `_utcnow()` helper function in `src/db/models.py`
- Replaced 9 model `default=datetime.utcnow` with `default=_utcnow`
- Replaced 2 model `onupdate=datetime.utcnow` with `onupdate=_utcnow`

### Task 2: Fix service and route files
- `src/services/conversation_engine.py` — 3 occurrences
- `src/services/lead_service.py` — 1 occurrence
- `src/api/routes/admin.py` — 1 occurrence
- `src/api/routes/admin_dashboard.py` — 2 occurrences
- `src/api/routes/admin_conversations.py` — 2 occurrences
- `src/api/routes/admin_inventory.py` — 3 occurrences

## Commits

| Hash | Message |
|------|---------|
| 0d3fc74 | fix(01-03): replace all datetime.utcnow() with datetime.now(UTC) |

## Key Files

### Modified
- `src/db/models.py` — added `_utcnow` helper, replaced 11 defaults
- `src/services/conversation_engine.py` — 3 replacements
- `src/services/lead_service.py` — 1 replacement
- `src/api/routes/admin.py` — 1 replacement
- `src/api/routes/admin_dashboard.py` — 2 replacements
- `src/api/routes/admin_conversations.py` — 2 replacements
- `src/api/routes/admin_inventory.py` — 3 replacements

## Self-Check: PASSED

- [x] Zero occurrences of `datetime.utcnow` in src/ (grep verified)
- [x] All files import `UTC` from datetime
- [x] Model defaults use `_utcnow` helper
