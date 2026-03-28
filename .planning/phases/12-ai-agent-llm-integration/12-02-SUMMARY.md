---
plan: 12-02
phase: 12
subsystem: conversation_engine
status: complete
tags: [llm, conversation-engine, generate-response, per-dealer-config]
completed_date: 2026-03-28
---

# Phase 12 Plan 02: LLM Full Response Integration Summary

**One-liner:** Replaced LLM rephrase shim with full `generate_response` + `ToolsExecutor` call, supporting per-dealer API key/model/flag overrides (D-02, D-04, D-05, D-06, D-07).

## What Changed

`src/services/conversation_engine.py` — block 10b rewritten.

**Before:** Block called `llm.rephrase(result.text, lang)` — a simple post-processing step that rephrased the deterministic response. Used global `settings.llm_enabled` only.

**After:** Block calls `_llm.generate_response(...)` with full conversation history (last 10 messages), `ToolsExecutor` wired in, and a three-layer config resolution:
- D-06: `dealer.llm_enabled` overrides `settings.llm_enabled` when not None
- D-05: `dealer.llm_api_key` overrides `settings.openai_api_key`; skips LLM if neither is set
- D-04: `dealer.llm_model` overrides `settings.openai_model`
- D-07: conversation history fetched via `select(Message)` limited to last 10, reversed to chronological order

`ToolsExecutor` callbacks are passed as `None` — the executor handles lead creation and handoff internally; the callbacks are optional external notifications not used in the deterministic flow.

## Key Files Modified

- `src/services/conversation_engine.py` — lines 432-499 (block 10b replacement)

## Decisions Made

- `on_create_lead=None, on_handoff=None`: No named callback variables exist in `process_message()`. The deterministic branches already call `create_lead_from_conversation` and `_do_handoff` directly. `ToolsExecutor` creates leads internally via `_create_lead`; callbacks are optional. Passing `None` is correct and safe.
- `Message` and `select` were already imported at top-level — no new top-level imports added.
- `_Dealership` imported locally inside the try block as `_Dealership` alias to avoid shadowing the module-level `Dealership` import used elsewhere in the file.

## Verification

- `python -c "from src.services.conversation_engine import process_message; print('OK')"` → OK
- `grep generate_response src/services/conversation_engine.py` → present at lines 432, 485, 499
- `grep rephrase src/services/conversation_engine.py` → no matches (call removed)
- `python -m pytest tests/ -x -q` → 207 passed, 7 warnings, 0 failures

## Deviations from Plan

None — plan executed exactly as written, with one clarification: the plan asked to substitute `ON_CREATE_LEAD_CALLBACK` and `ON_HANDOFF_CALLBACK` with "EXACT names found in process_message()". After reading the full function, no such named callback variables exist — the deterministic path calls module-level helpers directly. `None` is the correct substitution.

## Self-Check: PASSED

- File `src/services/conversation_engine.py` modified and importable
- 207 tests pass with no new failures
