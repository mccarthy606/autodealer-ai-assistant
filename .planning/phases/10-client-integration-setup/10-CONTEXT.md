# Phase 10: Client Self-Service Integration Setup — Context

## Phase Goal
Dealership owner can connect WhatsApp Business and MercadoLibre through the Admin UI — no .env editing, no `docker compose restart`, no technical knowledge required.

## Decisions

### Storage: Dealership table (migration 008)
Add missing credential columns to `dealerships` table:
- `whatsapp_webhook_secret` String(128)
- `ml_access_token` String(512)
- `ml_refresh_token` String(512)
- `ml_app_id` String(64)
- `ml_client_secret` String(128)

Existing columns (already present, no migration needed):
- `whatsapp_access_token`, `whatsapp_phone_number_id`, `whatsapp_verify_token`, `ml_user_id`

Adapters read credentials from the `Dealership` row (DB-first), falling back to `settings` only if the DB field is empty. This preserves backward compatibility for the dev .env setup.

### ML Token Manager: Per-Dealer
Redis keys namespaced by `dealership_id`:
- `ml:{did}:access_token`
- `ml:{did}:refresh_token`
- `ml:{did}:token_expires_at`
- `ml:{did}:refresh_lock`

`get_valid_token(did, dealer)` signature: takes dealership_id + dealer object (for fallback to settings when did=default).

### Test Connection: Live API Validation
After saving credentials, user clicks "Verificar conexión":
- **WhatsApp**: GET `https://graph.facebook.com/v18.0/{phone_number_id}` with the stored token. Success → phone name displayed. Failure → actionable error message.
- **MercadoLibre**: GET `https://api.mercadolibre.com/users/me` with the stored access token. Success → ML username displayed. Failure → suggest token refresh.

Result displayed inline on the integrations page (no page reload — AJAX or redirect with flash).

### WhatsApp Dev→Live Instructions
Include a "Checklist de activación WhatsApp" section on the integrations page (shown when WA credentials are saved but connection test fails or phone is not yet active):
1. Abrir Meta for Developers → WhatsApp → API Setup
2. Verificar que el número esté en modo "Live" (no "Development")
3. En Development mode: agregar el número del cliente al whitelist de prueba
4. Configurar el webhook URL: `https://tu-dominio/webhooks/whatsapp_cloud`
5. Verify Token debe coincidir con el campo guardado

Written in plain Spanish, no technical jargon beyond necessary field names.

### Integrations Page Redesign
Replace instructions showing `.env` snippets and `docker compose restart` with:
- Form fields for WhatsApp credentials (labeled in Spanish)
- Form fields for ML credentials (labeled in Spanish)
- "Guardar y verificar" button
- Connection status badges (Conectado / No configurado)
- WhatsApp activation checklist (collapsible, shown when relevant)
- ML linked cars section preserved as-is

### Webhook Routing Update
`webhook_cloud.py` must route by `whatsapp_phone_number_id` stored in DB, not only from `settings`. Query: `SELECT id FROM dealerships WHERE whatsapp_phone_number_id = :phone_number_id`. Falls back to `settings.default_dealership_id` if not found (backward compat).

## Out of Scope (Deferred)
- Multi-dealer ML accounts (different ML seller IDs per dealer)
- WhatsApp template management UI
- OAuth callback flow for ML (the form accepts the refresh_token directly; OAuth dance is a future improvement)

## Implementation Order (for planner)
1. Migration 008: add missing columns
2. Update ml_token_manager.py: per-dealer key namespacing
3. Update MercadoLibreAdapter._ensure_token(): pass dealer_id + dealer object
4. Redesign integrations.html: forms instead of instructions
5. Update admin_settings.py integrations routes: save + test endpoints
6. Update webhook_cloud.py: DB-first phone_number_id lookup
7. Include WA activation checklist in integrations page
