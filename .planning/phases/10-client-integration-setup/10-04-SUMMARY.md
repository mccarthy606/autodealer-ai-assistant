---
plan: 10-04
phase: 10-client-integration-setup
status: complete
started: 2026-03-28
completed: 2026-03-28
duration_minutes: 15
tasks_completed: 2
tasks_total: 2
commits:
  - 9238d8f
  - 4fb8e0e
key-files:
  modified:
    - src/api/routes/admin_settings.py
    - src/templates/admin/integrations.html
---

# Plan 10-04 Summary: Admin Integrations Page Redesign

## What Was Built

Added credential save and live test-connection endpoints to `admin_settings.py`, and redesigned `integrations.html` with Spanish-language forms replacing all `.env`-instruction layouts.

## Tasks

### Task 1: Backend — save + test-connection endpoints (admin_settings.py)
- Added `POST /admin/ui/integrations` — saves WhatsApp and ML credentials to the Dealership row. Blank-skip logic: fields left blank do not overwrite existing tokens.
- Added `POST /admin/ui/integrations/test-connection` — JSON endpoint that makes live API calls (WA: `GET /v18.0/{phone_id}`, ML: `GET /users/me`) and returns `{"ok": bool, "detail": str}`.
- Updated `GET /admin/ui/integrations` to read dealer credentials from DB (not just settings).

### Task 2: Frontend — integrations.html redesign
- Replaced `.env` code blocks and `docker compose restart` instructions with HTML forms.
- WhatsApp section: Phone Number ID, Access Token, Verify Token fields (token inputs are `type="password"` with `value=""` — tokens never rendered to HTML). "Guardar credenciales" submit + "Verificar conexión" AJAX button.
- MercadoLibre section: App ID, Client Secret, User ID, Refresh Token fields (same masking). Same save + verify buttons.
- WA activation checklist in `<details>` block — plain Spanish, Dev→Live transition steps.
- ML cars table and URL import form preserved.

## Self-Check: PASSED

- `admin_settings.py` contains `POST /integrations` save route: ✓
- `admin_settings.py` contains `/test-connection` endpoint returning JSON: ✓
- `integrations.html` has no `.env` or `docker compose` text: ✓
- All token inputs use `type="password"`: ✓
- Spanish labels throughout: ✓
