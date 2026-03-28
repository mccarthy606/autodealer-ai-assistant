---
plan: 12-03
phase: 12
status: complete
subsystem: admin-settings
tags: [llm, settings, admin-ui, forms]
completed: 2026-03-28
tasks_completed: 3
files_modified: 2
files_created: 1
---

# Phase 12 Plan 03: LLM Settings Admin UI Summary

Per-dealer LLM configuration (API key, model, enabled toggle) wired into the admin settings page with save logic and full unit test coverage.

## What Was Done

**Task 1 — admin_settings.py (GET + POST):**
- GET `settings_page`: Added `dealer_llm_api_key_set`, `dealer_llm_model`, `dealer_llm_enabled` to template context so the form can reflect per-dealer state.
- POST `settings_save`: Added LLM field save block inside `if dealer:` — blank API key preserves the existing credential (credentials not echoed back to browser), `llm_model` defaults to None if blank, `llm_enabled` derived from HTML checkbox presence in form dict.

**Task 2 — settings.html:**
- Replaced the read-only "Bot behavior" card (env-var display only) with an editable "Inteligencia Artificial" card containing: password field for OpenAI API key (placeholder changes based on whether a key is already saved), text field for model name, checkbox for enabling/disabling LLM.

**Task 3 — tests/test_llm_settings.py:**
- 3 async unit tests covering: save with key+model+checkbox (enables LLM), save without checkbox (disables LLM), blank API key submission (preserves existing key).

## Verification Results

- `tests/test_llm_settings.py`: 3/3 passed
- Full suite: 210 passed, 0 failures

## Key Files

### Modified
- `src/api/routes/admin_settings.py` — GET context keys + POST LLM save block
- `src/templates/admin/settings.html` — Bot behavior card replaced with AI settings card

### Created
- `tests/test_llm_settings.py` — 3 unit tests for LLM settings save logic

## Decisions Made

- Blank API key on form submit preserves existing DB value (same pattern as WhatsApp/ML credential fields in integrations_save).
- `llm_enabled` checkbox absence in form body = False (standard HTML form behavior for unchecked checkboxes).
- Fallback checkbox logic: if `dealer_llm_enabled` is None (never set), falls back to global `llm_enabled` env setting so existing deployments don't change behavior.

## Deviations from Plan

None — plan executed exactly as written.
