---
phase: 02-security-hardening
plan: 01
subsystem: security
tags: [cors, hmac, rate-limiting, webhook, lemon-squeezy]

# Dependency graph
requires:
  - phase: 01-conversation-engine
    provides: existing FastAPI app with config, routes, rate_limit module
provides:
  - CORS locked to configurable origins via ALLOWED_ORIGINS
  - admin_password_hash config field for bcrypt auth (used by Plan 02)
  - Lemon Squeezy webhook with HMAC-SHA256 signature verification
  - Generic rate limiter with prefix and retry_after support
affects: [02-02-auth-overhaul, 08-billing]

# Tech tracking
tech-stack:
  added: []
  patterns: [hmac-signature-verification, generic-rate-limiting-with-prefix]

key-files:
  created:
    - src/api/routes/webhook_lemon.py
    - tests/test_security_foundations.py
    - tests/test_webhook_lemon.py
  modified:
    - src/config.py
    - src/main.py
    - src/api/rate_limit.py
    - .env.example

key-decisions:
  - "Empty ALLOWED_ORIGINS = deny all cross-origin (admin UI is same-origin Jinja2, unaffected)"
  - "Rate limiter returns tuple (allowed, retry_after) instead of bare bool for better client UX"
  - "Webhook reads raw body before JSON parse to prevent stream exhaustion"

patterns-established:
  - "HMAC webhook verification: read raw body, verify signature, then parse JSON"
  - "Rate limiter generic prefix pattern: f'{prefix}:{key}' for reuse across features"

requirements-completed: [SEC-01, SEC-03, SEC-04]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 02 Plan 01: Security Foundations Summary

**CORS lockdown via configurable origins, Lemon Squeezy HMAC-SHA256 webhook, and generic rate limiter with prefix/retry_after**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T21:14:02Z
- **Completed:** 2026-03-27T21:17:59Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- CORS no longer uses wildcard -- configurable via ALLOWED_ORIGINS env var (empty = deny all)
- Lemon Squeezy webhook at /webhooks/lemon-squeezy verifies HMAC-SHA256 signature before processing
- Rate limiter refactored to generic prefix pattern with (allowed, retry_after) tuple return
- Three new security config fields ready for Plan 02 and Phase 8

## Task Commits

Each task was committed atomically:

1. **Task 1: Config + CORS lockdown + rate_limit refactor** - `0568293` (test: RED) + `646c2dd` (feat: GREEN)
2. **Task 2: Lemon Squeezy webhook with HMAC signature verification** - `50eef00` (test: RED) + `89fb68b` (feat: GREEN)

_Note: TDD tasks have RED (failing test) and GREEN (implementation) commits._

## Files Created/Modified
- `src/config.py` - Added allowed_origins, admin_password_hash, lemon_squeezy_webhook_secret fields
- `src/main.py` - CORS reads from settings.allowed_origins; registered lemon_router
- `src/api/rate_limit.py` - Generic check_rate_limit with prefix param and tuple return
- `src/api/routes/webhook_lemon.py` - New webhook with HMAC-SHA256 signature verification
- `.env.example` - Added ALLOWED_ORIGINS, ADMIN_PASSWORD_HASH, LEMON_SQUEEZY_WEBHOOK_SECRET
- `tests/test_security_foundations.py` - 8 tests for config, CORS, rate limiter
- `tests/test_webhook_lemon.py` - 8 tests for webhook signature verification and endpoint responses

## Decisions Made
- Empty ALLOWED_ORIGINS results in empty list (deny all cross-origin) -- admin UI is same-origin Jinja2 so unaffected
- Rate limiter returns (bool, int) tuple instead of bare bool for retry_after header support
- Webhook reads raw body first, verifies HMAC, then parses JSON to prevent stream exhaustion

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test mocks for Redis pipeline**
- **Found during:** Task 1 (rate limiter tests)
- **Issue:** AsyncMock for pipeline() caused 'coroutine' object errors because redis pipeline() is synchronous
- **Fix:** Used MagicMock for pipeline and its methods, AsyncMock only for execute()
- **Files modified:** tests/test_security_foundations.py
- **Verification:** All 8 rate limiter tests pass
- **Committed in:** 646c2dd (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test setup)
**Impact on plan:** Minor test mock adjustment. No scope creep.

## Issues Encountered
- Pre-existing test failures in test_engine.py and test_inventory.py (SQLAlchemy CompileError) -- not related to our changes, out of scope.

## User Setup Required
None - no external service configuration required. Users must set ALLOWED_ORIGINS, ADMIN_PASSWORD_HASH, and LEMON_SQUEEZY_WEBHOOK_SECRET in .env when deploying.

## Next Phase Readiness
- Config fields ready for Plan 02 (auth overhaul): admin_password_hash available
- Webhook endpoint ready for Phase 8 (billing): event handling placeholder in place
- Rate limiter ready for Plan 02: generic prefix enables per-route rate limiting
- No blockers

---
*Phase: 02-security-hardening*
*Completed: 2026-03-27*
