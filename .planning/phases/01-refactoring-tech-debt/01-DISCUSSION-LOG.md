# Phase 1: Refactoring & Tech Debt - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 01-refactoring-tech-debt
**Areas discussed:** Engine merge, Admin UI split, Test approach

---

## Engine Merge Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| conversation_engine (Recommended) | Base = state machine. Add LLM as optional layer. Delete orchestrator. | ✓ |
| orchestrator | Base = LLM-aware. Embed state machine inside. | |
| Claude's discretion | Let Claude decide | ✓ (user chose this) |

**User's choice:** "Ты решай" — delegated to Claude
**Notes:** Claude chose conversation_engine as base — it has the complete state machine and handles all intents. orchestrator adds LLM which is optional.

## LLM Mode

| Option | Description | Selected |
|--------|-------------|----------|
| Delete completely | Bot works only deterministically | |
| Keep as option | LLM_ENABLED=true enables response improvement via OpenAI | ✓ |
| Claude's discretion | Let Claude decide | ✓ (user chose this) |

**User's choice:** "Ты решай" — delegated to Claude
**Notes:** Claude chose to keep LLM as optional layer. Default off, can be enabled per-tenant later.

## Admin UI Split

| Option | Description | Selected |
|--------|-------------|----------|
| By domain (Recommended) | admin_inventory.py, admin_leads.py, admin_conversations.py, admin_dashboard.py, admin_settings.py | ✓ |
| By type (routes vs templates) | Logic separate from HTML templates | |
| Claude's discretion | Let Claude decide | ✓ (user chose this) |

**User's choice:** "Ты решай" — delegated to Claude
**Notes:** Claude chose domain split — consistent with existing router-per-domain pattern.

## Test Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Refactor + fix tests (Recommended) | Refactor code, then adapt tests to new structure | ✓ |
| Tests first | Update tests to target structure, then refactor | |
| Claude's discretion | Let Claude decide | ✓ (user chose this) |

**User's choice:** "Ты решай" — delegated to Claude
**Notes:** Claude chose refactor-first — existing tests are comprehensive and will guide correctness.

## Claude's Discretion

All 4 decisions delegated to Claude. Choices based on:
- conversation_engine has the complete state machine (500 lines vs 278 lines)
- Domain split follows existing router-per-domain pattern
- Refactor-first is standard for well-tested codebases

## Deferred Ideas

None — discussion stayed within phase scope.
