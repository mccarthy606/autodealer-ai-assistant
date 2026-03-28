---
phase: 13
plan: 02
subsystem: admin-ui
tags: [analytics, chart.js, funnel, metrics, template]
dependency_graph:
  requires: [13-01]
  provides: [metrics-page-ui]
  affects: [src/templates/admin/metrics.html]
tech_stack:
  added: [Chart.js CDN]
  patterns: [Jinja2 tojson filter, range toggle query param, stat-card funnel row]
key_files:
  modified:
    - src/templates/admin/metrics.html
decisions:
  - "Chart.js loaded from CDN (no npm install) — keeps template self-contained with zero build changes"
  - "Funnel pct_ values rendered inline below stat-label rather than as separate connector arrows — simpler markup"
  - "range_days == N Jinja2 comparison used for active toggle highlighting — matches btn-primary/btn-secondary pattern already present in admin CSS"
metrics:
  duration: 5min
  completed: "2026-03-28"
  tasks: 1
  files: 1
---

# Phase 13 Plan 02: Metrics UI — Funnel, Chart, Range Toggle Summary

**One-liner:** Added Chart.js line chart, 4-card conversion funnel, and 7d/30d/90d range toggle to metrics.html using template vars from plan 13-01.

## What Was Built

`src/templates/admin/metrics.html` was updated to render three new sections using context variables delivered by `metrics_page()` in plan 13-01:

1. **Conversion funnel row** — four `.stat-card` elements in a `.stats-grid` (4-column override) showing `funnel.convs`, `funnel.leads`, `funnel.visits`, `funnel.closed` with `pct_leads`, `pct_visits`, `pct_closed` percentage labels beneath each step.

2. **Range toggle buttons** — three `<a>` links to `?range=7`, `?range=30`, `?range=90`; the active button is highlighted via `btn-primary` (others `btn-secondary`) using `{% if range_days == N %}` Jinja2 conditional.

3. **Chart.js line chart** — `<canvas id="leadsChart">` initialized with `chart_labels` and `chart_data` injected via `{{ chart_labels | tojson }}` and `{{ chart_data | tojson }}`; Chart.js loaded from `https://cdn.jsdelivr.net/npm/chart.js` CDN before the inline script block.

Existing sections (daily stats grid, leads_by_source table, top_searches table) are fully preserved. The "Top searched" heading was updated from hardcoded "last 7 days" to `last {{ range_days }} days`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add funnel row, range toggle, and Chart.js chart to metrics.html | f1a775e | src/templates/admin/metrics.html |

## Verification Results

All acceptance criteria passed:

- `grep -c "cdn.jsdelivr.net/npm/chart.js"` → 1
- `grep -c "leadsChart"` → 2 (canvas id + getElementById)
- `grep -c "chart_labels | tojson"` → 1
- `grep -c "chart_data | tojson"` → 1
- `grep -c "funnel.convs|funnel.leads|funnel.visits|funnel.closed"` → 4
- `grep -c "range_days == 7|range_days == 30|range_days == 90"` → 3
- `grep -c "?range=7|?range=30|?range=90"` → 3
- `grep -c "pct_leads|pct_visits|pct_closed"` → 3
- Jinja2 parse check: `template parses ok`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all template variables (`funnel`, `chart_labels`, `chart_data`, `range_days`) are wired to real query logic delivered by plan 13-01.

## Self-Check: PASSED

- File exists: `src/templates/admin/metrics.html` — FOUND
- Commit f1a775e — FOUND (`git log --oneline -1` confirms)
