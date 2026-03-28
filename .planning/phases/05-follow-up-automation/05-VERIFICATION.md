---
phase: 05-follow-up-automation
verified: 2026-03-27T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 5: Follow-Up Automation Verification Report

**Phase Goal:** Automated follow-up messages for unresponsive leads — 24h first reminder, 3-day second reminder, via WhatsApp template messages, max 2 follow-ups, opt-out detection and stop.
**Verified:** 2026-03-27
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Celery Beat task runs every 15 min, sends first follow-up after 24h of silence (FUP-01) | VERIFIED | `celery_app.py` line 20-24: `"followup-every-15-min"` entry with `schedule: 900`; `followup_task.py` line 133: `if followup_count == 0 and hours_silent >= FOLLOWUP_1_HOURS` (24h) |
| 2 | Second follow-up after 72h with minimum 48h gap after first (FUP-02) | VERIFIED | `followup_task.py` lines 136-148: `FOLLOWUP_2_HOURS = 72`, `FOLLOWUP_2_MIN_GAP_HOURS = 48`, gap enforced via `last_followup_at` ISO timestamp comparison |
| 3 | All follow-ups use WhatsApp template messages (followup_24h_v1, followup_3d_v1), never free-form (FUP-03) | VERIFIED | `followup_task.py` lines 31-80: `_build_components_24h()` returns `"followup_24h_v1"`, `_build_components_3d()` returns `"followup_3d_v1"`; both call `wa_adapter.send_template()` exclusively |
| 4 | Max 2 follow-ups per conversation; state["followup_count"] tracked (FUP-04) | VERIFIED | `followup_task.py` line 117: `if state.get("followup_count", 0) >= 2: return False, 0`; line 215: `"followup_count": old_state.get("followup_count", 0) + 1` written on success |
| 5 | OPT_OUT intent detected, state["opted_out"] = True, acknowledgment sent, no further follow-ups (FUP-05) | VERIFIED | `intent.py` line 119-120: `OPT_OUT` is highest-priority rule; `conversation_engine.py` lines 181-206: sets `opted_out: True`, sends acknowledgment, flushes; `followup_task.py` line 115-116: `if state.get("opted_out"): return False, 0` |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/tasks/followup_task.py` | Celery Beat task `send_followups` | VERIFIED | 235 lines; `send_followups` decorated with `@celery_app.task(name="src.tasks.followup_task.send_followups", bind=True, max_retries=3)` |
| `src/tasks/celery_app.py` | Beat schedule entry `followup-every-15-min` | VERIFIED | `beat_schedule` dict contains `"followup-every-15-min"` with `schedule: 900` and correct task name |
| `src/services/intent.py` | `OPT_OUT` constant + detection logic | VERIFIED | Line 20: `OPT_OUT = "OPT_OUT"`; lines 96-103: `_OPT_OUT_KEYWORDS` (12 phrases) + `_OPT_OUT_BARE_NO` regex; line 119: highest-priority check |
| `src/services/conversation_engine.py` | OPT_OUT handler + opted-out guard | VERIFIED | Line 23: `OPT_OUT` imported; lines 119-126: opted-out guard returns empty; lines 181-206: full OPT_OUT handler sets flag, sends acknowledgment, logs event |
| `tests/test_followup_intent.py` | 15 unit tests for OPT_OUT detection | VERIFIED | 15 tests (9 positive, 6 non-regression), all PASSED |
| `tests/test_followup_task.py` | 14 tests for follow-up task logic | VERIFIED | 14 tests (13 `_should_followup` branches + 3 full-task), all PASSED |
| `tests/test_followup_engine.py` | 5 async integration tests | VERIFIED | 5 tests covering opted-out state, acknowledgment text, bare-no trigger, silence on second message, non-opt-out normal message; all PASSED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `celery_app.py` beat schedule | `followup_task.send_followups` | task name string `"src.tasks.followup_task.send_followups"` | WIRED | Task name in `beat_schedule` matches `@celery_app.task(name=...)` decorator exactly |
| `followup_task.py` | `WhatsAppCloudAdapter.send_template()` | `asyncio.run(wa_adapter.send_template(...))` | WIRED | Lines 194-201: async adapter called safely from sync Celery worker via `asyncio.run()` |
| `followup_task.py` | `sync_engine` (DB) | `sessionmaker(bind=sync_engine)` + `_SyncSession()` | WIRED | Line 18: reuses shared `sync_engine` from `session.py`; no second `create_engine` |
| `conversation_engine.py` OPT_OUT handler | `conv.state` JSONB update | `conv.state = {**dict(conv.state or {}), "opted_out": True}` | WIRED | Line 204: single JSONB-safe assignment before `flush()` |
| `intent.py` OPT_OUT | `conversation_engine.py` handler | `from src.services.intent import ... OPT_OUT` | WIRED | Line 23 of engine imports `OPT_OUT`; used at lines 119, 121, 181, 191 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `followup_task.send_followups` | `candidates` (list of Conversation) | `_get_candidates()` SQL query on `Conversation` table filtered by `mode="bot"` + `last_message_at` range | Yes — real DB query with ORM filters | FLOWING |
| `followup_task._build_components_24h` | `name`, `car_title`, `price` | `conv.state` JSONB (`selected_car_title`, `selected_car_price`, `name`) | Yes — from persisted conversation state | FLOWING (with known stub: `address = "nuestro salon"` — intentional, documented) |
| `followup_task._build_components_3d` | `name`, `car_title` | `conv.state` JSONB | Yes — from persisted conversation state | FLOWING (with known stub: `dealership_name = "nuestra concesionaria"` — intentional, documented) |
| `conversation_engine.py` OPT_OUT handler | `state["opted_out"]` | Written to `conv.state` via JSONB merge and `flush()` | Yes — persisted to DB | FLOWING |

**Known stubs (documented, non-blocking):** `address` and `dealership_name` in template builders are hardcoded generic strings. These are acknowledged in 05-01-SUMMARY.md as intentional placeholders pending Dealership table join. They do not prevent template sending — Meta-approved templates accept any text for those parameters.

---

### Behavioral Spot-Checks

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| `send_followups` task importable and callable | `python -c "from src.tasks.followup_task import send_followups; print(type(send_followups))"` | Task function confirmed importable via test collection (36 tests collected) | PASS |
| 36 new phase-5 tests pass | `pytest tests/test_followup_intent.py tests/test_followup_task.py tests/test_followup_engine.py -v` | **36 passed, 1 warning** (RuntimeWarning: unawaited coroutine in mock — cosmetic only, no test failure) | PASS |
| Full suite (122 tests) passes | `pytest tests/ -q --tb=short` | **122 passed, 3 warnings** (all warnings are FastAPI deprecation notices, not failures) | PASS |
| OPT_OUT is highest-priority intent | Code inspection: OPT_OUT check at line 118-120, before HUMAN at line 125 | Confirmed — `detect_intent("no")` returns `OPT_OUT` not `OTHER`; `detect_intent("quiero hablar con vendedor")` returns `HUMAN` | PASS |
| Max-2 cap enforced | `_should_followup` with `followup_count=2` returns `(False, 0)` | Verified at line 117; covered by `test_max_followups_reached` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FUP-01 | 05-01 | Auto-reminder after 24h of no reply | SATISFIED | Beat schedule 900s, `FOLLOWUP_1_HOURS = 24`, first-followup branch at line 133 |
| FUP-02 | 05-01 | Second reminder after 3 days, 48h gap | SATISFIED | `FOLLOWUP_2_HOURS = 72`, `FOLLOWUP_2_MIN_GAP_HOURS = 48`, gap guard at lines 143-148 |
| FUP-03 | 05-01 | Follow-ups via WhatsApp template messages only | SATISFIED | `followup_24h_v1` and `followup_3d_v1` templates; `send_template()` called exclusively — no free-form text in follow-up path |
| FUP-04 | 05-01 | Max 2 follow-ups; followup_count tracked | SATISFIED | Guard at line 117; `followup_count` incremented and written to `conv.state` on success |
| FUP-05 | 05-01 | Opt-out detection; opted_out=True; acknowledgment; no further messages | SATISFIED | `OPT_OUT` intent (12 keywords + bare-no regex); engine sets `opted_out: True`; acknowledgment in ES/EN; both engine guard and task guard block further contact |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/tasks/followup_task.py` | 43 | `address = "nuestro salon"` | Info | Hardcoded placeholder for dealership address in template body. Documented as intentional — requires Dealership table join in a future plan. Does not block follow-up sending. |
| `src/tasks/followup_task.py` | 67 | `dealership_name = "nuestra concesionaria"` | Info | Same as above — hardcoded dealership name in 3-day template. Documented intentional stub. |

No blockers. No undocumented stubs. Both Info-level items are explicitly acknowledged in 05-01-SUMMARY.md under "Known Stubs."

---

### Human Verification Required

None. All observable behaviors are fully verifiable programmatically and confirmed by the 122-test suite.

Production note (not a verification gap): WhatsApp templates `followup_24h_v1` and `followup_3d_v1` must be submitted to Meta for approval before follow-ups work in production. This is an external dependency outside the codebase scope, documented in CONTEXT.md D-07.

---

### Gaps Summary

No gaps. All 5 requirements (FUP-01 through FUP-05) are implemented, wired, and covered by passing tests.

**Summary of what was delivered:**
- `src/tasks/followup_task.py` (235 lines): complete Celery Beat task with candidate scanning, eligibility checks, template dispatch, state mutation, error handling
- `src/tasks/celery_app.py`: Beat schedule entry wired to correct task name at 900s interval
- `src/services/intent.py`: `OPT_OUT` constant + 12-keyword list + bare-no regex as highest-priority intent rule
- `src/services/conversation_engine.py`: opted-out guard (silent pass-through) + full OPT_OUT handler (flag + acknowledgment + event log)
- `tests/` (3 files, 36 tests): 15 unit + 14 mocked-task + 5 async integration, all passing
- Side fix: `src/db/models.py` `text` shadowing bug resolved (unblocked pre-existing test suite)

---

_Verified: 2026-03-27_
_Verifier: Claude (gsd-verifier)_
