---
# Phase 6: Multi-Tenancy - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Multiple dealerships operate on one instance with complete data isolation. Incoming requests are automatically scoped to the correct dealership. WhatsApp webhooks routed by phone_number_id, ML webhooks routed by ml_user_id, admin sessions scoped per dealership. Per-dealership WABA credentials stored in DB.

</domain>

<decisions>
## Implementation Decisions

### WABA Token Storage (MT-01, MT-02)
- **D-01:** Add `whatsapp_access_token` column (String 512, nullable) to `Dealership` table. Stored plaintext in DB for now (encryption deferred to Phase 9).
- **D-02:** `WhatsAppCloudAdapter.__init__()` accepts optional `phone_number_id: str` and `token: str` params. If provided, uses those instead of `settings`. Backward compat: falls back to `settings.whatsapp_phone_number_id` / `settings.whatsapp_cloud_token` when params absent.
- **D-03:** All call sites that know the dealership pass dealership's credentials to the adapter. Internal sends (e.g., outbound service, follow-up task) load dealership from DB and pass credentials explicitly.

### Admin Authentication (MT-02)
- **D-04:** Add `admin_username` (String 128, nullable) and `admin_password_hash` (String 255, nullable) to `Dealership` table via Alembic migration.
- **D-05:** Login flow: POST `/admin/login` receives username+password → `SELECT * FROM dealerships WHERE admin_username = ?` → bcrypt verify → on success: session stores `dealership_id`. Session key remains `admin:session:{token_hash}`, payload now includes `{"dealership_id": N}`.
- **D-06:** `auth.py` refactor: `create_session(response, dealership_id)` stores dealership_id in session value. `get_session_dealership_id(request) -> Optional[int]` reads it. `is_authenticated(request) -> bool` still works for legacy.
- **D-07:** `auth_check(request) -> int` (new helper) — verifies session AND returns `dealership_id`. Admin routes call `did = await auth_check(request)` instead of `settings.default_dealership_id`. Unauthorized → redirect to login.
- **D-08:** Global `settings.admin_password/admin_password_hash` retained as superadmin fallback (dealership_id=1). So existing deployment keeps working.

### WhatsApp Webhook Routing (MT-03)
- **D-09:** WhatsApp payload always contains `entry[0].changes[0].value.metadata.phone_number_id`. Extract it in `parse_incoming_message()` — return 4-tuple `(phone, text, wamid, phone_number_id)`.
- **D-10:** New dependency `get_dealership_by_wa(db, phone_number_id) -> Optional[Dealership]` — `SELECT * FROM dealerships WHERE whatsapp_phone_number_id = ?`. Returns None if no dealership configured for that phone_number_id.
- **D-11:** Webhook GET (verify): try to find dealership by `phone_number_id` from query params, use its `whatsapp_verify_token`. Fallback to `settings.whatsapp_verify_token` if not found (backward compat).
- **D-12:** Webhook POST: if dealership not found for phone_number_id → return 200 OK silently (ignore unknown webhooks, never 4xx — Meta retries on non-2xx).

### ML Webhook Routing (MT-03)
- **D-13:** ML webhook: extract `seller_id` from notification payload. `SELECT * FROM dealerships WHERE ml_user_id = ?`. If found → use that dealership. If not found → fallback to `settings.default_dealership_id` (keeps single-tenant setup working).
- **D-14:** `parse_incoming_question()` in `mercadolibre.py` returns the seller_id from the notification. Webhook handler uses it for dealership lookup.

### Redis Cache Isolation (MT-04)
- **D-15:** Rate limiter key changes from `rate:whatsapp:{phone}` to `rate:wa:{dealership_id}:{phone}`. The `check_rate_limit()` call in `webhook_cloud.py` passes `prefix=f"rate:wa:{dealership_id}"`.
- **D-16:** Session Redis keys remain `admin:session:{token_hash}` — no tenant prefix needed (each token is globally unique). Session VALUE stores `dealership_id`.
- **D-17:** No other Redis key changes needed for Phase 6.

### Database (MT-01)
- **D-18:** All models already have `dealership_id` FK — structural isolation already done. No new tables needed.
- **D-19:** No PostgreSQL RLS. Isolation enforced via SQLAlchemy `where(Model.dealership_id == did)` in all queries. Admin routes already do this correctly for most queries — just need `did` to come from session instead of `settings`.
- **D-20:** One Alembic migration (006): adds `whatsapp_access_token`, `admin_username`, `admin_password_hash` to `dealerships` table.

### Implementation Files
- **D-21:** `src/api/auth.py` — refactor `create_session`, `is_authenticated`, `auth_check`
- **D-22:** `src/api/routes/webhook_cloud.py` — use phone_number_id routing + dealership credentials
- **D-23:** `src/api/routes/webhook_ml.py` — use ml_user_id routing
- **D-24:** `src/api/routes/admin_*.py` — replace `settings.default_dealership_id` with `await auth_check(request)`
- **D-25:** `src/adapters/whatsapp_cloud.py` — accept optional phone_number_id/token params
- **D-26:** `src/services/outbound_service.py` — load dealership credentials, pass to adapter
- **D-27:** `src/tasks/followup_task.py` — load dealership credentials per conversation, pass to adapter
- **D-28:** `alembic/versions/006_multi_tenancy_dealership_columns.py` — migration

### Claude's Discretion
- Exact session payload serialization (JSON in Redis value vs separate keys)
- Edge case: dealership found but has no `whatsapp_access_token` (fall back to settings token)
- Whether to cache dealership-by-phone_number_id lookup in Redis for performance
- Superadmin detection logic (when using settings fallback vs dealership credentials)

</decisions>

<canonical_refs>
## Canonical References

### Existing Code
- `src/api/auth.py` — session management to refactor
- `src/api/routes/webhook_cloud.py` — WhatsApp webhook (phone_number_id routing)
- `src/api/routes/webhook_ml.py` — ML webhook (ml_user_id routing)
- `src/api/routes/admin_*.py` — all use settings.default_dealership_id
- `src/adapters/whatsapp_cloud.py` — adapter to make per-tenant
- `src/db/models.py` — Dealership model (add 3 columns)
- `src/services/outbound_service.py` — passes dealership_id, needs to pass credentials
- `src/tasks/followup_task.py` — needs per-dealership adapter calls

</canonical_refs>

<code_context>
## Existing Code Insights

### Current Single-Tenant Gaps
- `settings.default_dealership_id` hardcoded in: webhook_cloud.py, webhook_ml.py, all admin_*.py routes (17+ call sites)
- `WhatsAppCloudAdapter` uses `settings.whatsapp_phone_number_id` globally — single WABA account
- `auth.py` session has no dealership_id — purely boolean authenticated/not
- Rate limiter prefix doesn't include dealership_id

### Already Multi-Tenant Ready
- All DB models have `dealership_id` FK with indexed queries
- `Dealership.whatsapp_phone_number_id` column exists — just need lookup logic
- `Dealership.ml_user_id` column exists — just need lookup logic
- `Dealership.whatsapp_verify_token` exists — per-tenant verify token ready

</code_context>

<specifics>
## Specific Requirements

- WABA tokens: stored in Dealership table (plaintext)
- Admin auth: per-dealership username+password in Dealership table
- ML routing: by ml_user_id with fallback to default_dealership_id
- WhatsApp routing: by phone_number_id, return 200 silently if not found

</specifics>

<deferred>
## Deferred Ideas

- Encryption of WABA tokens at rest — Phase 9 (Production)
- Superadmin UI to manage all dealerships — v2
- Per-dealership subdomain routing — v2
- PostgreSQL RLS as additional isolation layer — v2
- ML multi-tenant without fallback (strict isolation) — v2

</deferred>

---

*Phase: 06-multi-tenancy*
*Context gathered: 2026-03-27*
