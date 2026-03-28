---
phase: 10-client-integration-setup
verified: 2026-03-28T16:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
human_verification:
  - test: "Open /admin/ui/integrations in a browser, enter credentials, click Guardar credenciales"
    expected: "Page redirects to /admin/ui/integrations?saved=1 with 'Credenciales guardadas.' alert; credentials are visible as non-blank placeholders on next load"
    why_human: "Full form-submit flow requires a running app and DB; can only verify template/route code statically"
  - test: "Click Verificar conexion for WhatsApp with valid credentials stored in DB"
    expected: "Inline span shows checkmark + phone display name without page reload"
    why_human: "Requires live Meta Graph API and a valid token; network call cannot be made statically"
  - test: "Click Verificar conexion for MercadoLibre with valid ML token"
    expected: "Inline span shows checkmark + ML nickname"
    why_human: "Requires live MercadoLibre API and a valid access_token"
  - test: "Send a WhatsApp message to a phone_number_id NOT stored in dealerships table"
    expected: "Message is processed using the default dealership (id=1); logger.info 'not in DB, using default dealership=1' appears in logs"
    why_human: "Requires running app, Postgres DB, and an incoming webhook POST"
---

# Phase 10: Client Integration Setup — Verification Report

**Phase Goal:** Dealership owner can connect WhatsApp Business and MercadoLibre through the Admin UI — no .env editing, no docker commands required
**Verified:** 2026-03-28T16:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dealership credentials stored in dealerships table (not only .env) | VERIFIED | `alembic/versions/008_client_integration_columns.py` adds exactly 5 columns; `src/db/models.py` lines 109-113 confirm all 5 Column definitions |
| 2 | Admin integrations page has a form for WA and ML credentials labeled in Spanish | VERIFIED | `src/templates/admin/integrations.html` — 4 WA fields + 5 ML fields, all labeled in Spanish; outer `<form action="/admin/ui/integrations">` present |
| 3 | "Verificar conexion" button makes a live API call and shows result inline without page reload | VERIFIED | Template has AJAX `testConnection()` JS calling `POST /admin/ui/integrations/test-connection`; backend calls `graph.facebook.com/v18.0/{phone_id}` and `api.mercadolibre.com/users/me`; result set on span without redirect |
| 4 | WhatsApp webhooks route by phone_number_id from DB with fallback to default dealership | VERIFIED | `src/api/routes/webhook_cloud.py` lines 92-112: two-stage fallback — DB lookup by phone_number_id then `settings.default_dealership_id` fallback; Meta always receives 200 |
| 5 | ML token manager uses per-dealership Redis keys (ml:{did}:access_token) | VERIFIED | `src/services/ml_token_manager.py` — `_ml_keys(did)` helper returns `(ml:{did}:access_token, ml:{did}:refresh_token, ml:{did}:token_expires_at, ml:{did}:refresh_lock)`; all 4 functions parameterized by `did`; settings singleton mutation removed |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `alembic/versions/008_client_integration_columns.py` | Schema migration adding 5 credential columns | VERIFIED | revision="008", down_revision="007"; exactly 5 op.add_column calls; reversible downgrade; `whatsapp_access_token` correctly excluded |
| `src/db/models.py` | Updated Dealership ORM model with 5 new columns | VERIFIED | Lines 109-113: all 5 columns with correct String sizes and nullable=True |
| `src/services/ml_token_manager.py` | Per-dealer token management with _ml_keys helper | VERIFIED | `_ml_keys(did)` defined; all helper functions accept `did`; no global REDIS_TOKEN_KEY constant; no settings mutation |
| `src/adapters/mercadolibre.py` | Updated _ensure_token with dealer context params | VERIFIED | Line 29: `async def _ensure_token(self, dealership_id: int = 1, dealer=None)`; passes both params to `get_valid_token()` |
| `src/api/routes/webhook_cloud.py` | POST webhook with default dealership fallback | VERIFIED | Lines 92-112: Dealership imported; two-stage fallback; logger.warning on double-miss; HTTP 200 always returned |
| `src/api/routes/admin_settings.py` | Save integrations endpoint + test-connection endpoint | VERIFIED | `POST /integrations` (integrations_save) at line 98; `POST /integrations/test-connection` (test_connection) at line 135; both auth-gated |
| `src/templates/admin/integrations.html` | Redesigned integrations page with Spanish forms | VERIFIED | Full redesign confirmed; no .env/docker compose references; all credential fields present; token fields use `type="password"` with `value=""`; WA checklist in `<details>`; ML cars table preserved |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `integrations.html` | `POST /admin/ui/integrations` | `<form action="/admin/ui/integrations">` | WIRED | Line 9 of template: `<form method="post" action="/admin/ui/integrations">` |
| `integrations.html` | `POST /admin/ui/integrations/test-connection` | `fetch()` in inline JS | WIRED | Line 161: `fetch('/admin/ui/integrations/test-connection', ...)` |
| `admin_settings.py` integrations_page | Dealership DB row | `select(Dealership).where(Dealership.id == did)` | WIRED | Lines 68-70; passes `dealer`, `wa_configured`, `ml_configured`, `saved` to template context |
| `admin_settings.py` test_connection | `graph.facebook.com/v18.0/{phone_id}` | httpx.AsyncClient GET | WIRED | Lines 162-165: live API call with Authorization header |
| `admin_settings.py` test_connection | `api.mercadolibre.com/users/me` | httpx.AsyncClient GET | WIRED | Lines 180-184: live API call with Authorization header |
| `mercadolibre.py` _ensure_token | `ml_token_manager.get_valid_token` | `get_valid_token(dealership_id=dealership_id, dealer=dealer)` | WIRED | Lines 31-32 of mercadolibre.py |
| `ml_token_manager._do_refresh` | DB credentials via dealer object | `dealer.ml_refresh_token / ml_app_id / ml_client_secret` | WIRED | Lines 97-99 of ml_token_manager.py: DB-first credential reads |
| `webhook_cloud.py` | Default dealership | `select(Dealership).where(Dealership.id == default_id)` | WIRED | Lines 97-101; `settings.default_dealership_id` confirmed present in `src/config.py` line 47 |
| `008_client_integration_columns.py` | `007_billing_subscription_columns.py` | `down_revision = "007"` | WIRED | Line 12 of migration file |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `integrations.html` — badge | `wa_configured`, `ml_configured` | `admin_settings.py` integrations_page() — reads `dealer.whatsapp_access_token`, `dealer.ml_access_token` from DB | Yes — DB query, not hardcoded | FLOWING |
| `integrations.html` — field values | `dealer.whatsapp_phone_number_id`, `dealer.ml_user_id`, `dealer.ml_app_id` | DB row passed as `dealer` from integrations_page() | Yes | FLOWING |
| `integrations.html` — token placeholders | conditional on `dealer.whatsapp_verify_token`, `dealer.whatsapp_webhook_secret`, etc. | DB row | Yes | FLOWING |
| `test_connection` response | `ok`, `detail` | Live API call (WA or ML) — response data parsed from actual HTTP response | Yes — real API response, no static return | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED for API/DB-dependent behaviors — app requires running PostgreSQL, Redis, and external API connectivity. Module-level checks only.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| migration 008 syntax valid | ast.parse check (via read) | File is syntactically correct Python with proper imports and functions | PASS |
| ml_token_manager.py has no settings mutation | grep "settings.ml_access_token =" in ml_token_manager.py | No match — mutation removed | PASS |
| webhook_cloud.py always returns 200 | grep "return {.status.: .ok.}" in webhook_cloud.py | Three return paths all return {"status": "ok"} | PASS |
| token fields never render actual values | grep `value=""` in integrations.html for password fields | Lines 30, 41, 86, 91, 103 all have `value=""` for token inputs | PASS |
| whatsapp_access_token NOT in migration 008 | grep whatsapp_access_token in 008 migration | No match — correctly excluded (already in 006) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INT-01 (ROADMAP def: credentials in dealerships table) | 10-01-PLAN | Migration 008 + Dealership model 5 new columns | SATISFIED | `alembic/versions/008_client_integration_columns.py` exists with 5 columns; `src/db/models.py` lines 109-113 |
| INT-02 (ROADMAP def: admin form to save WA + ML credentials) | 10-04-PLAN | `POST /admin/ui/integrations` save endpoint + form redesign | SATISFIED | `admin_settings.py` integrations_save() + `integrations.html` with 9 form fields |
| INT-03 (ROADMAP def: Verificar conexion button with inline result) | 10-04-PLAN | `POST /admin/ui/integrations/test-connection` + JS fetch | SATISFIED | test_connection() endpoint + testConnection() JS in integrations.html |
| INT-04 (ROADMAP def: WhatsApp webhook DB-first routing with fallback) | 10-03-PLAN | webhook_cloud.py default dealership fallback | SATISFIED | `webhook_cloud.py` lines 92-112 — two-stage fallback implemented |
| INT-05 (ROADMAP def: ML token manager per-dealer Redis keys) | 10-02-PLAN | `ml_token_manager.py` per-dealer key namespacing | SATISFIED | `_ml_keys(did)` helper; all keys as `ml:{did}:*`; settings mutation removed |

**Note on requirement ID namespace:** REQUIREMENTS.md body section only defines INT-01 (MercadoLibre messaging) and INT-02 (CRM integration) in its v2 Integrations list — these are different features from the INT-01 through INT-05 used in the ROADMAP for Phase 10. The ROADMAP and RESEARCH.md effectively redefine INT-01 through INT-05 as phase-specific success criteria for Phase 10. The traceability table in REQUIREMENTS.md only tracks "INT-01 (Phase 10)" as Complete. INT-02 through INT-05 (Phase 10 edition) are not in the traceability table. This is a documentation inconsistency in REQUIREMENTS.md but does not affect the implementation — all 5 behaviors are fully implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Checks performed:
- No TODO/FIXME/PLACEHOLDER comments in modified files
- No empty return `{}` or `[]` in any route (all routes return real data or redirect)
- Token fields in integrations.html use `value=""` — intentional security design, not a stub
- No `settings.ml_access_token =` mutation in ml_token_manager.py
- No `whatsapp_access_token` in migration 008 (correctly excluded)
- No bare `return null` or placeholder components in template

### Human Verification Required

#### 1. Credential Save Flow (End-to-End)

**Test:** Log into admin UI at `/admin/ui/integrations`. Enter a value in the "Token de acceso" WhatsApp field and click "Guardar credenciales".
**Expected:** Redirect to `/admin/ui/integrations?saved=1` with green "Credenciales guardadas." alert. The "Token de acceso" field placeholder should change to "(token guardado — dejar en blanco para no cambiar)" confirming the token was persisted to the DB.
**Why human:** Requires running FastAPI app + PostgreSQL — can only be verified at runtime.

#### 2. Verificar Conexion — WhatsApp (Live API)

**Test:** With a valid WhatsApp Cloud API token and phone_number_id stored in the DB, click "Verificar conexion" in the WhatsApp section.
**Expected:** The inline span next to the button updates to "checkmark Conectado: [phone display name]" without page reload.
**Why human:** Requires live Meta Graph API call with real credentials; network call cannot be made statically.

#### 3. Verificar Conexion — MercadoLibre (Live API)

**Test:** With a valid ML access token stored in the DB, click "Verificar conexion" in the MercadoLibre section.
**Expected:** The inline span shows "checkmark Conectado como: [ML nickname]" without page reload.
**Why human:** Requires live MercadoLibre API call.

#### 4. Webhook Fallback (Default Dealership)

**Test:** Send a WhatsApp POST webhook payload with a `phone_number_id` not stored in any Dealership row.
**Expected:** Message is processed using dealership id=1 (default); app logs `phone_number_id=X not in DB, using default dealership=1`.
**Why human:** Requires running app, Postgres with data, and a valid incoming webhook POST.

### Gaps Summary

No gaps found. All 5 phase success criteria are fully implemented and wired.

**Requirement ID documentation note:** REQUIREMENTS.md's traceability table only records INT-01 (Phase 10) as Complete — INT-02 through INT-05 (Phase 10) are not tracked there. The ROADMAP correctly defines all 5 as Phase 10 requirements. Recommend updating REQUIREMENTS.md traceability table to add INT-02 through INT-05 (Phase 10) rows. This is a documentation gap, not an implementation gap.

---

_Verified: 2026-03-28T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
