---
plan: 02-02
phase: 02-security-hardening
status: complete
started: 2026-03-27
completed: 2026-03-27
---

# Plan 02-02: Auth Overhaul + Rate Limit Wiring — Summary

## What Was Done

### Task 1: Auth overhaul — Redis sessions + bcrypt + async migration
- Rewrote `src/api/auth.py` with async Redis sessions (TTL 24h) and bcrypt password verification
- Added plaintext backward compat with logged warning
- Secure cookie flag based on database_url (localhost detection)
- In-memory session fallback when Redis unavailable
- Made `auth_check` async in `admin_common.py`
- Updated ~25 callers across 6 admin route files to use `await`

### Task 2: Wire rate limiting
- WhatsApp webhook: 20 req/60s per phone number with 429 + Retry-After
- Admin login: 5 attempts/60s per IP with 429 + Retry-After

## Commits

| Hash | Message |
|------|---------|
| fb8c115 | feat(02-02): auth overhaul (Redis sessions + bcrypt) and rate limit wiring |

## Key Files

### Modified
- `src/api/auth.py` — complete rewrite (async, Redis, bcrypt)
- `src/api/routes/admin_common.py` — async auth_check
- `src/api/routes/admin_dashboard.py` — await + login rate limit
- `src/api/routes/admin_conversations.py` — await auth_check
- `src/api/routes/admin_inventory.py` — await auth_check (11 calls)
- `src/api/routes/admin_leads.py` — await auth_check
- `src/api/routes/admin_settings.py` — await auth_check
- `src/api/routes/webhook_cloud.py` — rate limit wiring

## Self-Check: PASSED

- [x] auth.py contains `bcrypt.checkpw`
- [x] auth.py contains `await get_redis()`
- [x] auth.py contains `admin:session:` key pattern
- [x] All admin routes use `await auth_check`
- [x] webhook_cloud.py has `check_rate_limit` with 429
- [x] admin_dashboard.py login has `check_rate_limit` with 429
- [x] Both have Retry-After headers
