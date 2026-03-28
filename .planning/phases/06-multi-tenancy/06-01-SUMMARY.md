---
phase: 06-multi-tenancy
plan: 06-01
subsystem: auth, db, admin-ui
tags: [multi-tenancy, auth, alembic, sessions, login]
dependency-graph:
  requires: []
  provides: [dealership-columns, json-sessions, per-dealership-login, auth-check-returns-int]
  affects: [admin_common.py, admin_dashboard.py, auth.py, dealerships-table]
tech-stack:
  added: [json-sessions]
  patterns: [per-dealership-bcrypt-login, superadmin-settings-fallback, token-hash-dict-fallback]
key-files:
  created:
    - alembic/versions/006_multi_tenancy_dealership_columns.py
  modified:
    - src/db/models.py
    - src/api/auth.py
    - src/api/routes/admin_common.py
    - src/api/routes/admin_dashboard.py
    - src/templates/admin/login.html
decisions:
  - "Session value stored as JSON {dealership_id: N} in Redis; old string '1' sessions handled via backward-compat fallback returning 1"
  - "auth_check returns int|RedirectResponse (not raise); transient broken state between 06-01 and 06-03 is acceptable in dev — 06-03 must follow in same deployment session"
  - "get_session_dealership_id takes raw cookie string (not Request) for testability"
  - "Per-dealership login checked first (admin_username match + bcrypt); superadmin fallback uses settings.admin_password / admin_password_hash with dealership_id=default_dealership_id"
metrics:
  duration: ~12 minutes
  completed: 2026-03-27
  tasks: 4
  files: 6
---

# Phase 6 Plan 01: Migration 006 + Auth Multi-Tenant + Per-Dealership Login Summary

Per-dealership credentials and JSON sessions: added three columns to `dealerships`, refactored `auth.py` to store `dealership_id` in session JSON, updated `auth_check` to return `int`, and wired per-dealership bcrypt login with settings-level superadmin fallback.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Alembic migration 006 | fcb7473 | alembic/versions/006_multi_tenancy_dealership_columns.py |
| 2 | Dealership model columns | fcb7473 | src/db/models.py |
| 3a | auth.py refactor | fcb7473 | src/api/auth.py |
| 3b | admin_common.py auth_check | fcb7473 | src/api/routes/admin_common.py |
| 3c | admin_dashboard.py login | fcb7473 | src/api/routes/admin_dashboard.py |
| 3d | login.html username field | fcb7473 | src/templates/admin/login.html |

## What Was Built

### Migration 006
`alembic/versions/006_multi_tenancy_dealership_columns.py` — `revision="006"`, `down_revision="004"`. Adds `whatsapp_access_token VARCHAR(512)`, `admin_username VARCHAR(128)`, `admin_password_hash VARCHAR(255)` to `dealerships`. Downgrade drops them in reverse order.

### Dealership Model
Three nullable columns appended after `ml_user_id` in `src/db/models.py`. No relationships or indexes touched.

### auth.py Refactor
- `_admin_sessions` changed from `set[str]` to `dict[str, int]` (token_hash -> dealership_id).
- `create_session(response, dealership_id: int)` — stores `json.dumps({"dealership_id": N})` in Redis; in-memory fallback stores int in dict.
- `get_session_dealership_id(session_token: Optional[str]) -> Optional[int]` — new helper; json.loads with backward-compat fallback for old `"1"` string sessions.
- `is_authenticated` — delegates to `get_session_dealership_id`, returns `True` if not None.
- `remove_session` — uses `dict.pop(key, None)` instead of `set.discard`.

### admin_common.py
`auth_check(request)` now returns `int` (dealership_id) on success or `RedirectResponse` on failure. Imports `get_session_dealership_id` from `auth.py`. Existing `if redir: return redir` call sites still compile; 06-03 will update them to the `isinstance` pattern.

### admin_dashboard.py Login Route
`login_submit` gains `db: AsyncSession = Depends(get_db)`. New flow:
1. Extract `username` and `password` from form.
2. If `username` non-empty: query `Dealership.admin_username == username`, run `bcrypt.checkpw`; on match call `create_session(resp, dealer.id)`.
3. Superadmin fallback: check `settings.admin_password` / `admin_password_hash`; call `create_session(resp, settings.default_dealership_id)`.

### login.html
Username input (`type="text"`, `name="username"`, `placeholder="Usuario"`) added above the password field. Field is optional — leaving it blank triggers the superadmin path.

## Deviations from Plan

None — plan executed exactly as written.

## Deployment Note

**CRITICAL:** `auth_check` now returns `int | RedirectResponse`. Existing call sites (`if redir: return redir`) will return the int to the client on success paths until 06-03 updates them. **06-01 and 06-03 must be applied in the same deployment session — do not start the server between these two plans.**

## Verification Results

```
python -c "from src.api.auth import create_session, get_session_dealership_id, is_authenticated; print('auth ok')"
# auth ok

python -c "from src.api.routes.admin_common import auth_check; print('common ok')"
# common ok

python -c "from src.db.models import Dealership; print([c.key for c in Dealership.__table__.columns])"
# [..., 'whatsapp_access_token', 'admin_username', 'admin_password_hash', ...]

python -m pytest tests/ -x -q --tb=short
# 122 passed, 3 warnings in 2.76s
```

## Known Stubs

None.

## Self-Check: PASSED

- [x] `alembic/versions/006_multi_tenancy_dealership_columns.py` exists with `revision = "006"` and `down_revision = "004"`
- [x] `Dealership` model has `whatsapp_access_token`, `admin_username`, `admin_password_hash`
- [x] `create_session(response, dealership_id)` stores JSON `{"dealership_id": N}` in Redis
- [x] `get_session_dealership_id(token)` returns `int | None`
- [x] `is_authenticated` still returns `bool`
- [x] `auth_check(request)` returns `int` (dealership_id) or `RedirectResponse`
- [x] Login POST supports per-dealership username+password AND superadmin fallback
- [x] `login.html` has a `username` input field
- [x] All 122 existing tests pass
- [x] Deployment note recorded: 06-01 and 06-03 must be applied in same deployment session
