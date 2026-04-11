# Phase 12: AI Agent (LLM Integration) - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire `llm_service.py` fully into `conversation_engine.py`. When `llm_enabled=True`, `generate_response()` takes over the response — the LLM decides what to say, calls tools (search_inventory, create_lead, handoff_to_manager), and returns a natural Spanish response. The deterministic state machine remains as a silent fallback when LLM is unavailable or errors.

Add per-dealer LLM credentials (api_key, model) to Dealership table and Admin Settings UI.

This phase does NOT include: analytics, onboarding wizard, test deployment, or changing the conversation flow logic itself.

</domain>

<decisions>
## Implementation Decisions

### LLM Provider
- **D-01:** OpenAI is the provider. Use `AsyncOpenAI` (already in `llm_service.py`). Default model: `gpt-4o-mini`. No Anthropic SDK needed — OpenAI only.

### Integration Mode
- **D-02:** Full LLM mode. When `llm_enabled=True`, `generate_response()` in `llm_service.py` handles the entire response — it calls tools for inventory search, lead creation, and handoff. The existing `rephrase()` path is superseded by full mode (keep it for backward compat but it is no longer the primary LLM path).
- **D-03:** Silent fallback. On any LLM exception (timeout, API error, empty response), the conversation engine catches the error silently and returns the deterministic rule-based response instead. Client never sees an error. No "no puedo procesar" message — the bot just responds as if LLM were not enabled.

### Per-Dealer LLM Config
- **D-04:** Each dealership can configure their own `llm_api_key` (encrypted) and `llm_model` (string, e.g. "gpt-4o-mini") in Admin Settings. These are stored as new nullable columns on the `Dealership` table.
- **D-05:** Key resolution priority: dealer's own `llm_api_key` (from DB) → global `settings.openai_api_key` (from .env) → LLM disabled. If neither is set, engine falls back to deterministic silently.
- **D-06:** `llm_enabled` per-dealer: a boolean column on `Dealership`. Overrides global `settings.llm_enabled`. If dealer column is NULL, fall back to global setting.

### Conversation History for LLM
- **D-07:** Read the last 10 messages from the `Message` table for the current conversation (already queried in engine context). Pass as `[{"direction": "in"/"out", "text": "..."}]` list to `generate_response()`. This is already the expected format in `llm_service.py`.

### Admin UI
- **D-08:** Add three fields to the existing Admin Settings page (`/admin/ui/settings`): "OpenAI API Key" (password input), "Modelo" (text input, placeholder "gpt-4o-mini"), "Activar IA" (checkbox). Save via existing settings_save route.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing LLM Service
- `src/services/llm_service.py` — Full implementation: `LLMService.generate_response()`, `LLMService.rephrase()`, `ToolsExecutor`, `make_tools_definitions()`. Already written — this phase wires it in, does not rewrite it.

### Conversation Engine Integration Point
- `src/services/conversation_engine.py` lines ~430-445 — Current LLM hook (rephrase-only). Phase 12 replaces this with `generate_response()` call when `llm_enabled`.

### Config
- `src/config.py` — `openai_api_key: str = ""`, `openai_model: str = "gpt-4o-mini"`, `llm_enabled: bool = False`. These are global fallbacks; per-dealer values take priority (D-05, D-06).

### Dealership Model
- `src/db/models.py` — `Dealership` class. Last migration: `009`. New migration `010` adds: `llm_api_key` (EncryptedStr, nullable), `llm_model` (String(64), nullable), `llm_enabled` (Boolean, nullable).

### Admin Settings UI
- `src/api/routes/admin_settings.py` — `settings_page` (GET) and `settings_save` (POST). Add new fields here.
- `src/templates/admin/settings.html` — Add three new form inputs in the existing form.

### Prior Phase Decisions
- Phase 1 D-01: Lazy import pattern for LLM — `from src.services.llm_service import LLMService` inside the `if llm_enabled` block.
- Phase 1 D-02: LLM opt-in via `llm_enabled`, deterministic always fallback — EXTENDED by D-03 (silent fallback).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LLMService.generate_response(session, dealership_id, user_message, conversation_history, state, user_phone, tools_executor)` — already written, handles tool call loop (max 5 iterations), returns `(response_text, updated_state)`.
- `ToolsExecutor` — already written, handles `search_inventory`, `create_lead`, `handoff_to_manager` tool calls. Accepts `on_create_lead` and `on_handoff` callbacks.
- `conversation_engine.py` already has lead/handoff callbacks wired for the deterministic path — same callbacks can be passed to `ToolsExecutor`.

### Established Patterns
- `SyncSession` for Celery, `AsyncSession` for FastAPI routes — `generate_response()` already uses `AsyncSession`.
- Lazy imports for optional LLM deps (Phase 1 D-01).
- `EncryptedStr` for sensitive columns (Phase 10 pattern — used for `ml_access_token`, `whatsapp_access_token`).

### Integration Points
- `conversation_engine.py` `process_message()` → around line 430, after deterministic result is computed, check `llm_enabled` → call `generate_response()` → silent fallback on exception.
- `admin_settings.py` `settings_save()` → read `llm_api_key`, `llm_model`, `llm_enabled` from form data → save to dealer row.

</code_context>

<specifics>
## Specific Ideas

- Per-dealer key resolution (D-05): `effective_key = dealer.llm_api_key or settings.openai_api_key`. If empty → skip LLM silently.
- Silent fallback (D-03): wrap entire `generate_response()` call in `try/except Exception` — on any error, log warning and return deterministic result unchanged.
- The `llm_enabled` per-dealer override (D-06): `effective_llm = dealer.llm_enabled if dealer.llm_enabled is not None else settings.llm_enabled`.

</specifics>

<deferred>
## Deferred Ideas

- Switching to Anthropic Claude as provider — mentioned in ROADMAP but OpenAI decided for Phase 12. Could be a future option if multi-provider support is needed.
- Streaming responses (SSE) — would make chat feel faster but adds complexity. Defer.
- Fine-tuned model for Argentine auto dealerships — interesting future direction, out of scope.

</deferred>

---

*Phase: 12-ai-agent-llm-integration*
*Context gathered: 2026-03-28*
