# Phase 10: Client Integration Setup - Research

**Researched:** 2026-03-28
**Domain:** FastAPI admin routes, SQLAlchemy migrations, Redis per-tenant key namespacing, Jinja2 forms, WhatsApp Graph API, MercadoLibre OAuth API
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Storage: Dealership table (migration 008)**
Add missing credential columns to `dealerships` table:
- `whatsapp_webhook_secret` String(128)
- `ml_access_token` String(512)
- `ml_refresh_token` String(512)
- `ml_app_id` String(64)
- `ml_client_secret` String(128)

Existing columns already present (no migration needed):
- `whatsapp_access_token`, `whatsapp_phone_number_id`, `whatsapp_verify_token`, `ml_user_id`

Adapters read credentials from the `Dealership` row (DB-first), falling back to `settings` only if the DB field is empty. Preserves backward compatibility for the dev .env setup.

**ML Token Manager: Per-Dealer**
Redis keys namespaced by `dealership_id`:
- `ml:{did}:access_token`
- `ml:{did}:refresh_token`
- `ml:{did}:token_expires_at`
- `ml:{did}:refresh_lock`

`get_valid_token(did, dealer)` signature: takes dealership_id + dealer object (for fallback to settings when did=default).

**Test Connection: Live API Validation**
After saving credentials, user clicks "Verificar conexion":
- WhatsApp: GET `https://graph.facebook.com/v18.0/{phone_number_id}` with the stored token. Success -> phone name displayed. Failure -> actionable error message.
- MercadoLibre: GET `https://api.mercadolibre.com/users/me` with the stored access token. Success -> ML username displayed. Failure -> suggest token refresh.

Result displayed inline on the integrations page (no page reload — AJAX or redirect with flash).

**WhatsApp Dev-to-Live Instructions**
Include a "Checklist de activacion WhatsApp" section on the integrations page (shown when WA credentials are saved but connection test fails or phone is not yet active). Written in plain Spanish.

**Integrations Page Redesign**
Replace instructions showing `.env` snippets and `docker compose restart` with:
- Form fields for WhatsApp credentials (labeled in Spanish)
- Form fields for ML credentials (labeled in Spanish)
- "Guardar y verificar" button
- Connection status badges (Conectado / No configurado)
- WhatsApp activation checklist (collapsible, shown when relevant)
- ML linked cars section preserved as-is

**Webhook Routing Update**
`webhook_cloud.py` must route by `whatsapp_phone_number_id` stored in DB, not only from `settings`. Query: `SELECT id FROM dealerships WHERE whatsapp_phone_number_id = :phone_number_id`. Falls back to `settings.default_dealership_id` if not found (backward compat).

**Implementation Order (for planner)**
1. Migration 008: add missing columns
2. Update ml_token_manager.py: per-dealer key namespacing
3. Update MercadoLibreAdapter._ensure_token(): pass dealer_id + dealer object
4. Redesign integrations.html: forms instead of instructions
5. Update admin_settings.py integrations routes: save + test endpoints
6. Update webhook_cloud.py: DB-first phone_number_id lookup
7. Include WA activation checklist in integrations page

### Claude's Discretion

Not explicitly listed in CONTEXT.md for this phase. Based on constraints, discretion areas are:
- Whether test-connection endpoint uses JSON response (AJAX) or redirect with flash
- Exact Spanish label wording for form fields
- Whether WA checklist is always visible or toggled by JS

### Deferred Ideas (OUT OF SCOPE)

- Multi-dealer ML accounts (different ML seller IDs per dealer)
- WhatsApp template management UI
- OAuth callback flow for ML (the form accepts the refresh_token directly; OAuth dance is a future improvement)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INT-01 | Dealership credentials stored in dealerships table, not only .env | Migration 008 adds 5 missing columns; existing columns confirmed in models.py |
| INT-02 | Admin integrations page has a form to enter and save WA and ML credentials | admin_settings.py has GET /integrations route; POST save endpoint needs adding; template needs full redesign |
| INT-03 | "Verificar conexion" button makes a live API call and shows result inline | New POST /integrations/test-connection endpoint; WA: GET graph.facebook.com/v18.0/{phone_id}; ML: GET api.mercadolibre.com/users/me |
| INT-04 | WhatsApp webhooks route by phone_number_id looked up from DB | webhook_cloud.py already partially does DB-first lookup via get_dealership_by_wa(); the gap is the POST handler currently returns 200 silently when no dealership found instead of falling back to settings.default_dealership_id |
| INT-05 | ML token manager uses per-dealership Redis keys | ml_token_manager.py uses global keys (ml:access_token); needs per-dealer namespacing to ml:{did}:access_token etc. |
</phase_requirements>

---

## Summary

Phase 10 wires the admin UI to the database for credential management, replacing the current read-only display (which shows .env values) with editable forms backed by the `dealerships` table. The work spans three layers: a database migration adding five columns, backend service refactoring (ml_token_manager per-dealer namespacing, adapter fallback logic), and a Jinja2 template redesign.

The codebase is well-prepared. The `WhatsAppCloudAdapter` already accepts constructor-injected credentials (phone_number_id, token), so the webhook routing pattern already works — it just needs the fallback path filled in. The `MercadoLibreAdapter._ensure_token()` currently calls the global `get_valid_token()` with no arguments; the signature change is the main integration point.

The most structural change is `ml_token_manager.py`: all four Redis key constants and all six internal functions must be updated to accept and propagate a `dealership_id`. The internal helpers `_read_from_redis`, `_refresh_with_lock`, `_do_refresh` all reference hardcoded key names and must be parameterized.

**Primary recommendation:** Follow the implementation order in CONTEXT.md exactly — migration first, then token manager, then adapters, then UI, then webhook routing. Each step depends on the previous.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy (async) | Already in project | ORM for model changes and DB queries | Project standard |
| Alembic | Already in project | Database migrations | Project standard, chain 001-007 established |
| FastAPI | Already in project | Route handlers for save and test-connection endpoints | Project standard |
| Jinja2 | Already in project | Template redesign for integrations.html | Project standard |
| httpx | Already in project | Async HTTP calls for test-connection validation | Already used in all adapters |
| redis (aioredis-compatible) | Already in project | Per-dealer token storage | Already used in ml_token_manager.py and rate_limit.py |

### No New Dependencies

All required capabilities exist in the project. Do not add packages.

---

## Architecture Patterns

### Recommended Project Structure

No new directories. All changes are modifications to existing files:

```
src/
├── db/models.py                          # Dealership model — 5 new columns (no code change needed, migration only)
├── services/ml_token_manager.py          # Refactor: all functions gain dealership_id param
├── adapters/mercadolibre.py              # _ensure_token() passes dealer_id + dealer object
├── api/routes/admin_settings.py          # Add POST /integrations and POST /integrations/test-connection
├── api/routes/webhook_cloud.py           # Review fallback path (already mostly correct)
└── templates/admin/integrations.html     # Full redesign with Spanish forms
alembic/versions/
└── 008_client_integration_columns.py     # New migration (down_revision="007")
```

### Pattern 1: DB-First with Settings Fallback

All credential reads follow this pattern throughout the codebase (established in Phase 06):

```python
# DB-first, settings fallback
wa_token = dealer.whatsapp_access_token or settings.whatsapp_cloud_token
```

For the new columns, the same pattern applies:
```python
ml_access = dealer.ml_access_token or settings.ml_access_token
ml_refresh = dealer.ml_refresh_token or settings.ml_refresh_token
ml_app_id = dealer.ml_app_id or settings.ml_app_id
ml_secret = dealer.ml_client_secret or settings.ml_client_secret
```

This is the backward-compatibility contract. Dev environments that have .env set but no DB columns filled continue working.

### Pattern 2: Per-Dealer Redis Key Namespacing

The existing token manager uses module-level string constants. After the refactor, keys must be computed dynamically:

```python
# Before (global):
REDIS_TOKEN_KEY = "ml:access_token"

# After (per-dealer):
def _ml_keys(did: int) -> tuple[str, str, str, str]:
    return (
        f"ml:{did}:access_token",
        f"ml:{did}:refresh_token",
        f"ml:{did}:token_expires_at",
        f"ml:{did}:refresh_lock",
    )
```

The public function signature changes from `get_valid_token() -> str` to `get_valid_token(dealership_id: int, dealer) -> str`.

All internal helpers must thread `dealership_id` through: `_read_from_redis(redis, did)`, `_refresh_with_lock(redis, did, dealer)`, `_do_refresh(redis, did, dealer)`.

The `_do_refresh` function currently reads credentials from `settings` directly. After refactoring it must read from `dealer` object first:
```python
refresh_token = dealer.ml_refresh_token or settings.ml_refresh_token
app_id = dealer.ml_app_id or settings.ml_app_id
client_secret = dealer.ml_client_secret or settings.ml_client_secret
```

### Pattern 3: Test-Connection Endpoint

The integrations page save flow has two options per CONTEXT.md decision (AJAX or redirect with flash). Given the project uses Jinja2 + standard HTML forms (no JS framework), the simplest path is redirect-with-flash already used in settings_save:

```python
return RedirectResponse(url="/admin/ui/integrations?saved=1", status_code=302)
```

For inline test-connection result without page reload, a lightweight approach is a separate POST endpoint that returns JSON, and minimal inline JS (fetch API) to display the result — consistent with the project's "HTMX + Jinja2, no SPA" constraint from REQUIREMENTS.md.

```python
@router.post("/integrations/test-connection")
async def test_connection(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    # ... reads dealer from DB, makes live API call, returns JSON
    return {"service": "whatsapp", "ok": True, "detail": "Phone: +5491155550000"}
```

The template uses a minimal fetch() call:
```html
<button type="button" onclick="testConnection('whatsapp')">Verificar conexion</button>
<span id="wa-test-result"></span>
<script>
async function testConnection(service) {
    const r = await fetch('/admin/ui/integrations/test-connection', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({service})
    });
    const data = await r.json();
    document.getElementById(service + '-test-result').textContent =
        data.ok ? 'Conectado: ' + data.detail : 'Error: ' + data.detail;
}
</script>
```

### Pattern 4: Alembic Migration Structure

The migration chain is: `001 -> 002 -> 003 -> 004 -> 006 -> 007`. Migration 005 does not exist (gap is intentional per STATE.md). Migration 008 must set `down_revision = "007"`.

```python
revision = "008"
down_revision = "007"

def upgrade() -> None:
    op.add_column("dealerships", sa.Column("whatsapp_webhook_secret", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("ml_access_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_refresh_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_app_id", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("ml_client_secret", sa.String(128), nullable=True))
```

Note: `whatsapp_access_token` and `whatsapp_phone_number_id` already exist from migration 006. `ml_user_id` already exists from an earlier migration. Do NOT add these again.

### Pattern 5: Integrations Page Form Structure

The existing settings.html pattern: single form POSTing to the route, `saved=1` query param for flash message. The integrations page must add a second separate form (or combined form with different action buttons) for credential saving. The recommended split:

- **Form 1** — WhatsApp credentials: `POST /admin/ui/integrations/whatsapp`
  - Fields: `whatsapp_phone_number_id`, `whatsapp_access_token`, `whatsapp_verify_token`, `whatsapp_webhook_secret`
- **Form 2** — ML credentials: `POST /admin/ui/integrations/mercadolibre`
  - Fields: `ml_access_token`, `ml_refresh_token`, `ml_app_id`, `ml_client_secret`, `ml_user_id`

Alternatively, a single combined form `POST /admin/ui/integrations` is simpler and consistent with the existing settings pattern.

Spanish labels to use:
- Phone Number ID: "ID de numero de telefono"
- Access Token: "Token de acceso"
- Verify Token: "Token de verificacion"
- Webhook Secret: "Secreto del webhook"
- App ID: "ID de aplicacion ML"
- Client Secret: "Secreto de cliente ML"
- User ID: "ID de usuario ML"
- Refresh Token: "Token de refresco ML"

### Anti-Patterns to Avoid

- **Writing global `settings.ml_access_token =` in `_do_refresh`**: The current code mutates the module-level `settings` object as a local cache. After the per-dealer refactor, this mutation must be removed or scoped — mutating a shared singleton with dealer-specific data would corrupt the fallback for other dealers.
- **Calling `get_valid_token()` with no args from adapters**: After the signature change, any caller that doesn't pass `dealership_id` will break. The `MercadoLibreAdapter._ensure_token()` is the only caller — update it at the same time as the token manager.
- **Adding columns that already exist**: `whatsapp_access_token` was added in migration 006. Running `op.add_column` for it again will fail. Verify each column against the current model before writing migration 008.
- **Using `settings.whatsapp_webhook_secret` for signature verification**: The existing webhook_cloud.py POST handler checks `settings.whatsapp_webhook_secret` for HMAC signature verification. After migration 008 adds per-dealer `whatsapp_webhook_secret`, the handler should prefer `dealer.whatsapp_webhook_secret or settings.whatsapp_webhook_secret`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Distributed Redis lock for token refresh | Custom lock protocol | Existing `SET NX PX` pattern already in `_refresh_with_lock()` | Already handles multi-worker race condition correctly |
| HTTP client for test-connection | Requests or custom wrapper | `httpx.AsyncClient` already used in all adapters | Consistent timeout/error handling |
| Form CSRF protection | Custom token | FastAPI's `Request` + `auth_check` session already validates dealer identity | CSRF is mitigated by the session requirement |
| Token expiry tracking | Custom datetime math | Existing `_needs_refresh()` + `REFRESH_BUFFER_SECONDS` logic | Already handles timezone-aware comparison |

---

## Current State Inventory (What Exists vs. What Changes)

### Confirmed Existing Columns in `dealerships` (from models.py + migrations)

| Column | Added In | Notes |
|--------|----------|-------|
| `whatsapp_phone_number_id` | Initial schema | Already exists |
| `whatsapp_verify_token` | Initial schema | Already exists |
| `ml_user_id` | Initial schema | Already exists |
| `whatsapp_access_token` | Migration 006 | Already exists |
| `admin_username` | Migration 006 | Already exists |
| `admin_password_hash` | Migration 006 | Already exists |

### Columns Missing (Migration 008 Must Add)

| Column | Type | Notes |
|--------|------|-------|
| `whatsapp_webhook_secret` | String(128) | For per-dealer HMAC signature verification |
| `ml_access_token` | String(512) | Per-dealer ML OAuth access token |
| `ml_refresh_token` | String(512) | Per-dealer ML OAuth refresh token |
| `ml_app_id` | String(64) | Per-dealer ML app ID for token refresh |
| `ml_client_secret` | String(128) | Per-dealer ML app secret |

### Current Webhook Routing (webhook_cloud.py)

The POST handler at line 91-95 already does DB-first lookup via `get_dealership_by_wa()`. When dealer is None, it currently returns `{"status": "ok"}` silently. The CONTEXT.md decision says to "fall back to `settings.default_dealership_id` if not found (backward compat)". This is actually a change to the existing behavior (currently it drops the message; the new behavior looks up the default dealer).

However, reviewing Phase 06-02 decision in STATE.md: "Silent 200 on unknown phone_number_id (Meta must never receive 4xx from webhook)". The fallback to `settings.default_dealership_id` only makes sense for single-tenant deployments where the phone_number_id isn't in DB yet. Implement: if dealer not found by phone_number_id, query `SELECT * FROM dealerships WHERE id = settings.default_dealership_id`.

### Current admin_settings.py Integrations Route

The GET `/admin/ui/integrations` route (line 61-85) reads `wa_configured` and `ml_configured` from `settings` — not from the dealer DB row. After this phase, it must read from the dealer object (DB-first). The existing template context must be extended with the dealer's credential values (masked) to pre-populate form fields.

---

## Common Pitfalls

### Pitfall 1: Masking Tokens in Form Pre-Population

**What goes wrong:** Rendering actual token values into HTML `<input value="...">` fields exposes credentials in page source and browser history.

**Why it happens:** Copying the settings.html pattern of pre-populating form fields with current values.

**How to avoid:** Pre-populate with a placeholder only:
- If a token is set: `<input value="" placeholder="(token guardado — dejar en blanco para no cambiar)">`
- If not set: `<input value="" placeholder="Pegar token aqui">`
- On POST save: if the submitted field is blank, skip the update for that field (keep existing value)

**Warning signs:** Seeing `Bearer ey...` tokens in HTML source.

### Pitfall 2: `_do_refresh` Mutating `settings` Singleton After Per-Dealer Refactor

**What goes wrong:** The current `_do_refresh` assigns `settings.ml_access_token = new_access` and `settings.ml_refresh_token = new_refresh`. With per-dealer tokens, this writes dealer A's token into the global singleton, then dealer B's fallback reads it.

**Why it happens:** Original single-tenant design cached the refreshed token in-process for the current worker.

**How to avoid:** Remove the `settings.ml_*` mutation lines from `_do_refresh`. The per-dealer Redis storage is sufficient for cross-worker sharing. In-process state is not safe with multiple dealers.

### Pitfall 3: Adding Already-Existing Columns in Migration

**What goes wrong:** `alembic upgrade` throws `DuplicateColumn` or similar error.

**Why it happens:** `whatsapp_access_token` was added in migration 006 but is listed in CONTEXT.md under "Existing columns (already present, no migration needed)". The five columns listed for migration 008 are only those not yet in the schema.

**How to avoid:** Cross-check CONTEXT.md "Existing columns" list against migration 006 content. Confirmed: only the 5 listed above need to be added.

### Pitfall 4: `get_valid_token()` Called Without `dealership_id` From Other Code Paths

**What goes wrong:** After the signature change, if any other code path calls `get_valid_token()` without arguments (e.g., a Celery task or outbound service), it breaks.

**Why it happens:** Only `MercadoLibreAdapter._ensure_token()` was identified as the caller, but outbound flow code from Phase 04 may also call it.

**How to avoid:** Search the entire codebase for `get_valid_token` calls before changing the signature. Provide a default parameter fallback: `async def get_valid_token(dealership_id: int = 1, dealer=None)` to avoid breaking callers that haven't been updated yet.

### Pitfall 5: Test-Connection Endpoint Returns Credentials in Error Messages

**What goes wrong:** An error response like `"detail": "403 Forbidden: {token: 'Bearer EAA...'}"` leaks credentials.

**Why it happens:** httpx error messages can include response body which Meta sometimes echoes back partial credential info.

**How to avoid:** Catch the httpx response, extract only the status code and a sanitized error field from the JSON, never include raw response text in the result returned to the browser.

---

## Code Examples

### Migration 008 — Verified Column List

```python
# alembic/versions/008_client_integration_columns.py
revision = "008"
down_revision = "007"

def upgrade() -> None:
    op.add_column("dealerships", sa.Column("whatsapp_webhook_secret", sa.String(128), nullable=True))
    op.add_column("dealerships", sa.Column("ml_access_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_refresh_token", sa.String(512), nullable=True))
    op.add_column("dealerships", sa.Column("ml_app_id", sa.String(64), nullable=True))
    op.add_column("dealerships", sa.Column("ml_client_secret", sa.String(128), nullable=True))

def downgrade() -> None:
    op.drop_column("dealerships", "ml_client_secret")
    op.drop_column("dealerships", "ml_app_id")
    op.drop_column("dealerships", "ml_refresh_token")
    op.drop_column("dealerships", "ml_access_token")
    op.drop_column("dealerships", "whatsapp_webhook_secret")
```

### ML Token Manager — Per-Dealer Key Helper

```python
# Replaces module-level constants
def _ml_keys(did: int) -> tuple[str, str, str, str]:
    """Return (token_key, refresh_key, expires_key, lock_key) for a dealer."""
    return (
        f"ml:{did}:access_token",
        f"ml:{did}:refresh_token",
        f"ml:{did}:token_expires_at",
        f"ml:{did}:refresh_lock",
    )

async def get_valid_token(dealership_id: int = 1, dealer=None) -> str:
    token_key, refresh_key, expires_key, lock_key = _ml_keys(dealership_id)
    redis = await _get_redis()
    # ... rest of logic using these keys, not hardcoded constants
```

### MercadoLibreAdapter — Updated _ensure_token

```python
async def _ensure_token(self, dealership_id: int = 1, dealer=None) -> None:
    from src.services.ml_token_manager import get_valid_token
    self.token = await get_valid_token(dealership_id=dealership_id, dealer=dealer)
    self.is_configured = bool(self.token and self.user_id)
```

### Admin Route — Save Integrations (Blank = Keep Existing)

```python
@router.post("/integrations")
async def integrations_save(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
    form = await request.form()
    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()
    if dealer:
        # Only update if field was submitted non-empty
        if form.get("whatsapp_phone_number_id"):
            dealer.whatsapp_phone_number_id = form["whatsapp_phone_number_id"].strip()
        if form.get("whatsapp_access_token"):
            dealer.whatsapp_access_token = form["whatsapp_access_token"].strip()
        if form.get("whatsapp_verify_token"):
            dealer.whatsapp_verify_token = form["whatsapp_verify_token"].strip()
        if form.get("whatsapp_webhook_secret"):
            dealer.whatsapp_webhook_secret = form["whatsapp_webhook_secret"].strip()
        if form.get("ml_access_token"):
            dealer.ml_access_token = form["ml_access_token"].strip()
        # ... etc
        await db.commit()
    return RedirectResponse(url="/admin/ui/integrations?saved=1", status_code=302)
```

### Test-Connection Endpoint — Sanitized Response

```python
@router.post("/integrations/test-connection")
async def test_connection(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return {"ok": False, "detail": "No autenticado"}
    body = await request.json()
    service = body.get("service")  # "whatsapp" or "mercadolibre"

    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()
    if not dealer:
        return {"ok": False, "detail": "Concesionario no encontrado"}

    if service == "whatsapp":
        token = dealer.whatsapp_access_token or settings.whatsapp_cloud_token
        phone_id = dealer.whatsapp_phone_number_id or settings.whatsapp_phone_number_id
        if not token or not phone_id:
            return {"ok": False, "detail": "Credenciales no configuradas"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://graph.facebook.com/v18.0/{phone_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if resp.status_code == 200:
                name = data.get("display_phone_number") or data.get("verified_name") or phone_id
                return {"ok": True, "detail": f"Conectado: {name}"}
            error = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return {"ok": False, "detail": f"Error de Meta: {error}"}
        except Exception as e:
            return {"ok": False, "detail": "Error de red — verificar conexion"}

    if service == "mercadolibre":
        token = dealer.ml_access_token or settings.ml_access_token
        if not token:
            return {"ok": False, "detail": "Token ML no configurado"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.mercadolibre.com/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if resp.status_code == 200:
                nickname = data.get("nickname") or data.get("id")
                return {"ok": True, "detail": f"Conectado como: {nickname}"}
            return {"ok": False, "detail": "Token invalido — refrescar token ML"}
        except Exception:
            return {"ok": False, "detail": "Error de red — verificar conexion"}

    return {"ok": False, "detail": "Servicio desconocido"}
```

### Webhook Routing — Default Dealership Fallback

The current webhook_cloud.py POST handler (lines 89-95) already handles the DB-first case. The only change needed is the fallback path when `dealer is None`:

```python
# Current behavior (silent drop):
if dealer is None:
    logger.info("No dealership for phone_number_id=%s, ignoring", phone_number_id)
    return {"status": "ok"}

# New behavior (fallback to default):
if dealer is None:
    # Fallback: use default dealership (backward compat for single-tenant .env setup)
    default_id = settings.default_dealership_id
    stmt = select(Dealership).where(Dealership.id == default_id)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()
    if dealer is None:
        logger.warning("Default dealership id=%d not found, dropping message", default_id)
        return {"status": "ok"}
    logger.info("phone_number_id=%s not in DB, using default dealership=%d", phone_number_id, default_id)
```

---

## State of the Art

| Old Approach | Current Approach | Impact for Phase 10 |
|--------------|------------------|---------------------|
| Global `ml:access_token` Redis key | Per-dealer `ml:{did}:access_token` | Core refactor of ml_token_manager.py |
| Settings-only credential reads | DB-first + settings fallback | Already established in Phase 06; extend to ML credentials |
| .env instructions in UI | Editable form fields | Core UI deliverable |
| Silent drop on unknown phone_number_id | Fallback to default dealership | Change to existing webhook behavior |

---

## Open Questions

1. **Signature verification with per-dealer `whatsapp_webhook_secret`**
   - What we know: `webhook_cloud.py` POST handler currently checks `settings.whatsapp_webhook_secret` globally (line 63). Migration 008 adds a per-dealer `whatsapp_webhook_secret` column.
   - What's unclear: When to prefer the dealer-level secret. At signature-check time, we don't yet know which dealer the message belongs to (we haven't parsed the body yet — or have we? The body is read before parsing if `settings.whatsapp_webhook_secret` is set).
   - Recommendation: Use the global `settings.whatsapp_webhook_secret` for the signature check (it happens before dealer routing, on the raw body). The per-dealer `whatsapp_webhook_secret` column is available for future per-tenant webhook verification but is not wired into the existing HMAC check in this phase. Store it in the DB as a form field but leave the current HMAC logic unchanged.

2. **Callers of `get_valid_token()` beyond `MercadoLibreAdapter`**
   - What we know: `MercadoLibreAdapter._ensure_token()` is the confirmed caller.
   - What's unclear: Whether Celery tasks or outbound flow code (Phase 04/05) calls it directly.
   - Recommendation: Grep for `get_valid_token` across the codebase before changing the signature. Use a default parameter `dealership_id: int = 1` as a safety net.

---

## Environment Availability

Step 2.6: SKIPPED (phase is purely code/config changes to existing stack — all dependencies are already in use: PostgreSQL, Redis, httpx, SQLAlchemy, Alembic, FastAPI, Jinja2).

---

## Sources

### Primary (HIGH confidence)

- Direct codebase analysis: `src/db/models.py` — confirmed existing Dealership columns
- Direct codebase analysis: `src/services/ml_token_manager.py` — confirmed current global Redis key structure and all 6 functions
- Direct codebase analysis: `src/adapters/mercadolibre.py` — confirmed `_ensure_token()` call signature
- Direct codebase analysis: `src/adapters/whatsapp_cloud.py` — confirmed `get_dealership_by_wa()` function exists
- Direct codebase analysis: `src/api/routes/admin_settings.py` — confirmed current integrations route structure
- Direct codebase analysis: `src/api/routes/webhook_cloud.py` — confirmed current routing logic and silent-drop behavior
- Direct codebase analysis: `alembic/versions/007_billing_subscription_columns.py` — confirmed `down_revision="007"` is the correct base for 008
- Direct codebase analysis: `alembic/versions/006_multi_tenancy_dealership_columns.py` — confirmed which columns were added in 006 (prevents accidental duplicates in 008)
- Direct codebase analysis: `src/config.py` — confirmed all settings fields and their names

### Secondary (MEDIUM confidence)

- `tests/conftest.py` — SQLite test pattern confirmed; no test infrastructure changes needed for this phase
- `.planning/STATE.md` — confirmed Phase 06-02 decision "Silent 200 on unknown phone_number_id" which the webhook fallback change must be consistent with

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use, no new dependencies
- Architecture: HIGH — all patterns verified against existing code; no speculative design
- Pitfalls: HIGH — all pitfalls derived from direct code reading, not hypothetical

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable stack, no fast-moving dependencies)
