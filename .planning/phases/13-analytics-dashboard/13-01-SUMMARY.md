---
phase: 13
plan: 01
subsystem: admin-dashboard
tags: [analytics, metrics, funnel, chart, range-param]
dependency_graph:
  requires: []
  provides: [metrics-range-param, funnel-data, chart-data]
  affects: [metrics.html template]
tech_stack:
  added: []
  patterns: [range-param query parsing, zero-fill date grouping, module-level helper]
key_files:
  modified:
    - src/api/routes/admin_dashboard.py
decisions:
  - "_pct() helper defined at module level to avoid per-request re-definition"
  - "Funnel uses all-time counts per D-03 (not range-filtered)"
  - "top_searches in metrics_page() uses range_start; dashboard() keeps its own 7-day window unchanged"
  - "Zero-fill generates full date list from today backwards using range_days"
metrics:
  duration: 5min
  completed: "2026-03-28T22:43:58Z"
  tasks: 1
  files_modified: 1
---

# Phase 13 Plan 01: Metrics Page Range Param + Funnel + Chart Data Summary

**One-liner:** Extended `metrics_page()` with `?range=7|30|90` param, all-time conversion funnel dict, and daily lead-volume chart data with zero-fill.

## What Was Built

The `metrics_page()` route in `src/api/routes/admin_dashboard.py` was extended with four additions:

1. **Range param parsing** — `?range=7|30|90` query param accepted, validated, defaults to 7. `range_start` computed as `datetime.now(UTC) - timedelta(days=range_days)`.

2. **top_searches fix** — The hardcoded `timedelta(days=7)` in the metrics `top_searches` query was replaced with `range_start`, so the top-searches table now reflects the selected window.

3. **Conversion funnel** — Four all-time counts (conversations, leads, visit-intent leads, closed leads) with percentage strings between each step. Passed as `funnel` dict with keys: `convs`, `leads`, `visits`, `closed`, `pct_leads`, `pct_visits`, `pct_closed`.

4. **Lead volume over time** — Daily `Lead.created_at` counts grouped by `func.date()` for the selected range, zero-filled for missing dates. Passed as parallel lists `chart_labels` (date strings) and `chart_data` (int counts).

A `_pct(num, denom)` helper was added at module level (above `metrics_page()`) for safe percentage computation returning "—" on zero denominator.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add range param + funnel queries to metrics_page() | cd78fa8 | src/api/routes/admin_dashboard.py |

## Verification Results

- Python syntax check: PASSED
- `range_days` appears 5 lines (declaration, validation, use in range_start, use in zero-fill loop, in TemplateResponse)
- `funnel_convs`, `funnel_leads`, `funnel_visits`, `funnel_closed` each appear once (4 count queries)
- `chart_labels`, `chart_data` each appear at definition and in TemplateResponse
- `"range_days"`, `"funnel"` each appear once in TemplateResponse dict
- No `timedelta(days=7)` inside `metrics_page()` — the two remaining occurrences are in the separate `dashboard()` function (intentional)

## Deviations from Plan

None - plan executed exactly as written.

The only minor deviation: removed the `from datetime import date as date_type  # noqa: F401` line that was in the plan's Step 4 snippet, since `date` was not actually used (dates are obtained via `.date()` method on datetime objects). This is a cleanup, not a functional change.

## Known Stubs

None - all new variables (`funnel`, `chart_labels`, `chart_data`, `range_days`) are computed from live DB queries and passed directly to the template context.

## Self-Check: PASSED

- `src/api/routes/admin_dashboard.py` exists and contains all new code
- Commit `cd78fa8` verified in git log
- Python syntax check passes
