---
phase: 08-billing
plan: "08-03"
title: "Subscription gate in webhook_cloud.py + followup_task.py + admin settings badge"
status: complete
subsystem: billing
tags: [billing, subscription, gating, whatsapp, celery, admin-ui]
dependency_graph:
  requires: [08-01, 08-02]
  provides: [BILL-03, BILL-04]
  affects: [webhook_cloud.py, followup_task.py, settings.html]
tech_stack:
  added: []
  patterns: [silent-200-drop, subscription-gate, read-only-template-card]
key_files:
  modified:
    - src/api/routes/webhook_cloud.py
    - src/tasks/followup_task.py
    - src/templates/admin/settings.html
    - tests/test_followup_task.py
decisions:
  - "Silent 200 drop in webhook_cloud.py after dealership lookup — no error to Meta or customer"
  - "Gate in followup_task.py at dealer load site (line 181), not in _should_followup() — avoids extra DB query"
  - "is_subscription_active(None) covers orphaned conversations where session.get() returns None"
  - "Subscription card is read-only in settings.html — no Python route changes needed"
  - "admin_settings.py GET handler needed no changes — dealer already passed to template"
metrics:
  duration_minutes: 12
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_modified: 4
---

# Phase 8 Plan 03: Subscription Gate + Admin Badge Summary

**One-liner:** WhatsApp inbound and follow-up sends gated by is_subscription_active() with color-coded subscription card in admin settings.

## What Was Built

- **webhook_cloud.py gate** (line 82, after the `if dealer is None` block): calls `is_subscription_active(dealer)` and returns `{"status": "ok"}` silently if inactive — no reply to customer, no error to Meta
- **followup_task.py gate** (line 183, between `dealer = session.get(...)` and `wa_phone_id` assignment): calls `is_subscription_active(dealer)`, increments `skipped` counter and `continue`s — no WhatsApp API call made
- **settings.html subscription card**: read-only card between "Bot behavior" and Save button showing status (color-coded), plan, trial_ends_at (conditional), grace_period_ends_at (conditional, past_due only)

## Insertion Points (Exact Lines)

### webhook_cloud.py
```
Line 82-89 (after "if dealer is None: return"):
    if not is_subscription_active(dealer):
        logger.info(
            "Subscription inactive for dealership=%d (status=%s), dropping WA message",
            dealer.id,
            dealer.subscription_status,
        )
        return {"status": "ok"}
```
Gate appears **before** `dealership_id = dealer.id` (verified by position assertion in task check).

### followup_task.py
```
Line 183-185 (between dealer load and wa_phone_id):
    if not is_subscription_active(dealer):
        skipped += 1
        continue
```
Handles `dealer = None` (orphaned conv) via `is_subscription_active(None) → False`.

### settings.html
New `<div class="card">` block inserted between closing `</div>` of "Bot behavior" card (line 55) and `<div class="form-actions">` (line 57). Card contains:
- Status badge: `text-success` for trial/active, `text-warning` for past_due, `text-muted` for all other states
- Plan: shown only if `dealer.plan` is set
- Trial ends: shown only if `dealer.trial_ends_at` is set
- Grace period ends: shown only if status is past_due and `dealer.grace_period_ends_at` is set

## admin_settings.py

**No changes made.** The GET handler at `/admin/ui/settings` already passes `dealer` to the template context (line 31-36 of admin_settings.py). The new ORM columns added in 08-01 are automatically accessible via the existing `dealer` object.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mocks missing session.get() configuration**
- **Found during:** Overall verification (pytest run after both tasks)
- **Issue:** Two tests in `tests/test_followup_task.py` (`test_sends_first_followup_and_updates_state` and `test_api_error_increments_errors_not_sent`) did not configure `mock_session.get()`. After the billing gate was added, `session.get()` is now called in the hot path; the default `MagicMock` return has `subscription_status` as a `MagicMock` object which is not in `("active", "trial")`, so `is_subscription_active()` returned `False` and sends were incorrectly skipped.
- **Fix:** Added `mock_dealer = MagicMock()` with `subscription_status = "active"` and set `mock_session.get.return_value = mock_dealer` in both affected tests.
- **Files modified:** `tests/test_followup_task.py`
- **Commit:** `a8d4a16`

## Commits

| Hash | Message |
|------|---------|
| `2711c5b` | feat(08-billing-03): add subscription gate to webhook_cloud and followup_task |
| `df94cb7` | feat(08-billing-03): add subscription status card to admin settings.html |
| `a8d4a16` | fix(08-billing-03): update followup_task tests to mock dealer subscription_status |

## Verification Results

- `ast.parse()` clean on both modified Python files
- `is_subscription_active` present in both files
- Gate position in webhook_cloud.py confirmed before `dealership_id = dealer.id` by index assertion
- All 9 required strings present in settings.html
- Subscription card confirmed before form-actions div
- `from src.api.routes.webhook_cloud import router` — OK
- `from src.tasks.followup_task import send_followups` — OK
- **150 tests passed, 0 failed**

## Self-Check: PASSED

Files exist:
- src/api/routes/webhook_cloud.py — FOUND
- src/tasks/followup_task.py — FOUND
- src/templates/admin/settings.html — FOUND
- tests/test_followup_task.py — FOUND

Commits exist:
- 2711c5b — FOUND
- df94cb7 — FOUND
- a8d4a16 — FOUND
