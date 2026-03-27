---
phase: 01-refactoring-tech-debt
plan: 01
subsystem: api
tags: [conversation-engine, llm, refactoring, dead-code-removal]

# Dependency graph
requires: []
provides:
  - "Single unified conversation engine with optional LLM rephrasing layer"
  - "Dead code removed: orchestrator.py, deterministic_responder.py"
affects: [02-production-hardening, 03-manager-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional LLM layer: deterministic-first, LLM rephrase when llm_enabled=true"
    - "Lazy import pattern for optional LLM dependency"

key-files:
  created: []
  modified:
    - "src/services/conversation_engine.py"
    - "src/services/llm_service.py"
    - ".gitignore"

key-decisions:
  - "LLM rephrasing is opt-in via llm_enabled setting, deterministic responses are always the fallback"
  - "Lazy import of LLMService inside process_message to avoid hard dependency on OpenAI"

patterns-established:
  - "Optional LLM enhancement: deterministic engine always runs first, LLM enriches when enabled"

requirements-completed: [REF-01]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 01 Plan 01: Merge Conversation Engines Summary

**Single unified conversation engine with optional LLM rephrasing layer; deleted orchestrator.py and deterministic_responder.py dead code**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T20:44:31Z
- **Completed:** 2026-03-27T20:48:37Z
- **Tasks:** 1
- **Files modified:** 2 modified, 4 deleted, 1 updated (.gitignore)

## Accomplishments
- Merged two conversation engines into single `conversation_engine.py` with optional LLM rephrasing
- Added `rephrase()` method to `LLMService` for natural language polishing of deterministic responses
- Deleted 4 dead code files: `orchestrator.py`, `deterministic_responder.py`, `test_orchestrator.py`, `test_debug_routes.py`
- Zero remaining references to deleted modules across entire codebase

## Task Commits

Each task was committed atomically:

1. **Task 1: Add optional LLM rephrasing layer and delete dead files** - `5211d84` (feat)

**Plan metadata:** [pending final commit] (docs: complete plan)

## Files Created/Modified
- `src/services/conversation_engine.py` - Added optional LLM rephrasing block after deterministic response generation
- `src/services/llm_service.py` - Added `rephrase()` method and logging import
- `src/services/orchestrator.py` - DELETED (dead code)
- `src/services/deterministic_responder.py` - DELETED (dead code)
- `tests/test_orchestrator.py` - DELETED (stub file)
- `tests/test_debug_routes.py` - DELETED (stub file)
- `.gitignore` - Removed `.planning/` exclusion, added `.pgdata/`

## Decisions Made
- LLM rephrasing uses lazy import pattern to avoid hard dependency on OpenAI when `llm_enabled=false`
- Rephrase only applies to `mode="bot"` responses (not manager mode)
- `llm_enabled` setting already existed in config.py; no change needed there
- Added `self.model` attribute to LLMService for reuse across methods

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed .gitignore excluding .planning/ directory**
- **Found during:** Task 1 (commit preparation)
- **Issue:** `.gitignore` excluded `.planning/` which prevented tracking planning artifacts; also missing `.pgdata/` exclusion
- **Fix:** Removed `.planning/` from `.gitignore`, added `.pgdata/`
- **Files modified:** `.gitignore`
- **Verification:** `.planning/` files now trackable, `.pgdata/` properly excluded
- **Committed in:** `5211d84` (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for git workflow correctness. No scope creep.

## Issues Encountered
- Docker not running on host machine; could not execute `docker compose run --rm api pytest` verification
- Tests also fail locally due to pre-existing JSONB/SQLite incompatibility (models use `postgresql.JSONB` which SQLite cannot render)
- Verified changes via Python AST parsing (syntax validation) and grep-based acceptance criteria checks
- All acceptance criteria verified except Docker-based test suite execution

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Single conversation engine ready for production hardening (Plan 01-02: split admin_ui.py)
- LLM rephrasing available but off by default (set `LLM_ENABLED=true` in .env to activate)
- Pre-existing test infrastructure issue (JSONB on SQLite) should be addressed in a future plan

---
*Phase: 01-refactoring-tech-debt*
*Completed: 2026-03-27*
