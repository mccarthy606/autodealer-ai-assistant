# Phase 14: Client Onboarding — Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a step-by-step onboarding wizard at `/admin/ui/onboarding` that guides a new dealership through: (1) WhatsApp Business configuration, (2) MercadoLibre configuration, (3) Inventory sync, (4) Test WhatsApp message to their own phone. Instructions on every step are in Spanish, detailed enough that a non-technical dealer can follow without external docs.

The wizard page is permanent (always accessible from nav) and functions as both an initial setup guide and a credentials management page for re-configuration when numbers/tokens change.

This phase does NOT include: LLM/AI setup in the wizard (remains in Settings), multi-tenant admin management, payment setup, or any new credential fields beyond those already in the Dealership model.

</domain>

<decisions>
## Implementation Decisions

### Wizard Flow
- **D-01:** Linear locked steps. Step N becomes interactive only when Step N-1 has been validated. Completed steps show a green checkmark and remain clickable (dealer can re-enter credentials and re-validate at any time). Future locked steps are visually grayed out and not clickable. There is no "Skip" option.

### Steps Composition
- **D-02:** Exactly 4 steps in order:
  1. **WhatsApp Business** — Phone Number ID + Access Token + Verify Token + Webhook Secret → "Verificar conexión" must pass
  2. **MercadoLibre** — User ID + Access Token + Refresh Token + App ID + Client Secret → "Verificar conexión" must pass
  3. **Sincronizar inventario** — Trigger ML sync → wait for completion → at least 1 item must appear before Step 4 unlocks
  4. **Mensaje de prueba** — Dealer enters their own phone number → system sends a real WhatsApp message via `WhatsAppCloudAdapter.send_text()` → dealer clicks "Confirmé que recibí el mensaje" → wizard complete

  LLM/AI config is NOT a wizard step — dealer uses Settings page for that.

### Instruction Depth
- **D-03:** Every step includes a collapsible (but expanded by default) `<details>` section with Spanish step-by-step instructions. Instructions name the exact URL, section, button, and field to find each credential. Level of detail:
  - WA step: "Ve a business.facebook.com → Configuración → WhatsApp Business → Números de teléfono → seleccioná tu número → copiá el ID que aparece en 'ID del número de teléfono'"
  - ML step: "Ve a developers.mercadolibre.com → Mis aplicaciones → creá una nueva app → copiá el App ID de la página de resumen"
  - These are REAL instructions inside the wizard — no external docs needed.

### Test Message Step
- **D-04:** Dealer types their own WhatsApp phone number (international format hint shown: `+5491122334455`). System calls `WhatsAppCloudAdapter.send_text(phone, message)` using the dealer's already-configured WA credentials. Message text (in Spanish): `"Hola, este es un mensaje de prueba de tu bot AutoDealer. ¡Todo funciona correctamente! 🚗"`. After sending, dealer clicks "Confirmé que recibí el mensaje" button to mark wizard complete. No DB column needed — completion state is derived from dealer fields.

### Step Completion Logic (derived from existing DB columns, no migration needed)
- **D-05:**
  - Step 1 done: `bool(dealer.whatsapp_access_token and dealer.whatsapp_phone_number_id)`
  - Step 2 done: `bool(dealer.ml_access_token and dealer.ml_user_id)`
  - Step 3 done: `bool(dealer.ml_last_sync_at)` (column already exists from Phase 11)
  - Step 4 done: shown as "completed" if all of steps 1-3 are done (always re-doable)
  - Each step's "done" state is computed fresh on every GET — no separate wizard_state column.

### Post-Completion Accessibility
- **D-06:** Wizard page remains in nav forever (labeled "Configuración inicial" or "Inicio"). After completion, page shows all steps with green checkmarks + a success banner. Dealer can click any completed step to re-enter credentials and re-validate (useful when WhatsApp token expires or ML app is recreated). Re-validating a step does NOT reset later steps unless they depend on the changed field.

### Page Route and Nav
- **D-07:** New page at `GET /admin/ui/onboarding` in `admin_dashboard.py` (or new `admin_onboarding.py`). Template at `src/templates/admin/onboarding.html`. Nav link added to `base.html` as "Onboarding" (active when `/onboarding` in path). Auth-gated with existing `auth_check()` pattern.

### UI Step Indicator
- **D-08:** Horizontal step indicator at the top of the page (4 numbered circles connected by lines). States: completed (green, ✓), active (blue, current number), locked (gray, number). CSS added to `admin.css`. Below the indicator: the active step card expands fully; completed steps show a collapsed summary card (credentials saved, ✓); locked steps show a dimmed card saying "Disponible al completar el paso anterior".

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Route Patterns
- `src/api/routes/admin_dashboard.py` — existing routes structure, `auth_check` usage, `TemplateResponse` pattern
- `src/api/routes/admin_settings.py` — `integrations_save` pattern: blank field = keep existing value (D-06 re-entry pattern)
- `src/api/routes/admin_common.py` — `auth_check()` signature and usage

### Existing Integrations (credentials already work here)
- `src/api/routes/admin_settings.py` — POST `/admin/ui/integrations`: saves WA and ML credentials (same logic needed in wizard)
- `src/templates/admin/integrations.html` — existing credential forms with placeholder and hint patterns to replicate

### WhatsApp Adapter (for test message step)
- `src/adapters/whatsapp_cloud.py` — `WhatsAppCloudAdapter.__init__(phone_number_id, token)` + `send_text(phone, text)` method

### DB Models (step completion derived from these)
- `src/db/models.py` — Dealership model fields: `whatsapp_phone_number_id`, `whatsapp_access_token`, `ml_access_token`, `ml_user_id`, `ml_last_sync_at` (all already exist, no migration needed)

### Base Template (nav extension)
- `src/templates/base.html` — nav link pattern: `<a href="..." class="{% if '/path' in request.url.path %}active{% endif %}">Label</a>`

### Existing UI Patterns
- `src/templates/admin/dashboard.html` — stat-card and badge CSS class pattern
- `src/static/admin.css` — existing CSS (`.card`, `.form-group`, `.btn`, `.badge`, `.alert`) to extend for step indicator

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth_check(request)` — auth gate, returns `int` (dealer ID) or `RedirectResponse`
- `WhatsAppCloudAdapter(phone_number_id, token).send_text(phone, text)` — real WA send, used in conversations
- `POST /admin/ui/integrations/test-connection` — already validates WA and ML credentials; wizard should call same logic or inline it per step
- `dealer.ml_last_sync_at` — already populated by Phase 11 sync; use as Step 3 completion signal

### Established Patterns
- Blank field = keep existing value (credentials not echoed back): `if form.get("field"): dealer.field = form["field"].strip()`
- Jinja2 active nav: `{% if '/path' in request.url.path %}active{% endif %}`
- Step validation: `bool(dealer.whatsapp_access_token and dealer.whatsapp_phone_number_id)` — compute each step's state in `onboarding_page()` GET handler and pass to template

### Integration Points
- Add `onboarding_page()` GET route in `admin_dashboard.py` (or new `admin_onboarding.py`)
- Add POST route for step saves (can be one `onboarding_save()` that accepts a `step=` param, or 4 separate endpoints)
- Add nav link in `base.html`
- Add step indicator CSS to `admin.css`

</code_context>

<specifics>
## Specific Ideas

- Step instructions format: `<details open><summary>📋 Cómo obtener este dato</summary>...<ol><li>...</li></ol></details>` — expandable by default, collapsible to save space
- Each step card has a "Guardar y verificar" button that saves + tests in one click. On success: step shows ✓ and next step activates. On failure: red alert with the error message.
- Step 3 (inventory sync) reuses the existing `POST /admin/ui/cars/sync-ml` endpoint — wizard just adds a "Sincronizar ahora" button and polls (or reload after 3s) to show result
- Step 4 phone input: placeholder `+5491122334455`, note "Ingresá tu propio número de WhatsApp para recibir el mensaje de prueba"
- Test message text in Spanish: `"Hola, este es un mensaje de prueba de tu bot AutoDealer. ¡Todo funciona correctamente! 🚗"`
- Completion banner (shown when all 4 steps done): green `.alert-success` card — "¡Felicitaciones! Tu bot está listo para recibir clientes."

</specifics>

<deferred>
## Deferred Ideas

- LLM/AI config in wizard — already on Settings page
- Automated token refresh setup instructions — out of scope
- Multi-admin user management — separate phase
- Email notifications for wizard completion — out of scope
- Video tutorial embeds — out of scope

</deferred>

---

*Phase: 14-client-onboarding*
*Context gathered: 2026-03-28*
