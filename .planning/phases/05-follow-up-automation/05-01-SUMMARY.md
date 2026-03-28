---
phase: 05-follow-up-automation
plan: 05-01
subsystem: follow-up-automation
tags: [celery, beat, whatsapp, opt-out, intent, conversation-engine]
dependency_graph:
  requires: [04-02]
  provides: [follow-up-automation, opt-out-detection]
  affects: [conversation-engine, celery-tasks, intent-service]
tech_stack:
  added: [celery-beat-schedule]
  patterns: [asyncio-run-in-sync-celery, jsonb-safe-state-merge, python-side-jsonb-filtering]
key_files:
  created:
    - src/tasks/followup_task.py
  modified:
    - src/services/intent.py
    - src/services/conversation_engine.py
    - src/tasks/celery_app.py
decisions:
  - OPT_OUT uses bare-no regex + keyword list — "no quiero" excluded (ambiguous shopping phrase)
  - asyncio.run() used to call async send_template() from sync Celery worker (safe: no event loop in task thread)
  - sync_engine reused from session.py — no second create_engine() call
  - BROWSING conversations without selected_car_id skipped (avoids unprofessional generic template)
  - 48h minimum gap enforced between followup #1 and followup #2 via last_followup_at ISO timestamp
  - JSONB state updates use {**old_state, key: val} full reassignment pattern
metrics:
  duration: 15min
  completed_date: 2026-03-27
  tasks: 4
  files: 4
---

# Phase 5 Plan 01: Follow-up Task + Beat Schedule + OPT_OUT Intent + Engine Handler Summary

**One-liner:** Celery Beat 15-min scan sends followup_24h_v1 / followup_3d_v1 WhatsApp templates to unresponsive leads with OPT_OUT detection, opted-out guard, and max-2-followup cap.

## What Was Built

### Task 1 — OPT_OUT intent (`src/services/intent.py`)
- Added `OPT_OUT = "OPT_OUT"` constant after existing intent constants
- Added `_OPT_OUT_KEYWORDS` list (12 unambiguous terminal phrases in ES/EN)
- Added `_OPT_OUT_BARE_NO` regex (`^\s*no[\s!.?]*$`) for bare "no" detection
- OPT_OUT check inserted as highest-priority rule in `detect_intent()`, before HUMAN
- "no quiero" intentionally excluded (ambiguous shopping preference)

### Task 2 — OPT_OUT handler (`src/services/conversation_engine.py`)
- Updated import line to include `OPT_OUT` from intent module
- Added opted-out guard (2c) after manager mode check: silently returns empty response with `result.intent = OPT_OUT` set
- Added OPT_OUT handler (2b) before GREETING block:
  - Sets `state = {**state, "opted_out": True}` (local state)
  - Sets acknowledgment text (ES/EN)
  - Logs `opt_out` Event
  - JSONB-safe `conv.state` single-write merge before `flush()`
  - Returns early — does not fall through to other intent handling, entity persistence, or LLM rephrasing

### Task 3 — Celery Beat task (`src/tasks/followup_task.py`)
- New file with `send_followups` Celery task
- `_get_candidates()`: SQL filter on `mode=bot` + `last_message_at` range (24h–30d ago); Python-side stage/state filtering avoids JSONB cast issues
- `_should_followup()`: checks opted_out, followup_count >= 2, stage eligibility, BROWSING+no-car guard, 48h minimum gap between followups
- `_build_components_24h()` / `_build_components_3d()`: build template parameter lists for WhatsApp templates
- `asyncio.run(wa_adapter.send_template(...))` — calls async adapter safely from sync Celery worker
- JSONB-safe state update: `{**old_state, "followup_count": ..., "last_followup_at": ...}`
- Error handling: API errors logged and skipped (followup_count not incremented — retried next Beat run)
- Max retries: 3 (Celery task-level)

### Task 4 — Beat schedule (`src/tasks/celery_app.py`)
- Added `"src.tasks.followup_task"` to `include` list
- Added `beat_schedule` with `"followup-every-15-min"` entry, `schedule: 900` (integer seconds, no crontab import)

## Self-Check

| Check | Result |
|-------|--------|
| `detect_intent("no")` returns `OPT_OUT` | PASS |
| `detect_intent("no me interesa")` returns `OPT_OUT` | PASS |
| `detect_intent("stop")` returns `OPT_OUT` | PASS |
| `detect_intent("no quiero el rojo, quiero el azul")` returns `SEARCH_CAR` (not OPT_OUT) | PASS |
| `detect_intent("quiero hablar con un vendedor")` returns `HUMAN` | PASS |
| All 4 files parse without syntax errors | PASS |
| `sync_engine` imported from session.py (no second create_engine) | PASS |
| `asyncio.run(wa_adapter.send_template(...))` used | PASS |
| Single `conv.state` JSONB-safe assignment in OPT_OUT handler | PASS |
| `result.intent = OPT_OUT` set in opted-out guard | PASS |
| Beat schedule entry with `schedule: 900` | PASS |
| No `crontab` import in celery_app.py | PASS |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

- `_build_components_24h`: `address` hardcoded to `"nuestro salón"` — real implementation should join Dealership table. Intentional placeholder; future plan can wire dealership address.
- `_build_components_3d`: `dealership_name` hardcoded to `"nuestra concesionaria"` — same as above.

These stubs do not prevent the plan's goal: follow-up templates are sent correctly, and the address/name fields are configurable text that Meta-approved template variants can work around.

## Self-Check: PASSED

Files verified on disk:
- `src/tasks/followup_task.py` — created
- `src/services/intent.py` — OPT_OUT constant + keywords + detection at line 20, 96–103, 118–120
- `src/services/conversation_engine.py` — OPT_OUT import at line 23, opted-out guard at 118–126, OPT_OUT handler at 180–206
- `src/tasks/celery_app.py` — followup_task in include, beat_schedule with 900s interval

Commit: d29fa71
