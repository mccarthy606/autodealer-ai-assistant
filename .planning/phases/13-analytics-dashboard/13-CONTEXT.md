# Phase 13: Analytics Dashboard - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Upgrade the existing `/admin/ui/metrics` page to show: (1) conversion funnel as 4 stat-cards in a row, (2) lead volume over time as a Chart.js line chart with 7d/30d/90d toggle, (3) CSV export of leads. The basic metrics page and dashboard already exist — this phase extends them, it does not rewrite them.

This phase does NOT include: real-time push updates, email reports, custom date ranges beyond 7d/30d/90d, or exporting conversations.

</domain>

<decisions>
## Implementation Decisions

### Charts
- **D-01:** Use Chart.js (CDN) for the lead volume over time chart. Load from CDN in the metrics template — no npm/build step. One line chart showing daily lead count.
- **D-02:** Time range selector: 7d / 30d / 90d toggle buttons. Clicking a button reloads the page with a `?range=7` / `?range=30` / `?range=90` query param. The backend computes the data for the selected range and passes it to the template. No AJAX — full page reload on range change.

### Conversion Funnel
- **D-03:** Funnel displayed as 4 stat-cards in a row (same stat-card component as the existing dashboard). Order: Conversations → Leads → Visits scheduled → Closed. Show count + conversion % between each step (e.g., "42% →"). All-time counts (not filtered by date range).

### CSV Export
- **D-04:** Export only leads. Columns: id, name, phone, intent, status, preferred_brand, preferred_model, budget_min, budget_max, notes, created_at.
- **D-05:** Export endpoint: `GET /admin/ui/leads/export-csv`. Returns `text/csv` with `Content-Disposition: attachment; filename=leads.csv`. Auth-gated (same auth_check as other admin routes). Link/button on the leads page (`leads.html`), not on the metrics page.

### Data Queries
- **D-06:** Lead volume over time: group leads by `date(created_at)` for the selected range, return list of `{date, count}`. Fill missing dates with 0 so the chart has no gaps.
- **D-07:** Top 10 brands/models: already implemented in `metrics_page()` for last 7 days. Extend to respect the selected range param.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Metrics Page
- `src/api/routes/admin_dashboard.py` lines ~208-290 — `metrics_page()` route. Already has: convs_today, leads_today, handoffs_today, conversion, avg_response_str, top_searches, leads_by_source. Phase 13 extends this function — does not replace it.
- `src/templates/admin/metrics.html` — existing template with stats-grid and two tables. Phase 13 adds funnel row, chart card, and range toggle.

### Existing Leads Page (CSV export goes here)
- `src/api/routes/admin_leads.py` — leads listing route. Add export-csv route here.
- `src/templates/admin/leads.html` — add export button here.

### Models
- `src/db/models.py` — `Lead` (id, name, phone, intent, status, preferred_brand, preferred_model, budget_min, budget_max, notes, created_at, dealership_id), `Conversation`, `Event`.

### Existing UI Patterns
- `src/templates/admin/dashboard.html` — stat-card pattern with `stat-card`, `stat-number`, `stat-label` CSS classes. Reuse for funnel.
- Chart.js CDN: `https://cdn.jsdelivr.net/npm/chart.js` — load in metrics.html `<script>` block.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `metrics_page()` already queries top_searches, conversion rate, avg_response_str — extend, don't duplicate.
- `stat-card` HTML/CSS component from dashboard.html — copy for funnel display.
- `auth_check(request)` dependency pattern — used by all admin routes.

### Established Patterns
- Range param: `request.query_params.get("range", "7")` → cast to int → filter by `created_at >= now - timedelta(days=range_days)`.
- CSV response: `from fastapi.responses import StreamingResponse` + `io.StringIO` + `csv.writer`.
- Date grouping in PostgreSQL via SQLAlchemy: `func.date(Lead.created_at).label("day")` + `.group_by("day")`.

### Integration Points
- `admin_dashboard.py` `metrics_page()` — add range param, funnel queries, lead-over-time data.
- `admin_leads.py` — add `GET /leads/export-csv` route.
- `metrics.html` — add funnel row, Chart.js canvas, range toggle buttons.
- `leads.html` — add "Exportar CSV" button/link.

</code_context>

<specifics>
## Specific Ideas

- Chart.js data format: pass `labels` (date strings) and `data` (counts) as JSON via `|tojson` Jinja2 filter directly into the `<script>` block.
- Fill missing dates: generate all dates in range in Python, left-join with query results, fill 0 for missing.
- Funnel percentages: `leads/convs*100`, `visits/leads*100`, `closed/visits*100` — handle division by zero.

</specifics>

<deferred>
## Deferred Ideas

- Real-time push updates (WebSocket/SSE) — own phase if needed
- Custom date range picker — keep 3 fixed ranges for simplicity
- Exporting conversations — out of scope, leads only
- Email scheduled reports — future feature

</deferred>

---

*Phase: 13-analytics-dashboard*
*Context gathered: 2026-03-28*
