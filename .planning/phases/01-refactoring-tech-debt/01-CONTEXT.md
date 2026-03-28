# Phase 1: Refactoring & Tech Debt - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Clean the codebase: merge two parallel conversation engines into one, split the 32KB admin_ui.py monolith into domain modules, and fix deprecated datetime.utcnow() calls. No new features — pure structural improvement.

</domain>

<decisions>
## Implementation Decisions

### Engine Merge Strategy
- **D-01:** Use `conversation_engine.py` as the base — it has the complete state machine (NEW → BROWSING → PRESENTING → DETAILS → CLOSING → HANDOFF) and handles all 7 intents deterministically.
- **D-02:** Absorb LLM integration from `orchestrator.py` as an optional layer. When `LLM_ENABLED=true`, pass the deterministic response through LLM for phrasing improvement. When false (default), pure deterministic.
- **D-03:** Delete `orchestrator.py` and `deterministic_responder.py` after merge. All routes must use the single unified engine.
- **D-04:** Keep `llm_service.py` as a separate service — engine calls it optionally, not the other way around.

### Admin UI Split
- **D-05:** Split by domain into separate route modules:
  - `admin_dashboard.py` — home page, overview
  - `admin_inventory.py` — car CRUD, CSV import
  - `admin_leads.py` — lead management, filtering
  - `admin_conversations.py` — conversation viewer, chat history
  - `admin_settings.py` — dealership settings, config
- **D-06:** Keep Jinja2 templates in `templates/admin/` — one template per module.
- **D-07:** Shared admin auth middleware stays in `api/auth.py` — each module imports it.
- **D-08:** Each module should be under 300 lines. If over, split further.

### Deprecated API Fixes
- **D-09:** Replace all `datetime.utcnow()` with `datetime.now(datetime.UTC)` across the entire codebase (models, engine, services).

### Claude's Discretion
- Test approach: refactor first, then fix tests. Existing tests cover engine behavior — adapt imports and function signatures after merge. Add tests for any new edge cases discovered during refactoring.
- File naming: use `snake_case` matching existing convention.
- Import paths: keep relative imports matching existing pattern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Codebase Understanding
- `.planning/codebase/ARCHITECTURE.md` — Current architecture, state machine, service layer design
- `.planning/codebase/STRUCTURE.md` — Directory tree, module dependencies, where to add new code
- `.planning/codebase/CONVENTIONS.md` — Naming, imports, error handling patterns
- `.planning/codebase/TESTING.md` — Test framework, fixtures, coverage gaps
- `.planning/codebase/CONCERNS.md` — Technical debt details, code smells

### Key Source Files
- `src/services/conversation_engine.py` — Primary engine (500 lines, state machine) — THIS IS THE BASE
- `src/services/orchestrator.py` — Secondary engine (278 lines, LLM-aware) — ABSORB AND DELETE
- `src/services/deterministic_responder.py` — Standalone responder — DELETE after merge
- `src/api/routes/admin_ui.py` — 32KB monolith — SPLIT target
- `src/api/auth.py` — Admin auth — KEEP as shared middleware

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `conversation_engine.process_message()` — Already handles all 7 intents, all state transitions, lead creation, handoff. This is the complete engine.
- `orchestrator._try_handle_visit_intent()` — Visit detection that should be preserved in merge.
- `llm_service.LLMService` — OpenAI integration with tool calling. Keep as optional layer.
- `tests/test_engine.py` — 10 integration tests covering core engine behavior. Adapt after merge.
- `tests/test_intent_entities.py` — 22 unit tests. Should work unchanged.
- `conftest.py` — SQLite in-memory fixtures. Reusable.

### Established Patterns
- **Async everywhere** — All DB operations use AsyncSession, keep this pattern
- **Pydantic Settings** — Config via env vars, single `settings` singleton
- **Router-per-domain** — Each route module has its own `APIRouter` with prefix
- **`get_db` dependency** — All routes use `Depends(get_db)` for session management

### Integration Points
- `src/main.py` — Router registration. Must update after admin split (register new sub-routers).
- `src/api/routes/webhook_cloud.py` — Imports `conversation_engine.process_message`. Must work after merge.
- `src/api/routes/webhooks.py` — Generic webhook. Must work after merge.
- `src/api/routes/debug_routes.py` — Uses orchestrator. Must switch to unified engine.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User delegated all technical decisions to Claude.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-refactoring-tech-debt*
*Context gathered: 2026-03-27*
