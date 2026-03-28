---
phase: 07-admin-dashboard-analytics
plan: 07-01
subsystem: admin-dashboard
tags: [dashboard, metrics, analytics, queries, templates]
dependency_graph:
  requires: []
  provides: [active_conversations_query, pending_visits_query, avg_response_str_computation]
  affects: [admin/dashboard.html, admin/metrics.html]
tech_stack:
  added: []
  patterns: [python-side-aggregation, naive-datetime-sqlite-compat]
key_files:
  created:
    - tests/test_admin_dashboard.py
  modified:
    - src/api/routes/admin_dashboard.py
    - src/templates/admin/dashboard.html
    - src/templates/admin/metrics.html
decisions:
  - Used LeadStatusEnum.new and .qualified (contacted does not exist)
  - avg_response_str computed Python-side (not SQL) for portability
  - Tests query logic directly without calling route functions to avoid mocking overhead
  - Naive datetimes used in test rows for SQLite DateTime column compatibility
metrics:
  duration: ~15min
  completed: 2026-03-27
  tasks_completed: 3
  files_modified: 4
---

# Phase 07 Plan 01: Admin Dashboard Gaps Summary

**One-liner:** Patched three dashboard stat gaps — active bot conversations (7d), pending visit leads (new/qualified), and Python-side avg bot response time (30d window) with 8 unit tests.

## What Was Built

Three targeted gap fixes to the existing admin dashboard:

1. **Active conversations** — `dashboard()` route now counts `Conversation` rows where `mode="bot"` and `last_message_at >= now - 7 days`, replacing the old "conversations today" count. TemplateResponse key renamed from `convs_today` to `active_conversations`.

2. **Pending visits** — `dashboard()` route now counts `Lead` rows where `intent=visit` AND `status IN (new, qualified)`, replacing the old "pending handoffs" manager-mode conversation count. TemplateResponse key renamed from `pending_handoffs` to `pending_visits`.

3. **Avg response time** — `metrics_page()` route now computes `avg_response_str` (e.g. `"30s"`, `"1m 30s"`, or `"—"`) by fetching messages for the last 30 days, pairing inbound→outbound within each conversation Python-side, and formatting the mean delta. Added `"avg_response_str"` to the TemplateResponse dict and a fifth stat card to `metrics.html`.

## Tests

8 tests in `tests/test_admin_dashboard.py`, all passing:

| Test | Covers |
|---|---|
| `test_pending_visits_counts_visit_new` | intent=visit+new counted; info and handed_off excluded |
| `test_pending_visits_counts_visit_qualified` | intent=visit+qualified counted |
| `test_active_conversations_bot_mode_7days` | bot+recent counted; manager and old excluded |
| `test_active_conversations_excludes_other_dealership` | dealership isolation enforced |
| `test_avg_response_str_basic_seconds` | 30s delta → "30s" |
| `test_avg_response_str_minutes` | 90s delta → "1m 30s" |
| `test_avg_response_str_no_data` | no messages → "—" |
| `test_avg_response_str_old_messages_excluded` | >30 day old messages not counted |

## Deviations from Plan

None — plan executed exactly as written.

Key constraint honored: `LeadStatusEnum.contacted` does not exist in the model; `LeadStatusEnum.new` and `LeadStatusEnum.qualified` used throughout.

## Commits

| Hash | Message |
|---|---|
| `bcd6d4f` | feat(07-01): dashboard gaps — active convs + pending visits + avg response time |

## Self-Check: PASSED

All 4 modified/created files exist on disk. Commit `bcd6d4f` confirmed in git log.
