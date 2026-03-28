---
# Phase 7: Admin Dashboard & Analytics - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Admin dashboard enhancements: three specific gaps remain after Phase 1 built the base UI. All other DASH requirements are already implemented. No new pages needed — only targeted changes to existing routes and templates.

</domain>

<decisions>
## Implementation Decisions

### What Already Exists (do NOT reimplement)
- `dashboard.html` + route — shows convs_today, leads_today, pending_handoffs, cars_available, top_searches ✅
- `metrics.html` + route — shows conversion rate, leads_by_source, top_searches (brand+model), handoffs_today ✅
- `conversations.html` + `conversation_detail.html` + routes — full list + history per dealership ✅
- `leads.html` + route — list with filter (intent, status, source) ✅
- All data is per-tenant via session `did` from Phase 6 ✅

### Gap 1: Dashboard — "Pending Visits" replaces "Pending Handoffs" (DASH-01)
- **D-01:** Replace `pending_handoffs` stat card on dashboard with `pending_visits` — count of `Lead` rows where `intent = LeadIntentEnum.visit` AND `status` in (`LeadStatusEnum.new`, `LeadStatusEnum.contacted`) AND `dealership_id == did`.
- **D-02:** The dashboard route (`admin_dashboard.py:dashboard()`) already has `did` — just change the query. Remove the `mode == "manager"` Conversation query, add the Lead intent/status query.
- **D-03:** Update `dashboard.html` stat card label from "Pending handoffs" to "Pending visits".

### Gap 2: Dashboard — "Active Conversations" replaces "Conversations today" (DASH-01)
- **D-04:** Replace `convs_today` with `active_conversations` — count of `Conversation` rows where `mode = "bot"` AND `dealership_id == did` AND `last_message_at >= now - 7 days` (conversations with recent activity, not just today's). Rationale: "active" is more meaningful than "today" for a sales context.
- **D-05:** Update `dashboard.html` stat card label from "Conversations today" to "Active conversations".
- **D-06:** Keep `leads_today` as-is on dashboard — still useful.

### Gap 3: Metrics — Average Bot Response Time (DASH-02)
- **D-07:** Add `avg_response_seconds` to `metrics_page()` route. Computation: for each conversation, find pairs of (inbound Message, next outbound Message by the bot). Average the time difference in seconds across all such pairs for the dealership, over the last 30 days.
- **D-08:** SQL approach — use a self-join or subquery on `messages` table:
  ```sql
  -- For each inbound message, find the next outbound message in the same conversation
  -- avg(outbound.created_at - inbound.created_at) where both within 30 days
  ```
  Use SQLAlchemy with a correlated subquery or Python-side computation. Python-side is simpler: load last 30 days of conversations with messages, compute per-conversation avg, then overall avg.
- **D-09:** If no data → display "N/A" or "—". Format output as seconds if < 60, minutes if >= 60 (e.g. "23s" or "1m 12s"). Compute in Python, pass formatted string to template.
- **D-10:** Add a new stat card to `metrics.html` for avg response time alongside the existing four cards.

### Implementation Scope
- **D-11:** Two files changed: `src/api/routes/admin_dashboard.py` (dashboard route + metrics route), `src/templates/admin/dashboard.html` (stat card labels/values), `src/templates/admin/metrics.html` (new stat card).
- **D-12:** No new routes, no new templates, no migrations needed.
- **D-13:** Python-side response time computation is preferred over complex SQL to avoid JSONB/dialect issues. Load messages for last 30 days per dealership, compute in-memory.

### Tests
- **D-14:** Unit tests for the dashboard stats queries (mock DB, verify pending_visits count logic).
- **D-15:** Unit test for avg_response_seconds computation with sample message timestamps.
- **D-16:** Template rendering is not tested (Jinja templates) — only route logic.

### Claude's Discretion
- Exact SQL vs Python-side implementation for response time (prefer Python-side for simplicity)
- Cutoff for "active" conversations (7 days suggested; can adjust)
- Response time formatting (seconds/minutes display logic)
- Whether to show response time per-day chart or single average (single average is simpler)

</decisions>

<canonical_refs>
## Canonical References

### Existing Code
- `src/api/routes/admin_dashboard.py` — dashboard() and metrics_page() to modify
- `src/templates/admin/dashboard.html` — two stat card updates
- `src/templates/admin/metrics.html` — one new stat card
- `src/db/models.py` — Lead, Conversation, Message, LeadIntentEnum, LeadStatusEnum

</canonical_refs>

<code_context>
## Existing Code Insights

### dashboard() route already has:
- `convs_today` → replace with `active_conversations` (mode=bot, last 7 days)
- `leads_today` → keep
- `pending_handoffs` (mode=manager) → replace with `pending_visits` (intent=visit, status new/contacted)
- `top_searches` → keep
- `cars_available` → keep

### metrics_page() route already has:
- `convs_today`, `leads_today`, `handoffs_today`, `conversion` (4 stat cards)
- `leads_by_source` table
- `top_searches` table
- Missing: `avg_response_seconds` → add as 5th stat card

### Message model:
- `direction` column: `MessageDirectionEnum.inbound` / `MessageDirectionEnum.outbound`
- `created_at` column: DateTime
- `conversation_id` FK

</code_context>

<specifics>
## Specific Requirements

- All three gaps must be closed to satisfy DASH-01, DASH-02
- DASH-03 (top brands/models), DASH-04 (conversation history), DASH-05 (lead filtering) are already done
- Minimal change: only touch the two route functions and two templates

</specifics>

<deferred>
## Deferred Ideas

- Date range selector for metrics page — v2
- Per-day chart/graph for leads and conversations — v2
- Export leads to CSV — v2
- Real-time dashboard updates (WebSocket) — v2
- Email digest / weekly report — v2

</deferred>

---

*Phase: 07-admin-dashboard-analytics*
*Context gathered: 2026-03-27*
