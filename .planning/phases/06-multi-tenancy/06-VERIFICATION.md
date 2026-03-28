---
phase: 06-multi-tenancy
verified: 2026-03-27T00:00:00Z
status: passed
score: 4/4 must-haves verified
gaps: []
human_verification:
  - test: "Per-dealership login end-to-end"
    expected: "Logging in with dealership username+password scopes admin UI to that dealership's data only"
    why_human: "Requires running server with two real dealership rows and verifying data isolation in browser"
  - test: "Unknown phone_number_id silent 200"
    expected: "Meta receives HTTP 200 with {status: ok} and no retry is triggered when phone_number_id is unrecognized"
    why_human: "Requires live Meta webhook delivery or integration test harness to confirm no 4xx is ever sent"
---

# Phase 6: Multi-Tenancy Verification Report

**Phase Goal:** Multiple dealerships operate on one instance with complete data isolation. Incoming requests are automatically scoped to the correct dealership. WhatsApp webhooks routed by phone_number_id, ML webhooks routed by ml_user_id, admin sessions scoped per dealership. Per-dealership WABA credentials stored in DB.
**Verified:** 2026-03-27
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MT-01: Admin routes query DB filtered by session dealership_id, not a hardcoded constant | VERIFIED | `default_dealership_id` appears only in `admin_dashboard.py` lines 74 and 79 — both are `create_session(resp, settings.default_dealership_id)` calls inside `login_submit` that set the superadmin session value at login time, not query filters. All five admin route files have zero query-level references. |
| 2 | MT-02: `auth_check()` returns `int`; `create_session()` takes `dealership_id`; `get_session_dealership_id()` exists | VERIFIED | `admin_common.py:16` declares `async def auth_check(request) -> Union[int, RedirectResponse]` returning `did` (int). `auth.py:49` declares `async def create_session(response: Response, dealership_id: int)`. `auth.py:69` declares `async def get_session_dealership_id(session_token: Optional[str]) -> Optional[int]`. All three signatures confirmed in source. |
| 3 | MT-03: WA webhook routes by phone_number_id; ML webhook routes by ml_user_id | VERIFIED | `whatsapp_cloud.py:117` — `parse_incoming_message` returns 4-tuple `(phone, text, wamid, phone_number_id)`. `whatsapp_cloud.py:102` — `get_dealership_by_wa(db, phone_number_id)` exists, queries `WHERE whatsapp_phone_number_id = ?`. `webhook_ml.py:11` imports `get_dealership_by_ml` from `mercadolibre`; `webhook_ml.py:43` calls it with `seller_id`. |
| 4 | MT-04: Redis rate limiter keyed per-dealership with prefix `rate:wa:{dealership_id}` | VERIFIED | `webhook_cloud.py:97` — `check_rate_limit(key=phone, ..., prefix=f"rate:wa:{dealership_id}")`. The `dealership_id` is resolved from DB lookup (line 82) before this call; not hardcoded. |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/api/auth.py` | Refactored session management with `dealership_id` | VERIFIED | `create_session`, `get_session_dealership_id`, `is_authenticated`, `remove_session` all present and substantive. In-memory fallback uses `dict[str, int]`. Redis path stores JSON `{"dealership_id": N}`. |
| `src/api/routes/admin_common.py` | `auth_check` returns `int` | VERIFIED | 33-line file, fully implemented. Returns `did` (int) or `RedirectResponse`. |
| `src/api/routes/admin_dashboard.py` | Session-scoped queries, per-dealership login | VERIFIED | All route handlers use `isinstance(did, int)` guard pattern. Login supports per-dealership bcrypt + superadmin fallback. |
| `src/adapters/whatsapp_cloud.py` | Optional per-tenant constructor, 4-tuple parser, `get_dealership_by_wa` | VERIFIED | Constructor accepts `phone_number_id` and `token` params with settings fallback. `parse_incoming_message` returns 4-tuple. `get_dealership_by_wa` is a module-level async function. |
| `src/api/routes/webhook_cloud.py` | Phone_number_id routing, dealership resolution, per-tenant rate key | VERIFIED | Full routing logic implemented. Unknown phone_number_id returns `{"status": "ok"}` (silent 200). Rate key is `f"rate:wa:{dealership_id}"`. |
| `src/api/routes/webhook_ml.py` | `get_dealership_by_ml` import and usage, fallback to `default_dealership_id` | VERIFIED | Imports `get_dealership_by_ml`. Extracts `seller_id` from `user_id`. Falls back to `settings.default_dealership_id` when no dealership found. |
| `alembic/versions/006_multi_tenancy_dealership_columns.py` | Migration adding three columns | NOT DIRECTLY READ — confirmed via SUMMARY self-check: revision="006", down_revision="004", adds whatsapp_access_token/admin_username/admin_password_hash. |
| `tests/test_auth_session.py` | 7 MT-02 tests | VERIFIED (via test run) — 142 tests pass, 20 new added in plan 06-04. |
| `tests/test_multi_tenancy_routing.py` | 13 MT-01/MT-03/MT-04 tests | VERIFIED (via test run) — included in 142 passing tests. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `admin_dashboard.py` login | `auth.py create_session` | `create_session(resp, dealer.id)` and `create_session(resp, settings.default_dealership_id)` | WIRED | Lines 68, 74, 79 — three call sites confirmed |
| `admin_dashboard.py` handlers | `admin_common.auth_check` | `did = await auth_check(request); if not isinstance(did, int): return did` | WIRED | All route handlers use this pattern |
| `webhook_cloud.py` | `whatsapp_cloud.get_dealership_by_wa` | Imported and called with `phone_number_id` from 4-tuple | WIRED | Lines 16-17 import, line 76 call |
| `webhook_cloud.py` | `rate_limit.check_rate_limit` | Called with `prefix=f"rate:wa:{dealership_id}"` | WIRED | Line 95-98 |
| `webhook_ml.py` | `mercadolibre.get_dealership_by_ml` | Imported line 11, called line 43 with `seller_id` | WIRED | Confirmed in source |
| `auth.py create_session` | Redis | `r.set(f"admin:session:{token_hash}", json.dumps({"dealership_id": N}), ex=86400)` | WIRED | Line 59 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `webhook_cloud.py` POST handler | `dealership_id` | `get_dealership_by_wa(db, phone_number_id)` → DB query `WHERE whatsapp_phone_number_id = ?` | Yes — SQLAlchemy select against live DB | FLOWING |
| `admin_dashboard.py dashboard()` | `did` | `auth_check(request)` → `get_session_dealership_id(cookie)` → Redis/in-memory | Yes — reads persisted session | FLOWING |
| `webhook_ml.py` | `dealership_id` | `get_dealership_by_ml(db, seller_id)` → DB query, fallback to `settings.default_dealership_id` | Yes — DB query with defined fallback | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Test suite (all 142 tests) | `python -m pytest tests/ -q --tb=short` | `142 passed, 3 warnings in 2.80s` | PASS |
| MT-01: `default_dealership_id` not used as query filter in admin routes | `grep -rn "default_dealership_id" src/api/routes/admin_*.py` | Only lines 74, 79 in `admin_dashboard.py` (login_submit `create_session` calls — session creation, not queries) | PASS |
| MT-02: `auth_check` signature returns `int` | Read `admin_common.py` | `-> Union[int, RedirectResponse]`, returns `did` on success | PASS |
| MT-03: `parse_incoming_message` returns 4-tuple | Read `whatsapp_cloud.py:117-149` | Returns `(phone, text, wamid, phone_number_id)` | PASS |
| MT-04: Rate key uses dealership prefix | Read `webhook_cloud.py:95-98` | `prefix=f"rate:wa:{dealership_id}"` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MT-01 | 06-01, 06-03 | Data isolation: queries scoped to session dealership_id, not hardcoded constant | SATISFIED | All 5 admin route files use `did` from `auth_check`; only 2 remaining `default_dealership_id` references are session-creation at login (intentional superadmin path per D-08) |
| MT-02 | 06-01 | Tenant middleware: `auth_check` returns `int`; `create_session` takes `dealership_id`; `get_session_dealership_id` exists | SATISFIED | All three confirmed in `auth.py` and `admin_common.py` source |
| MT-03 | 06-02 | Webhook routing: WA by phone_number_id, ML by ml_user_id | SATISFIED | `parse_incoming_message` 4-tuple confirmed; `get_dealership_by_wa` and `get_dealership_by_ml` confirmed in source |
| MT-04 | 06-02 | Redis isolation: rate limiter prefix `rate:wa:{dealership_id}` in webhook_cloud | SATISFIED | Line 97 of `webhook_cloud.py` confirmed |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None detected | — | — | — | — |

No placeholders, TODO stubs, empty returns masking real logic, or hardcoded empty data were found in the verified files. The two `settings.default_dealership_id` references in `admin_dashboard.py` are correct by design (D-08: superadmin fallback path sets session to dealership 1 at login time).

---

### Human Verification Required

#### 1. Per-Dealership Login End-to-End

**Test:** Create two dealerships in the DB with distinct `admin_username`/`admin_password_hash` values. Log in as each and confirm the admin UI shows only that dealership's inventory, conversations, and leads.
**Expected:** Dealer A's login shows Dealer A data; Dealer B's login shows Dealer B data; no cross-contamination.
**Why human:** Requires a running server with real DB rows. Programmatic check cannot confirm rendered HTML shows correct tenant data.

#### 2. Unknown phone_number_id Returns Silent 200

**Test:** Send a POST to `/webhooks/whatsapp_cloud` with a `phone_number_id` that does not match any row in `dealerships`. Observe the HTTP response.
**Expected:** HTTP 200 with body `{"status": "ok"}`. Meta must never receive a 4xx.
**Why human:** Requires a live HTTP client hitting the running server; automated unit tests mock the DB and don't exercise the full ASGI stack for this specific scenario.

---

### Gaps Summary

No gaps. All four MT requirements are implemented and verified in source code. The test suite passes at 142/142. The two `settings.default_dealership_id` usages that remain are intentional by design (D-08: superadmin fallback stores `dealership_id=1` in session at login time — this is session creation, not a query filter bypassing isolation).

---

_Verified: 2026-03-27_
_Verifier: Claude (gsd-verifier)_
