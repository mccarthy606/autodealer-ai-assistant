# Phase 3: Engine Consolidation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Ensure the unified conversation engine (from Phase 1 merge) handles all inbound channels correctly: all 6 conversation states work, multilingual auto-detection responds correctly, duplicate WhatsApp messages are dropped, and all 7 intents trigger correct transitions. No new features — quality assurance and hardening of existing engine.

</domain>

<decisions>
## Implementation Decisions

### Unified Engine (ENG-01)
- **D-01:** conversation_engine.py is already the single engine (Phase 1 merged it). This phase verifies correctness and fixes any gaps found during testing.
- **D-02:** All routes (webhook_cloud.py, debug_routes.py, admin test chat) must use `process_message()` from conversation_engine.

### State Machine (ENG-02)
- **D-03:** Verify all 6 states (NEW, BROWSING, PRESENTING, DETAILS, CLOSING, HANDOFF) + NOTIFY_WAIT work correctly with proper transitions.
- **D-04:** Add comprehensive test coverage for edge cases: state transitions that were previously only in orchestrator, conversation recovery after errors.

### Multilingual (ENG-03)
- **D-05:** Language detection already works (entities.py `detect_language()`). Ensure bot responds in correct language consistently — no mixing Spanish/English within a conversation.
- **D-06:** Language sticky: once detected, keep using that language unless customer switches.

### Message Deduplication (ENG-04)
- **D-07:** Add `wamid` (WhatsApp message ID) column to Message model. Unique constraint per conversation.
- **D-08:** In webhook_cloud.py, check for existing wamid before calling process_message(). If duplicate, return `{"status": "ok", "message": "duplicate"}` without processing.
- **D-09:** New Alembic migration for wamid column.

### Claude's Discretion
- Test strategy: expand existing test_engine.py with new test cases for edge cases
- Language detection improvements if needed
- Error handling in state transitions

</decisions>

<canonical_refs>
## Canonical References

### Engine Code
- `src/services/conversation_engine.py` — Unified engine (after Phase 1 merge)
- `src/services/intent.py` — Intent detection (7 intents)
- `src/services/entities.py` — Entity extraction + language detection
- `src/services/responder.py` — Multilingual response builder
- `src/db/models.py` — Message model (add wamid column)

### Tests
- `tests/test_engine.py` — 10 existing integration tests
- `tests/test_intent_entities.py` — 22 unit tests

### Webhook
- `src/api/routes/webhook_cloud.py` — WhatsApp webhook (add dedup check)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `detect_language()` in entities.py — Already handles es/en detection
- `detect_intent()` in intent.py — All 7 intents with regex patterns
- `EngineResult` class — Structured result with all needed fields
- SQLite in-memory test fixtures — Easy to add new test cases

### Established Patterns
- State stored as JSONB in Conversation.state
- Language tracked in state["language"]
- Intent → handler mapping via if/elif chain in process_message()

### Integration Points
- `webhook_cloud.py` — Add wamid dedup before process_message()
- `models.py` — Add wamid column to Message
- `alembic/versions/` — New migration

</code_context>

<specifics>
## Specific Ideas

No specific requirements — all decisions delegated to Claude.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-engine-consolidation*
*Context gathered: 2026-03-27*
